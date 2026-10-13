#!/usr/bin/env python3
from __future__ import annotations

"""
s09_jsonl_transcript.py - JSONL Transcript & Session Replay

Append-only JSONL is the source of truth for conversation history.
SQLite is for metadata/indexing. JSONL is for content.

    User says "fix the bug"
        |
        v
    +--------------------------+
    |  session.jsonl (append)  |
    |                          |
    |  {"type":"message",...}  |  user msg
    |  {"type":"reasoning",.}  |  thinking
    |  {"type":"function_call"}|  tool call
    |  {"type":"function_call_ |
    |   result",...}           |  tool result
    |  {"type":"file-history-  |
    |   snapshot",...}         |  file state
    |  {"type":"ai-title",..}  |  auto title
    |                          |
    |  CRASH? Just replay.     |
    +--------------------------+

Usage:
    python s09_jsonl_transcript/code.py
"""



# Machine-readable learning path metadata. Tests enforce that every
# chapter declares what it inherits and what it adds.
PROGRESSION = {
    "chapter": "s09_jsonl_transcript",
    "builds_on": ["s08_model_routing"],
    "adds": [
        "sequenced transcript evidence",
        "stable transcript event ids",
        "derived replay state",
        "explicit transcript-to-memory selection",
        "partial-tail recovery",
    ],
    "preserves": ["model turn event shape", "memory as a selective derived view"],
}

# Shared learning entrypoints: --demo is offline; --provider deepseek configures real API env.
import sys as _wb_sys
from pathlib import Path as _wb_Path
_WB_ROOT = _wb_Path(__file__).resolve().parents[1]
if str(_WB_ROOT) not in _wb_sys.path:
    _wb_sys.path.insert(0, str(_WB_ROOT))
from mini_workbuddy.chapter_demo import maybe_run_chapter_demo as _wb_maybe_run_chapter_demo
_wb_maybe_run_chapter_demo(__file__, PROGRESSION)

import json
import os
import time
import hashlib
import tempfile
import argparse
from copy import deepcopy
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

# --- Constants ---

SESSION_MAX_ITEMS = 1000  # Max items to replay on session load

# 6 event types
TYPE_MESSAGE = "message"
TYPE_REASONING = "reasoning"
TYPE_FUNCTION_CALL = "function_call"
TYPE_FUNCTION_CALL_RESULT = "function_call_result"
TYPE_FILE_SNAPSHOT = "file-history-snapshot"
TYPE_AI_TITLE = "ai-title"

TRANSCRIPT_SOURCE_TYPE = "transcript"
MEMORY_ELIGIBLE_EVENT_TYPES = frozenset({TYPE_MESSAGE, TYPE_FILE_SNAPSHOT})
RESERVED_ENVELOPE_FIELDS = frozenset(
    {"schema_version", "sequence", "recorded_at", "session_id", "event_id"}
)


class TranscriptCorruptionError(RuntimeError):
    """A complete persisted record is malformed or out of sequence."""


class TranscriptValidationError(ValueError):
    """A caller tried to append an event that violates the evidence envelope."""


class MemorySelectionError(ValueError):
    """A transcript event cannot cross the explicit memory-selection boundary."""


@dataclass(frozen=True)
class ReplayState:
    """Ephemeral runtime state derived from immutable transcript evidence.

    This object is safe to discard and rebuild.  It is deliberately not called
    memory: it belongs to one session and contains no retention or relevance
    policy.
    """

    messages: list[dict] = field(default_factory=list)
    title: str | None = None
    file_snapshots: list[dict] = field(default_factory=list)
    total_events: int = 0
    reasoning_count: int = 0
    next_sequence: int = 1
    ignored_partial_tail: bool = False


