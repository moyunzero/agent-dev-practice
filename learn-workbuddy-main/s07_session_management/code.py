#!/usr/bin/env python3
from __future__ import annotations

"""s07_session_management - explicit create, resume, and close boundaries.

The chapter models two things that desktop Agent Harnesses must not conflate:

* a logical session record, which can outlive one worker process; and
* a session runtime, which owns ephemeral resources such as a server, thread,
  port, abort flag, and provider client.

The teaching store is deliberately in memory.  Reusing the same store across
two ``SessionManager`` instances demonstrates restart recovery without
pretending that this chapter ships a durable database.  A production adapter
could persist the same ``SessionRecord`` contract in SQLite or another store.

Usage:
    python s07_session_management/code.py
"""

import copy
import json
import os
import subprocess
import sys
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Callable, Iterable, Mapping, Protocol


# Machine-readable learning path metadata. Tests enforce that every chapter
# declares what it inherits and what it adds.
PROGRESSION = {
    "chapter": "s07_session_management",
    "builds_on": ["s06_sidecar_server"],
    "adds": [
        "logical session and runtime separation",
        "create resume close lifecycle",
        "ACP-like HTTP boundary",
    ],
    "preserves": ["sidecar-managed runtime"],
}


# Shared learning entrypoints: --demo is offline; --provider configures a real
# API environment.  The chapter remains directly runnable like every prior
# lesson while its lifecycle model can also be imported by tests.
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from mini_workbuddy.chapter_demo import maybe_run_chapter_demo
from mini_workbuddy.chapter_demo import prepare_chapter_provider

maybe_run_chapter_demo(__file__, PROGRESSION)
prepare_chapter_provider()

from anthropic import Anthropic
from dotenv import load_dotenv


try:
    import readline

    readline.parse_and_bind("set bind-tty-special-chars off")
    readline.parse_and_bind("set input-meta on")
    readline.parse_and_bind("set output-meta on")
    readline.parse_and_bind("set convert-meta off")
except ImportError:
    pass


load_dotenv(override=True)
if os.getenv("ANTHROPIC_BASE_URL"):
    os.environ.pop("ANTHROPIC_AUTH_TOKEN", None)

WORKDIR = Path.cwd()


# ═══════════════════════════════════════════════════════════════
# Logical session state — persisted facts, not process liveness
# ═══════════════════════════════════════════════════════════════


class SessionState(str, Enum):
    """Lifecycle vocabulary shared by the manager, runtime, and UI.

    ``CLOSED`` means that no runtime resources remain.  It does not mean that
    the logical session record or transcript has been deleted, so the same
    session id may later be resumed with a fresh runtime generation.
    """

    CREATING = "creating"
    IDLE = "idle"
    RUNNING = "running"
    CLOSING = "closing"
    CLOSED = "closed"
    ERROR = "error"


# Compatibility constants keep the state names easy to try in a REPL.
STATE_CREATING = SessionState.CREATING.value
STATE_RUNNING = SessionState.RUNNING.value
STATE_IDLE = SessionState.IDLE.value
STATE_CLOSING = SessionState.CLOSING.value
STATE_CLOSED = SessionState.CLOSED.value
STATE_TERMINATED = STATE_CLOSED
STATE_ERROR = SessionState.ERROR.value

MODE_CRAFT = "craft"  # Act immediately.
MODE_PLAN = "plan"    # Plan before acting.
MODE_ASK = "ask"      # Conversation only; no tools.
SESSION_MODES = frozenset({MODE_CRAFT, MODE_PLAN, MODE_ASK})
SESSION_BACKENDS = frozenset({"pty", "pipe"})


class SessionLifecycleError(RuntimeError):
    """Raised when a caller asks for an invalid lifecycle transition."""


class SessionNotFoundError(SessionLifecycleError):
    """Raised when a session id has no logical record."""


class SessionAlreadyRunningError(SessionLifecycleError):
    """Raised when resume would create a second runtime for one session."""


