from __future__ import annotations

import itertools
import os
import re
import shlex
import subprocess
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from .config import HarnessConfig
from .storage import SessionRecord, Storage


_TOOL_CALL_ID = re.compile(r"\Acall_[A-Za-z0-9_-]+_[0-9]+_[0-9]+\Z")


@dataclass
class ToolResult:
    tool_call_id: str
    name: str
    content: str
    externalized_path: str | None = None
    exit_code: int | None = None


class PermissionError(RuntimeError):
    pass


_TOOL_ENV_ALLOWLIST = (
    "PATH",
    "LANG",
    "LANGUAGE",
    "LC_ALL",
    "LC_COLLATE",
    "LC_CTYPE",
    "LC_MESSAGES",
    "LC_MONETARY",
    "LC_NUMERIC",
    "LC_TIME",
    "TMPDIR",
    "TEMP",
    "TMP",
)


def build_subprocess_env(workspace: str | Path) -> dict[str, str]:
    """Return the small ambient environment exposed to a tool subprocess.

    Provider credentials and unrelated parent-process variables are omitted by
    construction.  HOME and PWD point at the session workspace so shell tools
    do not discover user-level configuration through the real home directory.
    This is credential hygiene, not an OS sandbox: readable workspace files and
    network access remain governed by their own boundaries.
    """

    workspace_path = Path(workspace).expanduser().resolve()
    env = {
        name: os.environ[name]
        for name in _TOOL_ENV_ALLOWLIST
        if os.environ.get(name)
    }
    # A usable PATH is required even when the parent process did not define one.
    env.setdefault("PATH", os.defpath)
    env["HOME"] = str(workspace_path)
    env["PWD"] = str(workspace_path)
    return env


class ToolRegistry:
    def __init__(self, config: HarnessConfig, storage: Storage) -> None:
        self.config = config
        self.storage = storage
        self._id_counter = itertools.count(1)
        self._id_lock = threading.Lock()
        self._tools: dict[
            str,
            Callable[[str, SessionRecord, str], ToolResult],
        ] = {
            "bash": self._bash,
            "read_file": self._read_file,
            "tool_search": self._tool_search,
        }

    def names(self) -> list[str]:
        return sorted(self._tools)

    def new_call_id(self, name: str) -> str:
        """Reserve an identity before a tool crosses its execution boundary."""

        if name not in self._tools:
            raise KeyError(f"unknown tool: {name}")
        return self._tool_call_id(name)

    def run(
        self,
        name: str,
        argument: str,
        session: SessionRecord,
        *,
        tool_call_id: str | None = None,
    ) -> ToolResult:
        if name not in self._tools:
            raise KeyError(f"unknown tool: {name}")
        call_id = tool_call_id or self._tool_call_id(name)
        # Externalized output uses this value as a file name.  Accept only the
        # same path-safe shape produced by ``new_call_id`` rather than trusting
        # an arbitrary correlation value supplied by another runtime layer.
        if _TOOL_CALL_ID.fullmatch(call_id) is None:
            raise ValueError("tool_call_id does not match the registry format")
        return self._tools[name](argument, session, call_id)

    def _bash(
        self,
        command: str,
        session: SessionRecord,
        tool_call_id: str,
    ) -> ToolResult:
        self._check_command(command)
        try:
            completed = subprocess.run(
                command,
                cwd=session.cwd,
                env=build_subprocess_env(session.cwd),
                shell=True,
                text=True,
                capture_output=True,
                timeout=30,
            )
        except subprocess.TimeoutExpired as exc:
            # NB: subprocess.TimeoutExpired is NOT a subclass of builtin TimeoutError.
            # Convert it so MiniAgent's error boundary (which catches TimeoutError)
            # reports "Tool failed" instead of crashing the whole prompt.
            raise TimeoutError(f"command timed out after {exc.timeout:.0f}s: {command[:80]}") from exc
        content = completed.stdout
        if completed.stderr:
            content += ("\n--- stderr ---\n" + completed.stderr)
        return self._maybe_externalize(
            "bash",
            command,
            content,
            session,
            completed.returncode,
            tool_call_id,
        )

    def _read_file(
        self,
        path: str,
        session: SessionRecord,
        tool_call_id: str,
    ) -> ToolResult:
        target = self._resolve_session_path(path, session)
        content = target.read_text(encoding="utf-8", errors="replace")
        return self._maybe_externalize(
            "read_file",
            path,
            content,
            session,
            0,
            tool_call_id,
        )

    def _tool_search(
        self,
        query: str,
        session: SessionRecord,
        tool_call_id: str,
    ) -> ToolResult:
        descriptions = {
            "bash": "Run a shell command in the session cwd. Dangerous commands are denied.",
            "read_file": "Read a UTF-8 text file by absolute or cwd-relative path.",
            "tool_search": "Search available deferred tools by name or description.",
        }
        needle = query.lower().strip()
        rows = [
            f"- {name}: {desc}"
            for name, desc in descriptions.items()
            if not needle or needle in name.lower() or needle in desc.lower()
        ]
        return ToolResult(
            tool_call_id=tool_call_id,
            name="tool_search",
            content="\n".join(rows),
        )

    def _check_command(self, command: str) -> None:
        try:
            tokens = shlex.split(command)
        except ValueError as exc:
            # Unparseable input (e.g. unbalanced quotes) is denied, not crashed on.
            # Fail-closed: if the harness cannot understand a command, it must not run it.
            raise PermissionError(f"command could not be parsed safely: {exc}") from exc
        denied = {"rm", "sudo", "shutdown", "reboot", "mkfs", "dd"}
        if tokens and tokens[0] in denied:
            raise PermissionError(f"command denied by mini harness policy: {tokens[0]}")
        if any(part in command for part in [" > /dev/", " /etc/passwd", " ~/.ssh"]):
            raise PermissionError("command touches a protected path")

    def _resolve_session_path(self, path: str, session: SessionRecord) -> Path:
        cwd = Path(session.cwd).expanduser().resolve(strict=True)
        candidate = Path(path).expanduser()
        if not candidate.is_absolute():
            candidate = cwd / candidate
        target = candidate.resolve(strict=True)
        if not target.is_relative_to(cwd):
            raise PermissionError(f"path escapes session cwd: {path}")
        if not target.is_file():
            raise PermissionError(f"path is not a regular file: {path}")
        return target

    def _maybe_externalize(
        self,
        name: str,
        argument: str,
        content: str,
        session: SessionRecord,
        exit_code: int | None,
        tool_call_id: str,
    ) -> ToolResult:
        if len(content.encode("utf-8")) <= self.config.tool_result_threshold:
            return ToolResult(
                tool_call_id=tool_call_id,
                name=name,
                content=content,
                exit_code=exit_code,
            )
        path = self.storage.tool_result_path(session, tool_call_id)
        path.write_text(content, encoding="utf-8")
        preview = content[:6_000] + "\n\n...[externalized output]...\n\n" + content[-24_000:]
        pointer = f"\n\nFull output written to: {path}"
        return ToolResult(
            tool_call_id=tool_call_id,
            name=name,
            content=preview + pointer,
            externalized_path=str(path),
            exit_code=exit_code,
        )

    def _tool_call_id(self, name: str) -> str:
        with self._id_lock:
            counter = next(self._id_counter)
        return f"call_{name}_{time.time_ns()}_{counter}"