@dataclass(frozen=True)
class TranscriptMemoryCandidate:
    """A compact source reference offered to a later memory policy.

    Selecting a candidate does not write memory and deliberately does not copy
    the source event body.  Workspace, user, or remote memory still decides
    whether the summary is durable; the transcript remains the evidence owner.
    """

    source_id: str
    session_id: str
    sequence: int
    event_type: str
    captured_at: str
    summary: str
    selection_reason: str
    source_type: str = TRANSCRIPT_SOURCE_TYPE

    def source_metadata(self) -> dict[str, str]:
        """Return the provenance shape accepted by the later memory chapter."""

        return {
            "source_id": self.source_id,
            "source_type": self.source_type,
            "title": f"{self.session_id} event {self.sequence}",
            "captured_at": self.captured_at,
        }


def _required_selection_text(value: str, *, field_name: str) -> str:
    normalized = " ".join(str(value).split())
    if not normalized:
        raise MemorySelectionError(f"{field_name} is required for memory selection")
    return normalized


class JSONLTranscript:
    """Append-only JSONL transcript for a single session.

    Each line is one JSON event. The file grows monotonically —
    we never modify or delete lines. On crash, just replay.

    File location: ~/.workbuddy/projects/<workspace>/<session>.jsonl
    """

    def __init__(self, filepath: str | Path):
        self.path = Path(filepath)
        self.filepath = str(self.path)  # compatibility with the original demo
        self.session_id = self.path.stem
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._ignored_partial_tail = False
        self._missing_final_newline = False

    def _event_id(self, sequence: int) -> str:
        """Build the stable cross-chapter source identifier for one record."""

        return f"{TRANSCRIPT_SOURCE_TYPE}:{self.session_id}:{sequence}"

    def append(self, event: dict) -> None:
        """Append one event as a single JSON line. Never overwrite."""
        reserved = sorted(RESERVED_ENVELOPE_FIELDS.intersection(event))
        if reserved:
            raise TranscriptValidationError(
                "event payload contains reserved envelope fields: " + ", ".join(reserved)
            )
        existing = self._read_all_events()
        # Read-only recovery may ignore an incomplete tail, but appending would
        # turn it into a corrupt complete line. Preserve the evidence unchanged.
        if self._ignored_partial_tail:
            raise TranscriptCorruptionError(
                f"{self.path.name}: cannot append after partial tail; "
                "preserve this log and use a new transcript file"
            )
        # A complete last record without its newline would be glued to the new one.
        if self._missing_final_newline:
            raise TranscriptCorruptionError(
                f"{self.path.name}: cannot append after unterminated last line; "
                "preserve this log and use a new transcript file"
            )
        sequence = existing[-1]["sequence"] + 1 if existing else 1
        envelope = {
            **deepcopy(event),
            "schema_version": 1,
            "sequence": sequence,
            "recorded_at": datetime.now(timezone.utc).isoformat(),
            "session_id": self.session_id,
            "event_id": self._event_id(sequence),
        }
        encoded = (json.dumps(envelope, ensure_ascii=False, sort_keys=True) + "\n").encode()
        descriptor = os.open(self.path, os.O_APPEND | os.O_CREAT | os.O_WRONLY, 0o600)
        try:
            written = os.write(descriptor, encoded)
            if written != len(encoded):
                raise OSError(f"short transcript write: {written}/{len(encoded)} bytes")
            os.fsync(descriptor)
        finally:
            os.close(descriptor)

    def _read_all_events(self) -> list[dict]:
        """Read all events from the JSONL file."""
        # The flag describes this read, not an earlier observation of the path.
        self._ignored_partial_tail = False
        self._missing_final_newline = False
        if not self.path.exists():
            return []
        events: list[dict] = []
        raw = self.path.read_bytes()
        # Judge the final newline on raw bytes; decoded lines may end in "\r" or U+2028.
        self._missing_final_newline = bool(raw) and not raw.endswith(b"\n")
        text = raw.decode("utf-8").replace("\r\n", "\n").replace("\r", "\n")  # same as read_text()
        lines = text.splitlines(keepends=True)
        for line_number, line in enumerate(lines, start=1):
            if not line.strip():
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError as exc:
                partial_tail = line_number == len(lines) and not line.endswith("\n")
                if partial_tail:
                    self._ignored_partial_tail = True
                    break
                raise TranscriptCorruptionError(
                    f"{self.path.name}:{line_number}: invalid complete JSON record"
                ) from exc
            if not isinstance(event, dict):
                raise TranscriptCorruptionError(
                    f"{self.path.name}:{line_number}: record must be a JSON object"
                )
            expected = len(events) + 1
            sequence = event.get("sequence", expected)  # read legacy teaching logs
            if sequence != expected:
                raise TranscriptCorruptionError(
                    f"{self.path.name}:{line_number}: expected sequence {expected}, got {sequence}"
                )
            event.setdefault("sequence", sequence)
            session_id = event.get("session_id", self.session_id)
            if session_id != self.session_id:
                raise TranscriptCorruptionError(
                    f"{self.path.name}:{line_number}: expected session_id "
                    f"{self.session_id!r}, got {session_id!r}"
                )
            event.setdefault("session_id", self.session_id)
            expected_event_id = self._event_id(expected)
            event_id = event.get("event_id", expected_event_id)
            if event_id != expected_event_id:
                raise TranscriptCorruptionError(
                    f"{self.path.name}:{line_number}: expected event_id "
                    f"{expected_event_id!r}, got {event_id!r}"
                )
            event.setdefault("event_id", expected_event_id)
            events.append(event)
        return events

    def replay(self, max_items: int = SESSION_MAX_ITEMS) -> list[dict]:
        """Read backwards, return reconstructed messages (<= max_items).

        Takes the last max_items events from the JSONL file and
        reconstructs an LLM-compatible messages[] array in chronological
        order. This prevents ultra-long sessions from filling context
        on load.

        In production, this reads backwards via file seek for efficiency.
        Here we read all lines and slice — same concept, simpler code.
        """
        events = self._read_all_events()
        recent = events[-max_items:]  # Take last N events

        messages = []
        for event in recent:
            msg = self._event_to_message(event)
            if msg:
                messages.append(msg)
        return messages

    def replay_state(self, max_items: int = SESSION_MAX_ITEMS) -> ReplayState:
        """Fold evidence into disposable state for a replacement runtime."""
        events = self._read_all_events()
        recent = events[-max_items:]
        messages = [
            message
            for event in recent
            if (message := self._event_to_message(event)) is not None
        ]
        title = None
        snapshots: list[dict] = []
        reasoning_count = 0
        for event in events:
            if event.get("type") == TYPE_AI_TITLE:
                title = event.get("title")
            elif event.get("type") == TYPE_FILE_SNAPSHOT:
                snapshots.append({"path": event.get("path"), "hash": event.get("hash")})
            elif event.get("type") == TYPE_REASONING:
                reasoning_count += 1
        return ReplayState(
            messages=messages,
            title=title,
            file_snapshots=snapshots,
            total_events=len(events),
            reasoning_count=reasoning_count,
            next_sequence=len(events) + 1,
            ignored_partial_tail=self._ignored_partial_tail,
        )

    def select_memory_candidate(
        self,
        event_id: str,
        *,
        summary: str,
        reason: str,
    ) -> TranscriptMemoryCandidate:
        """Select one persisted event for evaluation by a memory policy.

        The caller must name one stable event id and explain the selection.
        Replay limits are unrelated: replay controls prompt context, while this
        method creates a source-bearing candidate for s10-s12 to evaluate.
        Reasoning, tool calls/results, and titles are never promoted directly.
        """

        normalized_summary = _required_selection_text(summary, field_name="summary")
        normalized_reason = _required_selection_text(reason, field_name="reason")
        events = self._read_all_events()
        selected = next(
            (event for event in events if event.get("event_id") == event_id),
            None,
        )
        if selected is None:
            raise MemorySelectionError(f"unknown transcript event: {event_id}")
        event_type = str(selected.get("type", ""))
        if event_type not in MEMORY_ELIGIBLE_EVENT_TYPES:
            raise MemorySelectionError(
                f"event type {event_type!r} is not eligible for memory selection"
            )
        captured_at = str(selected.get("recorded_at", "")).strip()
        if not captured_at:
            raise MemorySelectionError(
                f"transcript event {event_id} has no recorded_at provenance"
            )
        return TranscriptMemoryCandidate(
            source_id=str(selected["event_id"]),
            session_id=str(selected["session_id"]),
            sequence=int(selected["sequence"]),
            event_type=event_type,
            captured_at=captured_at,
            summary=normalized_summary,
            selection_reason=normalized_reason,
        )

    def recover(self) -> dict:
        """Simulate crash recovery: open file, replay, reconstruct state.

        Returns recovered messages + metadata (title, file snapshots, stats).
        This is what happens when a session process crashes and restarts:
        open the JSONL, replay everything, pick up where we left off.
        """
        state = self.replay_state()
        return {
            "messages": state.messages,
            "title": state.title,
            "file_snapshots": state.file_snapshots,
            "total_events": state.total_events,
            "message_count": len(state.messages),
            "reasoning_count": state.reasoning_count,
            "next_sequence": state.next_sequence,
            "ignored_partial_tail": state.ignored_partial_tail,
        }

    @staticmethod
    def _event_to_message(event: dict) -> dict | None:
        """Convert a JSONL event to an LLM message (or None if metadata).

        - message             -> {"role": ..., "content": ...}
        - function_call       -> assistant message with tool_use block
        - function_call_result-> user message with tool_result block
        - reasoning, file-history-snapshot, ai-title -> None (metadata)
        """
        etype = event.get("type")

        if etype == TYPE_MESSAGE:
            return {"role": event["role"], "content": event["content"]}

        if etype == TYPE_FUNCTION_CALL:
            return {
                "role": "assistant",
                "content": [{
                    "type": "tool_use",
                    "id": event["callId"],
                    "name": event["name"],
                    "input": event["arguments"],
                }],
            }

        if etype == TYPE_FUNCTION_CALL_RESULT:
            return {
                "role": "user",
                "content": [{
                    "type": "tool_result",
                    "tool_use_id": event["callId"],
                    "content": event["output"],
                }],
            }

        # reasoning, file-history-snapshot, ai-title are metadata
        return None

    def count_lines(self) -> int:
        """Count total lines in the JSONL file."""
        if not os.path.exists(self.filepath):
            return 0
        with open(self.filepath, "r", encoding="utf-8") as f:
            return sum(1 for line in f if line.strip())