@dataclass
class SessionRecord:
    """Serializable facts that are allowed to survive a runtime restart.

    Ports, threads, HTTP servers, locks, provider clients, and abort flags are
    intentionally absent.  Those values belong to ``SessionProcess`` and must
    be recreated rather than deserialized.

    ``messages`` is a session transcript used to continue this conversation.
    It is not long-term memory: it is scoped to one session id, is not searched
    across sessions, and carries no relevance or retention policy.
    """

    id: str
    cwd: str
    mode: str = MODE_CRAFT
    backend: str = "pipe"
    status: str = STATE_CREATING
    title: str = "Untitled session"
    model: str = ""
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    runtime_generation: int = 1
    messages: list[dict] = field(default_factory=list)
    last_error: str | None = None

    def summary(self, *, live_port: int | None = None) -> dict[str, object]:
        """Return UI-safe metadata without leaking runtime objects."""

        return {
            "id": self.id,
            "cwd": self.cwd,
            "title": self.title,
            "status": self.status,
            "mode": self.mode,
            "backend": self.backend,
            "model": self.model,
            "runtimeGeneration": self.runtime_generation,
            "messages": len(self.messages),
            "livePort": live_port,
            "lastError": self.last_error,
        }


class SessionStore(Protocol):
    """Persistence port consumed by the manager, independent of one backend."""

    def create(self, record: SessionRecord) -> None: ...

    def save(self, record: SessionRecord) -> None: ...

    def load(self, session_id: str) -> SessionRecord: ...

    def list(self) -> list[SessionRecord]: ...

    def delete(self, session_id: str) -> bool: ...


class InMemorySessionStore:
    """Thread-safe teaching store for logical session records.

    This adapter proves the lifecycle contract, including manager replacement,
    but intentionally does not survive interpreter exit.  Keeping persistence
    behind this small boundary avoids mixing database mechanics into the
    session-runtime lesson.
    """

    def __init__(self) -> None:
        self._records: dict[str, SessionRecord] = {}
        self._lock = threading.RLock()

    def create(self, record: SessionRecord) -> None:
        with self._lock:
            if record.id in self._records:
                raise SessionLifecycleError(f"session already exists: {record.id}")
            self._records[record.id] = copy.deepcopy(record)

    def save(self, record: SessionRecord) -> None:
        with self._lock:
            if record.id not in self._records:
                raise SessionNotFoundError(record.id)
            self._records[record.id] = copy.deepcopy(record)

    def load(self, session_id: str) -> SessionRecord:
        with self._lock:
            try:
                return copy.deepcopy(self._records[session_id])
            except KeyError as exc:
                raise SessionNotFoundError(session_id) from exc

    def list(self) -> list[SessionRecord]:
        with self._lock:
            return [copy.deepcopy(record) for record in self._records.values()]

    def delete(self, session_id: str) -> bool:
        with self._lock:
            return self._records.pop(session_id, None) is not None


# ═══════════════════════════════════════════════════════════════
# ACP-like HTTP boundary — transport delegates lifecycle to runtime
# ═══════════════════════════════════════════════════════════════


class SessionHTTPServer(ThreadingHTTPServer):
    """Typed server wrapper exposing the owning teaching runtime."""

    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, address: tuple[str, int], session: SessionProcess) -> None:
        self.session = session
        super().__init__(address, ACPRequestHandler)


class ACPRequestHandler(BaseHTTPRequestHandler):
    """Small ACP-like surface hosted inside one session runtime.

    The protocol endpoint never owns session transitions.  It delegates to the
    runtime so the CLI, HTTP path, and tests all exercise the same lifecycle.
    """

    server: SessionHTTPServer

    def log_message(self, _format: str, *_args: object) -> None:
        pass  # The chapter prints explicit session-scoped lifecycle logs.

    def do_GET(self) -> None:
        session = self.server.session
        if self.path == "/agent/status":
            self._json(200, session.info())
            return
        if self.path == "/agent/messages":
            self._json(200, {"messages": session.transport_messages()})
            return
        self._json(404, {"error": "not found"})

    def do_POST(self) -> None:
        session = self.server.session
        if self.path == "/agent/abort":
            session.abort()
            self._json(200, {"status": "abort_requested"})
            return
        if self.path != "/agent/send":
            self._json(404, {"error": "not found"})
            return

        try:
            content_length = int(self.headers.get("Content-Length", "0"))
            payload = json.loads(self.rfile.read(content_length) or b"{}")
            message = payload.get("message")
            if not isinstance(message, str) or not message.strip():
                self._json(400, {"error": "message must be a non-empty string"})
                return
            self._json(200, {"response": session.run_agent_loop(message)})
        except SessionLifecycleError as exc:
            self._json(409, {"error": str(exc)})
        except (ValueError, json.JSONDecodeError) as exc:
            self._json(400, {"error": f"invalid JSON request: {exc}"})
        except Exception as exc:
            self._json(500, {"error": f"session turn failed: {exc}"})

    def _json(self, status_code: int, payload: Mapping[str, object]) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