# --- Mock LLM (no API calls) ---

class MockLLM:
    """Simulates LLM with a scripted conversation.

    Exercises all 6 event types in a realistic bug-fix scenario.
    No API calls — just a fixed script that demonstrates JSONL logging.
    """

    def __init__(self):
        self.step = 0
        self.script = self._build_script()

    def _build_script(self) -> list[dict]:
        fixed_code = (
            "def login(user, pwd):\n"
            "    if pwd == '123':\n"
            "        return True\n"
            "    return False"
        )
        return [
            {"type": TYPE_MESSAGE, "role": "user",
             "content": "帮我修复 main.py 里的登录 bug"},
            {"type": TYPE_REASONING,
             "content": "用户说有登录 bug，先读 main.py 看代码结构。"},
            {"type": TYPE_FUNCTION_CALL, "name": "read_file",
             "arguments": {"path": "main.py"}, "callId": "call_001"},
            {"type": TYPE_FUNCTION_CALL_RESULT, "callId": "call_001",
             "output": {"content": "def login(user, pwd):\n    if pwd = '123':  # BUG\n        return True\n    return False"}},
            {"type": TYPE_REASONING,
             "content": "找到 bug！pwd = '123' 应为 pwd == '123'。= 是赋值，== 是比较。"},
            {"type": TYPE_FUNCTION_CALL, "name": "write_file",
             "arguments": {"path": "main.py", "content": fixed_code}, "callId": "call_002"},
            {"type": TYPE_FUNCTION_CALL_RESULT, "callId": "call_002",
             "output": {"content": "File written: main.py (89 bytes)"}},
            {"type": TYPE_FILE_SNAPSHOT, "path": "main.py",
             "hash": hashlib.md5(fixed_code.encode()).hexdigest()},
            {"type": TYPE_MESSAGE, "role": "assistant",
             "content": "已修复！pwd = '123' 应为 pwd == '123'。已更新 main.py。"},
            {"type": TYPE_AI_TITLE, "title": "修复 main.py 登录 bug"},
        ]

    def next_event(self) -> dict | None:
        if self.step >= len(self.script):
            return None
        event = self.script[self.step]
        self.step += 1
        return event


# --- Console output helpers ---

def log_event(event: dict, line_count: int):
    """Print a colored log line for an appended event."""
    etype = event["type"]

    if etype == TYPE_MESSAGE:
        role = event["role"]
        color = "\033[36m" if role == "user" else "\033[32m"
        print(f"{color}[{role:9s}]\033[0m {event['content'][:70]}")
    elif etype == TYPE_REASONING:
        print(f"\033[35m[thinking ]\033[0m {event['content'][:70]}")
    elif etype == TYPE_FUNCTION_CALL:
        args = json.dumps(event["arguments"], ensure_ascii=False)
        print(f"\033[33m[tool_call]\033[0m {event['name']}({args[:50]})")
    elif etype == TYPE_FUNCTION_CALL_RESULT:
        out = str(event["output"].get("content", ""))[:50]
        print(f"\033[90m[tool_res ]\033[0m {out}...")
    elif etype == TYPE_FILE_SNAPSHOT:
        print(f"\033[34m[snapshot ]\033[0m {event['path']} (hash: {event['hash'][:8]}...)")
    elif etype == TYPE_AI_TITLE:
        print(f"\033[93m[ai-title ]\033[0m \"{event['title']}\"")

    print(f"           \033[90mjsonl line: {line_count}\033[0m")


# --- Demo: Agent loop + Crash + Recovery ---