# ═══════════════════════════════════════════════════════════════
# SessionProcess — ephemeral worker for one runtime generation
# ═══════════════════════════════════════════════════════════════


RecordSink = Callable[[SessionRecord], None]


class SessionProcess:
    """Own one generation of ephemeral execution resources.

    The class uses a thread and local HTTP server to keep the lesson portable.
    A production harness could replace this implementation with a child process
    using PTY or pipes while preserving the manager/store lifecycle contract.
    """

    _ALLOWED_TRANSITIONS: dict[str, frozenset[str]] = {
        STATE_CREATING: frozenset({STATE_IDLE, STATE_CLOSING, STATE_ERROR}),
        STATE_IDLE: frozenset({STATE_RUNNING, STATE_CLOSING, STATE_ERROR}),
        STATE_RUNNING: frozenset({STATE_IDLE, STATE_CLOSING, STATE_ERROR}),
        STATE_CLOSING: frozenset({STATE_CLOSED, STATE_ERROR}),
        STATE_CLOSED: frozenset(),
        STATE_ERROR: frozenset({STATE_CLOSING, STATE_CLOSED}),
    }

    def __init__(self, record: SessionRecord, record_sink: RecordSink) -> None:
        self.record = copy.deepcopy(record)
        self._record_sink = record_sink
        self._http_server: SessionHTTPServer | None = None
        self._http_thread: threading.Thread | None = None
        self._state_lock = threading.RLock()
        self._turn_lock = threading.Lock()
        self._abort_requested = threading.Event()
        self.port: int | None = None

    @property
    def id(self) -> str:
        return self.record.id

    @property
    def cwd(self) -> str:
        return self.record.cwd

    @property
    def mode(self) -> str:
        return self.record.mode

    @property
    def backend(self) -> str:
        return self.record.backend

    @property
    def status(self) -> str:
        return self.record.status

    @property
    def messages(self) -> list[dict]:
        return self.record.messages

    def start(self) -> None:
        """Allocate a fresh runtime and publish readiness as one transition.

        Binding directly to port 0 lets the operating system choose the port
        atomically.  Selecting a free port in a separate preflight step would
        introduce a check-then-bind race.
        """

        if self.status != STATE_CREATING:
            raise SessionLifecycleError(
                f"cannot start session {self.id} from {self.status}"
            )
        try:
            try:
                server = SessionHTTPServer(("127.0.0.1", 0), self)
            except PermissionError:
                # Some teaching sandboxes deny all socket binds.  Transport is
                # a runtime capability, not session identity, so the lifecycle
                # remains runnable without pretending that an endpoint exists.
                self._transition(STATE_IDLE)
                self._log(
                    "session started without ACP listener "
                    f"(backend={self.backend}, generation={self.record.runtime_generation}; "
                    "socket binding unavailable)"
                )
                return
            self._http_server = server
            self.port = int(server.server_address[1])
            self._http_thread = threading.Thread(
                target=server.serve_forever,
                name=f"session-http-{self.id}",
                daemon=True,
            )
            self._http_thread.start()
            self._transition(STATE_IDLE)
            self._log(
                f"session started on ACP port {self.port} "
                f"(backend={self.backend}, generation={self.record.runtime_generation})"
            )
        except Exception as exc:
            # A partially allocated listener must not leak when thread startup
            # or readiness publication fails.
            if self._http_server is not None:
                self._http_server.server_close()
                self._http_server = None
            self._http_thread = None
            self.port = None
            self.record.last_error = str(exc)
            self._transition(STATE_ERROR)
            raise

    def run_agent_loop(self, user_message: str) -> str:
        """Run one turn while enforcing the IDLE -> RUNNING -> IDLE boundary."""

        if not self._turn_lock.acquire(blocking=False):
            raise SessionLifecycleError(f"session {self.id} already has a running turn")
        if self.status != STATE_IDLE:
            self._turn_lock.release()
            raise SessionLifecycleError(
                f"session {self.id} cannot accept input while {self.status}"
            )

        self._abort_requested.clear()
        self._transition(STATE_RUNNING)
        try:
            result = self._call_provider(user_message)
            if self.status == STATE_RUNNING:
                self._transition(STATE_IDLE)
            return result
        except Exception as exc:
            self.record.last_error = str(exc)
            if self.status == STATE_RUNNING:
                self._transition(STATE_ERROR)
            raise
        finally:
            self._turn_lock.release()

    def _call_provider(self, user_message: str) -> str:
        """Keep provider mechanics inside the runtime, not the manager/store."""

        client = Anthropic(base_url=os.getenv("ANTHROPIC_BASE_URL"))
        system, tools = self._provider_context()
        messages = copy.deepcopy(self.messages)
        messages.append({"role": "user", "content": user_message})

        while True:
            if self._abort_requested.is_set():
                messages.append({"role": "assistant", "content": "(aborted by user)"})
                self._commit_transcript_if_running(messages)
                return "(aborted by user)"

            response = client.messages.create(
                model=self.record.model,
                system=system,
                messages=messages,
                tools=tools or None,
                max_tokens=8000,
            )
            messages.append({"role": "assistant", "content": response.content})
            if response.stop_reason != "tool_use":
                break

            tool_results: list[dict[str, object]] = []
            for block in response.content:
                if getattr(block, "type", None) != "tool_use":
                    continue
                command = getattr(block, "input", {}).get("command", "")
                self._log(f"tool_use: bash {command[:60]!r}")
                tool_results.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": self._execute_tool(command),
                    }
                )
            messages.append({"role": "user", "content": tool_results})

        if not self._commit_transcript_if_running(messages):
            # Close may finish while a synchronous provider request is still
            # returning.  Late output must not rewrite the retained CLOSED
            # record after its runtime generation has been released.
            return "(turn discarded because the session runtime closed)"
        return "".join(
            block.text
            for block in response.content
            if getattr(block, "type", None) == "text"
        )

    def _provider_context(self) -> tuple[str, list[dict[str, object]]]:
        if self.mode == MODE_ASK:
            return (
                f"You are a helpful assistant at {self.cwd}. "
                "Answer questions and do not use tools.",
                [],
            )
        if self.mode == MODE_PLAN:
            return (
                f"You are a coding agent at {self.cwd}. Plan first, then act.",
                [self._bash_tool()],
            )
        return (
            f"You are a coding agent at {self.cwd}. Act immediately and be concise.",
            [self._bash_tool()],
        )

    @staticmethod
    def _bash_tool() -> dict[str, object]:
        return {
            "name": "bash",
            "description": "Run a shell command.",
            "input_schema": {
                "type": "object",
                "properties": {"command": {"type": "string"}},
                "required": ["command"],
            },
        }

    def _execute_tool(self, command: str) -> str:
        """Demonstrate PTY/pipe selection without claiming to be a sandbox.

        S04 explains permission governance.  This chapter keeps a tiny local
        guard only so its standalone demo does not present obviously dangerous
        commands as acceptable; production isolation still requires OS-level
        controls and a governed tool runner.
        """

        hard_denies = ("rm -rf /", "sudo", "shutdown", "reboot")
        if any(pattern in command for pattern in hard_denies):
            return "Error: command blocked by the standalone teaching guard"
        try:
            completed = subprocess.run(
                command,
                shell=True,
                cwd=self.cwd,
                capture_output=True,
                text=True,
                timeout=120,
            )
            output = (completed.stdout + completed.stderr).strip()
            return output[:50_000] if output else "(no output)"
        except subprocess.TimeoutExpired:
            return "Error: timeout (120s)"
        except OSError as exc:
            return f"Error: {exc}"

    def abort(self) -> None:
        """Request cooperative interruption of the current provider loop."""

        self._abort_requested.set()
        self._log("abort requested")

    def close(self) -> None:
        """Release runtime resources while preserving the logical record.

        Close is idempotent.  It first requests cooperative cancellation, then
        stops the HTTP boundary and publishes ``CLOSED``.  The manager retains
        the record so a later resume can create a new runtime generation.
        """

        if self.status == STATE_CLOSED:
            return
        if self.status not in {STATE_CLOSING, STATE_ERROR}:
            self._transition(STATE_CLOSING)
        self._abort_requested.set()
        try:
            if self._http_server is not None:
                self._http_server.shutdown()
                self._http_server.server_close()
            if self._http_thread is not None:
                self._http_thread.join(timeout=2)
        finally:
            self._http_server = None
            self._http_thread = None
            self.port = None
            if self.status != STATE_CLOSED:
                self._transition(STATE_CLOSED)
            self._log("session runtime closed; logical record retained")

    def set_mode(self, mode: str) -> None:
        if mode not in SESSION_MODES:
            raise ValueError(f"unsupported session mode: {mode}")
        with self._state_lock:
            if self.status != STATE_IDLE:
                raise SessionLifecycleError("mode can change only while session is idle")
            self.record.mode = mode
            self._publish()

    def transport_messages(self) -> list[dict[str, str]]:
        """Return a JSON-safe transcript view for the teaching HTTP endpoint."""

        return [
            {"role": str(message.get("role", "")), "content": str(message.get("content", ""))}
            for message in self.messages
        ]

    def info(self) -> dict[str, object]:
        return self.record.summary(live_port=self.port)

    def _transition(self, next_state: str) -> None:
        with self._state_lock:
            if next_state == self.status:
                return
            allowed = self._ALLOWED_TRANSITIONS.get(self.status, frozenset())
            if next_state not in allowed:
                raise SessionLifecycleError(
                    f"invalid session transition: {self.status} -> {next_state}"
                )
            self.record.status = next_state
            self._publish()

    def _commit_transcript_if_running(self, messages: list[dict]) -> bool:
        """Atomically reject a provider result that arrives after close began."""

        with self._state_lock:
            if self.status != STATE_RUNNING:
                return False
            self.record.messages = messages
            self.record.last_error = None
            self._publish()
            return True

    def _publish(self) -> None:
        with self._state_lock:
            self.record.updated_at = time.time()
            self._record_sink(copy.deepcopy(self.record))

    def _log(self, message: str) -> None:
        timestamp = datetime.now().strftime("%H:%M:%S")
        print(f"\033[90m  [{timestamp}] [session:{self.id}] {message}\033[0m")