def demo():
    """Run a full demo: agent conversation -> crash -> recovery."""

    # Simulate ~/.workbuddy/projects/myproject/session_abc123.jsonl
    tmpdir = tempfile.mkdtemp(prefix="workbuddy_demo_")
    session_file = os.path.join(tmpdir, "myproject", "session_abc123.jsonl")

    transcript = JSONLTranscript(session_file)
    llm = MockLLM()

    # -- Part 1: Agent loop — log everything to JSONL --
    print("=" * 60)
    print("  Part 1: Agent Loop — all events logged to JSONL")
    print("=" * 60)
    print(f"\n  Transcript: {session_file}\n")

    in_memory_messages = []

    while True:
        event = llm.next_event()
        if event is None:
            break

        transcript.append(event)
        log_event(event, transcript.count_lines())

        msg = JSONLTranscript._event_to_message(event)
        if msg:
            in_memory_messages.append(msg)

    print(f"\n  In-memory messages: {len(in_memory_messages)}")
    print(f"  JSONL file lines:   {transcript.count_lines()}")

    # -- Part 2: Simulate crash --
    print("\n" + "=" * 60)
    print("  Part 2: CRASH — in-memory state lost!")
    print("=" * 60)
    print(f"\n  >>> Process killed. In-memory messages cleared.")
    print(f"  >>> Was holding {len(in_memory_messages)} messages in memory.")
    print(f"  >>> JSONL file still has {transcript.count_lines()} lines on disk.")

    in_memory_messages = []  # Simulated crash — memory gone

    # -- Part 3: Recovery from JSONL --
    print("\n" + "=" * 60)
    print("  Part 3: Recovery — replay from JSONL")
    print("=" * 60)

    # New transcript instance = fresh process opening the same file
    recovered = JSONLTranscript(session_file)
    state = recovered.recover()

    print(f"\n  Recovered state:")
    print(f"    Title:          {state['title']}")
    print(f"    Total events:   {state['total_events']}")
    print(f"    Messages:       {state['message_count']}")
    print(f"    Reasoning:      {state['reasoning_count']}")
    print(f"    File snapshots: {len(state['file_snapshots'])}")

    print(f"\n  Reconstructed messages[]:")
    for i, msg in enumerate(state["messages"]):
        role = msg["role"]
        content = msg["content"]
        if isinstance(content, list):
            block = content[0]
            if block.get("type") == "tool_use":
                desc = f"[tool_use: {block['name']}]"
            else:
                desc = f"[tool_result: {block.get('tool_use_id', '?')}]"
        else:
            desc = content[:50]
        print(f"    [{i}] {role:9s}: {desc}")

    print(f"\n  Recovery successful — {state['total_events']} events replayed")
    print(f"  {state['message_count']} messages reconstructed from JSONL")

    # -- Show raw JSONL --
    print("\n" + "=" * 60)
    print("  Raw JSONL file:")
    print("=" * 60)
    with open(session_file, "r", encoding="utf-8") as f:
        for i, line in enumerate(f, 1):
            print(f"  {i:2d}. {line.rstrip()}")
    print(f"\n  File: {session_file}")
    print(f"  Size: {os.path.getsize(session_file)} bytes")


def interactive():
    """Interactive JSONL transcript shell."""
    tmpdir = tempfile.mkdtemp(prefix="workbuddy_jsonl_interactive_")
    session_file = os.path.join(tmpdir, "session_interactive.jsonl")
    transcript = JSONLTranscript(session_file)
    print("s09: JSONL Transcript Interactive")
    print(f"Transcript: {session_file}")
    print("Commands:")
    print("  user <text>")
    print("  assistant <text>")
    print("  reason <text>")
    print("  tool <name>")
    print("  result <text>")
    print("  title <text>")
    print("  replay")
    print("  recover")
    print("  raw")
    print("  q")
    last_call_id = "call_interactive"

    while True:
        try:
            line = input("s09 >> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return
        if not line or line.lower() in {"q", "quit", "exit"}:
            return
        if line.startswith("user "):
            event = {"type": TYPE_MESSAGE, "role": "user", "content": line[5:]}
        elif line.startswith("assistant "):
            event = {"type": TYPE_MESSAGE, "role": "assistant", "content": line[10:]}
        elif line.startswith("reason "):
            event = {"type": TYPE_REASONING, "content": line[7:]}
        elif line.startswith("tool "):
            name = line[5:].strip() or "read_file"
            last_call_id = f"call_{transcript.count_lines()+1:03d}"
            event = {"type": TYPE_FUNCTION_CALL, "name": name, "arguments": {}, "callId": last_call_id}
        elif line.startswith("result "):
            event = {"type": TYPE_FUNCTION_CALL_RESULT, "callId": last_call_id, "output": {"content": line[7:]}}
        elif line.startswith("title "):
            event = {"type": TYPE_AI_TITLE, "title": line[6:]}
        elif line == "replay":
            print(json.dumps(transcript.replay(), indent=2, ensure_ascii=False))
            continue
        elif line == "recover":
            print(json.dumps(transcript.recover(), indent=2, ensure_ascii=False))
            continue
        elif line == "raw":
            print(open(session_file, encoding="utf-8").read() if os.path.exists(session_file) else "(empty)")
            continue
        else:
            print("Unknown command. Use: user/assistant/reason/tool/result/title/replay/recover/raw/q")
            continue
        transcript.append(event)
        log_event(event, transcript.count_lines())


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="JSONL transcript demo")
    parser.add_argument("--interactive", action="store_true", help="open an interactive JSONL transcript shell")
    args = parser.parse_args()
    if args.interactive:
        interactive()
    else:
        demo()