# ═══════════════════════════════════════════════════════════════
# SessionManager — Sidecar control plane for records and runtimes
# ═══════════════════════════════════════════════════════════════


class SessionManager:
    """Coordinate logical session identity and live runtime ownership."""

    def __init__(self, store: SessionStore | None = None) -> None:
        self.store = store or InMemorySessionStore()
        self._runtimes: dict[str, SessionProcess] = {}
        self._counter = self._highest_existing_counter(self.store.list())

    @staticmethod
    def _highest_existing_counter(records: Iterable[SessionRecord]) -> int:
        counters: list[int] = []
        for record in records:
            prefix, separator, suffix = record.id.rpartition("_")
            if separator and prefix == "sess" and suffix.isdigit():
                counters.append(int(suffix))
        return max(counters, default=0)

    def create_session(
        self,
        cwd: str,
        mode: str = MODE_CRAFT,
        backend: str = "pipe",
        title: str = "Untitled session",
    ) -> str:
        """Create a new logical identity and its first runtime generation."""

        resolved_cwd = self._validate_options(cwd, mode, backend)
        self._counter += 1
        session_id = f"sess_{self._counter:04d}"
        record = SessionRecord(
            id=session_id,
            cwd=resolved_cwd,
            mode=mode,
            backend=backend,
            title=title,
            model=os.environ.get("MODEL_ID", ""),
        )
        self.store.create(record)
        self._start_runtime(record)
        return session_id

    def resume_session(self, session_id: str) -> str:
        """Start a fresh runtime from a retained logical session record.

        Resume never revives a thread, process, port, or provider client.  It
        reloads recoverable facts, increments ``runtime_generation``, and lets
        the operating system allocate new runtime resources.
        """

        if session_id in self._runtimes:
            raise SessionAlreadyRunningError(session_id)
        record = self.store.load(session_id)
        self._validate_options(record.cwd, record.mode, record.backend)
        record.status = STATE_CREATING
        record.runtime_generation += 1
        record.last_error = None
        self.store.save(record)
        self._start_runtime(record)
        return session_id

    def close_session(self, session_id: str) -> bool:
        """Close a live runtime but keep its record and transcript resumable."""

        runtime = self._runtimes.pop(session_id, None)
        if runtime is not None:
            runtime.close()
            return True

        # Closing an already closed logical session is intentionally idempotent.
        record = self.store.load(session_id)
        if record.status != STATE_CLOSED:
            record.status = STATE_CLOSED
            record.updated_at = time.time()
            self.store.save(record)
        return False

    def forget_session(self, session_id: str) -> bool:
        """Delete logical history only after its runtime has been closed."""

        if session_id in self._runtimes:
            raise SessionLifecycleError(
                f"close session {session_id} before forgetting its record"
            )
        return self.store.delete(session_id)

    def get_session(self, session_id: str) -> SessionProcess | None:
        """Return only a live runtime; use ``load_record`` for closed sessions."""

        return self._runtimes.get(session_id)

    def load_record(self, session_id: str) -> SessionRecord:
        return self.store.load(session_id)

    def list_sessions(self) -> list[dict[str, object]]:
        summaries: list[dict[str, object]] = []
        for record in self.store.list():
            runtime = self._runtimes.get(record.id)
            summaries.append(
                record.summary(live_port=runtime.port if runtime is not None else None)
            )
        return summaries

    def shutdown_all(self) -> None:
        """Close every live runtime while retaining resumable session records."""

        for session_id in list(self._runtimes):
            self.close_session(session_id)

    # The old chapter exposed destroy_session.  Keep it as an explicit alias
    # for runtime close so existing learners do not accidentally lose history.
    def destroy_session(self, session_id: str) -> bool:
        return self.close_session(session_id)

    def _start_runtime(self, record: SessionRecord) -> None:
        runtime = SessionProcess(record, self.store.save)
        try:
            runtime.start()
        except Exception:
            # SessionProcess has already published ERROR with its reason.
            raise
        self._runtimes[record.id] = runtime

    @staticmethod
    def _validate_options(cwd: str, mode: str, backend: str) -> str:
        path = Path(cwd).expanduser().resolve(strict=True)
        if not path.is_dir():
            raise ValueError(f"session cwd must be a directory: {path}")
        if mode not in SESSION_MODES:
            raise ValueError(f"unsupported session mode: {mode}")
        if backend not in SESSION_BACKENDS:
            raise ValueError(f"unsupported session backend: {backend}")
        return str(path)


# ═══════════════════════════════════════════════════════════════
# Entry point — interactive lifecycle walkthrough
# ═══════════════════════════════════════════════════════════════


def _print_sessions(manager: SessionManager, current_session_id: str | None) -> None:
    print(
        f"\033[33m  {'ID':<12} {'Status':<10} {'Gen':<5} {'Mode':<7} "
        f"{'Backend':<8} {'Port':<7} {'Msgs':<6}{'CWD'}"
    )
    print(f"  {'─' * 12} {'─' * 10} {'─' * 5} {'─' * 7} {'─' * 8} {'─' * 7} {'─' * 6}{'─' * 20}")
    for item in manager.list_sessions():
        marker = " ►" if item["id"] == current_session_id else "  "
        port = item["livePort"] if item["livePort"] is not None else "-"
        print(
            f"{marker}{item['id']:<12} {item['status']:<10} "
            f"{item['runtimeGeneration']:<5} {item['mode']:<7} "
            f"{item['backend']:<8} {port!s:<7} {item['messages']:<6}{item['cwd']}"
        )
    print()


def main() -> None:
    print("╔═══════════════════════════════════════════════════════════╗")
    print("║  s07: Session Lifecycle — create / resume / close        ║")
    print("║  逻辑会话可恢复，运行时资源必须重建                         ║")
    print("╚═══════════════════════════════════════════════════════════╝\n")

    store = InMemorySessionStore()
    manager = SessionManager(store)
    current_session_id: str | None = manager.create_session(str(WORKDIR))
    print(f"\033[90m[sidecar] Default session: {current_session_id}\033[0m\n")

    print("命令:")
    print("  /sessions                         — 列出逻辑会话与运行时状态")
    print("  /new [craft|plan|ask] [pty|pipe] — 创建新逻辑会话")
    print("  /switch <id>                      — 切换到正在运行的会话")
    print("  /close [id]                       — 关闭运行时，保留会话记录")
    print("  /resume <id>                      — 从记录创建新运行时")
    print("  /forget <id>                      — 删除已关闭的逻辑会话")
    print("  /mode <mode>                      — 修改空闲会话模式")
    print("  直接输入文字                      — 给当前运行时发消息")
    print("  q                                 — 退出\n")

    while True:
        runtime = (
            manager.get_session(current_session_id)
            if current_session_id is not None
            else None
        )
        prompt_session = current_session_id or "no-session"
        prompt_mode = runtime.mode if runtime is not None else "closed"
        try:
            query = input(
                f"\033[36ms07[{prompt_session}:{prompt_mode}] >> \033[0m"
            ).strip()
        except (EOFError, KeyboardInterrupt):
            break
        if query.lower() in {"q", "exit", "quit"}:
            break
        if not query:
            continue

        parts = query.split()
        command = parts[0]
        try:
            if command == "/sessions":
                _print_sessions(manager, current_session_id)
                continue

            if command == "/new":
                mode = parts[1] if len(parts) > 1 else MODE_CRAFT
                backend = parts[2] if len(parts) > 2 else "pipe"
                current_session_id = manager.create_session(
                    str(WORKDIR), mode=mode, backend=backend
                )
                print(f"\033[90m[sidecar] Created {current_session_id}\033[0m\n")
                continue

            if command == "/switch":
                target = parts[1]
                if manager.get_session(target) is None:
                    raise SessionLifecycleError(
                        f"{target} has no live runtime; use /resume {target}"
                    )
                current_session_id = target
                print(f"\033[90m[sidecar] Switched to {target}\033[0m\n")
                continue

            if command in {"/close", "/destroy"}:
                target = parts[1] if len(parts) > 1 else current_session_id
                if target is None:
                    raise SessionLifecycleError("no session selected")
                manager.close_session(target)
                if current_session_id == target:
                    current_session_id = None
                print(
                    f"\033[90m[sidecar] Closed runtime for {target}; "
                    "record retained\033[0m\n"
                )
                continue

            if command == "/resume":
                target = parts[1]
                manager.resume_session(target)
                current_session_id = target
                print(f"\033[90m[sidecar] Resumed {target}\033[0m\n")
                continue

            if command == "/forget":
                target = parts[1]
                manager.forget_session(target)
                if current_session_id == target:
                    current_session_id = None
                print(f"\033[90m[sidecar] Forgot {target}\033[0m\n")
                continue

            if command == "/mode":
                if runtime is None:
                    raise SessionLifecycleError("no live session selected")
                runtime.set_mode(parts[1])
                print(f"\033[90m[sidecar] Mode -> {parts[1]}\033[0m\n")
                continue

            if runtime is None:
                raise SessionLifecycleError(
                    "no live session selected; use /new or /resume <id>"
                )
            print(
                f"\033[90m[sidecar] -> ACP POST "
                f"http://localhost:{runtime.port}/agent/send\033[0m"
            )
            print(f"\033[32m{runtime.run_agent_loop(query)}\033[0m\n")
        except (IndexError, SessionLifecycleError, SessionNotFoundError, ValueError) as exc:
            print(f"\033[31m{exc}\033[0m\n")

    manager.shutdown_all()
    print("\n\033[90m[sidecar] All runtimes closed. Goodbye.\033[0m")


if __name__ == "__main__":
    main()
