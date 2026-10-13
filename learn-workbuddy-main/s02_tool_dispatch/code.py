#!/usr/bin/env python3
"""s02_tool_dispatch.py - One registry, many tools.

s01 established the bounded agent loop.  This lesson keeps that loop shape and
replaces its hard-coded bash branch with one explicit dispatch boundary:

    provider tool_use block
            -> ToolCall
            -> ToolRegistry.dispatch()
            -> ToolDispatchResult
            -> provider tool_result block

Each :class:`ToolSpec` stores the model-visible schema beside the Python
handler that implements it.  The registry is therefore the only source of
tool metadata: model schemas, name lookup, argument validation, concurrency
policy, execution, and protocol errors all flow through the same object.

Usage:
    pip install anthropic python-dotenv
    ANTHROPIC_API_KEY=... MODEL_ID=... python s02_tool_dispatch/code.py
"""

from __future__ import annotations

import copy
import glob as globmod
import os
import subprocess
from collections.abc import Callable, Mapping
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, cast


# Machine-readable learning path metadata. Tests enforce that every chapter
# declares what it inherits and what it adds.
PROGRESSION = {
    "chapter": "s02_tool_dispatch",
    "builds_on": ["s01_agent_loop"],
    "adds": [
        "single-source tool registry",
        "schema-based argument validation",
        "structured dispatch results",
        "read-safe concurrent execution",
        "filtered tool subprocess environment",
    ],
    "preserves": ["bounded agent loop", "interactive CLI"],
}

# Shared learning entrypoints: --demo is offline; --provider deepseek
# configures a real API environment before this standalone lesson loads.
import sys as _wb_sys
from pathlib import Path as _wb_Path

_WB_ROOT = _wb_Path(__file__).resolve().parents[1]
if str(_WB_ROOT) not in _wb_sys.path:
    _wb_sys.path.insert(0, str(_WB_ROOT))
from mini_workbuddy.chapter_demo import maybe_run_chapter_demo as _wb_maybe_run_chapter_demo

_wb_maybe_run_chapter_demo(__file__, PROGRESSION)
from mini_workbuddy.chapter_demo import prepare_chapter_provider as _wb_prepare_chapter_provider

_wb_prepare_chapter_provider()

try:
    import readline

    readline.parse_and_bind("set bind-tty-special-chars off")
    readline.parse_and_bind("set input-meta on")
    readline.parse_and_bind("set output-meta on")
    readline.parse_and_bind("set convert-meta off")
except ImportError:
    pass

from anthropic import Anthropic
from dotenv import load_dotenv

load_dotenv(override=True)
if os.getenv("ANTHROPIC_BASE_URL"):
    os.environ.pop("ANTHROPIC_AUTH_TOKEN", None)

WORKDIR = Path.cwd().resolve()
MAX_TURNS = 8
client = Anthropic(base_url=os.getenv("ANTHROPIC_BASE_URL"))
MODEL = os.environ.get("MODEL_ID")
if not MODEL:
    raise SystemExit(
        "MODEL_ID is not set. Copy .env.example to .env and fill in "
        "ANTHROPIC_API_KEY and MODEL_ID (see README quick start)."
    )

SYSTEM = f"You are a coding agent at {WORKDIR}. Use tools to solve tasks. Act, don't explain."


# == Provider-neutral dispatch contracts ==

ToolHandler = Callable[..., str]


class ToolErrorCode(str, Enum):
    """Stable harness errors; provider wording and Python exceptions stay internal."""

    UNKNOWN_TOOL = "unknown_tool"
    INVALID_ARGUMENTS = "invalid_arguments"
    EXECUTION_ERROR = "execution_error"


@dataclass(frozen=True)
class ToolCall:
    """The provider-neutral subset of a tool_use block needed for dispatch."""

    tool_use_id: str
    name: str
    # Provider input remains an untrusted object until the registry validates it.
    arguments: object

    @classmethod
    def from_block(cls, block: Any) -> ToolCall:
        return cls(
            tool_use_id=str(getattr(block, "id", "")),
            name=str(getattr(block, "name", "")),
            arguments=getattr(block, "input", {}),
        )


@dataclass(frozen=True)
class ToolSpec:
    """One tool's model contract, local implementation, and execution policy."""

    name: str
    description: str
    input_schema: Mapping[str, Any]
    handler: ToolHandler
    concurrent_safe: bool = False

    def model_schema(self) -> dict[str, Any]:
        """Return a detached provider schema so callers cannot mutate the registry."""

        return {
            "name": self.name,
            "description": self.description,
            "input_schema": copy.deepcopy(dict(self.input_schema)),
        }


@dataclass(frozen=True)
class ToolDispatchResult:
    """Observable result of crossing from model protocol into local Python."""

    call: ToolCall
    content: str
    error_code: ToolErrorCode | None = None

    @property
    def ok(self) -> bool:
        return self.error_code is None

    def to_protocol_block(self) -> dict[str, Any]:
        """Encode the local result back into an Anthropic tool_result block."""

        block: dict[str, Any] = {
            "type": "tool_result",
            "tool_use_id": self.call.tool_use_id,
            "content": self.content,
        }
        if not self.ok:
            block["is_error"] = True
        return block


class ToolRegistry:
    """Register, describe, validate, look up, and execute tools in one place."""

    def __init__(self) -> None:
        self._specs: dict[str, ToolSpec] = {}

    def register(self, spec: ToolSpec) -> None:
        """Add one complete tool definition and reject ambiguous names early."""

        if not spec.name:
            raise ValueError("tool name must not be empty")
        if spec.name in self._specs:
            raise ValueError(f"duplicate tool name: {spec.name}")
        if spec.input_schema.get("type") != "object":
            raise ValueError(f"tool {spec.name} must declare an object input schema")
        # Keep an owned schema snapshot. ToolSpec is frozen, but callers could
        # otherwise mutate the nested dictionary they used during registration.
        self._specs[spec.name] = ToolSpec(
            name=spec.name,
            description=spec.description,
            input_schema=copy.deepcopy(dict(spec.input_schema)),
            handler=spec.handler,
            concurrent_safe=spec.concurrent_safe,
        )

    def get(self, name: str) -> ToolSpec | None:
        """Resolve a model-provided name without exposing the mutable registry map."""

        return self._specs.get(name)

    def model_schemas(self) -> list[dict[str, Any]]:
        """Build the provider tool catalog from the same specs used at execution."""

        return [spec.model_schema() for spec in self._specs.values()]

    def dispatch(self, call: ToolCall) -> ToolDispatchResult:
        """Validate and execute one call, converting all failures into data."""

        spec = self.get(call.name)
        if spec is None:
            return self._error(
                call,
                ToolErrorCode.UNKNOWN_TOOL,
                f"tool is not registered: {call.name or '<empty>'}",
            )

        validation_error = _validate_arguments(spec.input_schema, call.arguments)
        if validation_error:
            return self._error(call, ToolErrorCode.INVALID_ARGUMENTS, validation_error)

        # Validation guarantees a string-keyed mapping before ** expansion.
        arguments = dict(cast(Mapping[str, Any], call.arguments))
        try:
            output = spec.handler(**arguments)
        except Exception as exc:  # The dispatch boundary must not crash the agent loop.
            return self._error(call, ToolErrorCode.EXECUTION_ERROR, str(exc))
        return ToolDispatchResult(call=call, content=str(output))

    def dispatch_many(self, calls: list[ToolCall]) -> list[ToolDispatchResult]:
        """Execute independent read-safe calls concurrently and preserve result order."""

        specs = [self.get(call.name) for call in calls]
        can_run_concurrently = len(calls) > 1 and all(
            spec is not None and spec.concurrent_safe for spec in specs
        )
        if not can_run_concurrently:
            # Unknown, invalid, bash, and mutating calls take the conservative path.
            return [self.dispatch(call) for call in calls]

        with ThreadPoolExecutor(max_workers=min(4, len(calls))) as pool:
            # executor.map preserves input order even if handlers finish out of order.
            return list(pool.map(self.dispatch, calls))

    @staticmethod
    def _error(
        call: ToolCall,
        code: ToolErrorCode,
        detail: str,
    ) -> ToolDispatchResult:
        return ToolDispatchResult(
            call=call,
            content=f"Error [{code.value}]: {detail}",
            error_code=code,
        )


def _validate_arguments(schema: Mapping[str, Any], raw: Any) -> str | None:
    """Validate the small JSON Schema subset used by this teaching chapter."""

    if not isinstance(raw, Mapping):
        return "arguments must be an object"
    if any(not isinstance(key, str) for key in raw):
        return "argument names must be strings"

    properties = schema.get("properties", {})
    required = schema.get("required", [])
    missing = [name for name in required if name not in raw]
    if missing:
        return f"missing required argument(s): {', '.join(missing)}"

    if schema.get("additionalProperties") is False:
        unknown = sorted(set(raw) - set(properties))
        if unknown:
            return f"unknown argument(s): {', '.join(unknown)}"

    json_types: dict[str, tuple[type, ...]] = {
        "string": (str,),
        "integer": (int,),
        "number": (int, float),
        "boolean": (bool,),
        "object": (Mapping,),
        "array": (list,),
    }
    for name, value in raw.items():
        rule = properties.get(name)
        if not isinstance(rule, Mapping):
            continue
        expected = rule.get("type")
        accepted = json_types.get(expected)
        # JSON booleans are not integers even though bool subclasses int in Python.
        if accepted and (not isinstance(value, accepted) or expected in {"integer", "number"} and isinstance(value, bool)):
            return f"argument {name!r} must be {expected}"
        if "minimum" in rule and value < rule["minimum"]:
            return f"argument {name!r} must be >= {rule['minimum']}"
    return None


def object_schema(
    properties: dict[str, dict[str, Any]],
    required: list[str],
) -> dict[str, Any]:
    """Keep every teaching schema strict and visually compact at registration."""

    return {
        "type": "object",
        "properties": properties,
        "required": required,
        "additionalProperties": False,
    }


# == Tool implementations ==

def safe_path(path_text: str) -> Path:
    """Resolve a model path and reject reads or writes outside this workspace."""

    path = (WORKDIR / path_text).resolve()
    if not path.is_relative_to(WORKDIR):
        raise ValueError(f"path escapes workspace: {path_text}")
    return path


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


def build_subprocess_env(workspace: Path) -> dict[str, str]:
    """Expose only shell basics, never the provider process's credentials.

    HOME and PWD are workspace-scoped so the shell does not inherit access to
    user-level configuration by convention.  This closes direct environment
    inheritance; it does not replace filesystem, network, or OS isolation.
    """

    workspace_path = workspace.expanduser().resolve()
    env = {
        name: os.environ[name]
        for name in _TOOL_ENV_ALLOWLIST
        if os.environ.get(name)
    }
    env.setdefault("PATH", os.defpath)
    env["HOME"] = str(workspace_path)
    env["PWD"] = str(workspace_path)
    return env


def run_bash(command: str) -> str:
    dangerous = ["rm -rf /", "sudo", "shutdown", "reboot", "> /dev/"]
    if any(item in command for item in dangerous):
        return "Error: dangerous command blocked"
    try:
        completed = subprocess.run(
            command,
            shell=True,
            cwd=WORKDIR,
            env=build_subprocess_env(WORKDIR),
            capture_output=True,
            text=True,
            timeout=120,
        )
        output = (completed.stdout + completed.stderr).strip()
        return output[:50000] if output else "(no output)"
    except subprocess.TimeoutExpired:
        return "Error: timeout (120s)"
    except OSError as exc:
        return f"Error: {exc}"


def run_read(path: str, limit: int | None = None) -> str:
    file_path = safe_path(path)
    lines = file_path.read_text(encoding="utf-8").splitlines()
    if limit is not None and limit < len(lines):
        lines = lines[:limit] + [f"... ({len(lines) - limit} more lines)"]
    return "\n".join(lines)


def run_write(path: str, content: str) -> str:
    file_path = safe_path(path)
    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_text(content, encoding="utf-8")
    return f"Wrote {len(content.encode('utf-8'))} bytes to {path}"


def run_edit(path: str, old_text: str, new_text: str) -> str:
    file_path = safe_path(path)
    text = file_path.read_text(encoding="utf-8")
    if old_text not in text:
        return f"Error: text not found in {path}"
    file_path.write_text(text.replace(old_text, new_text, 1), encoding="utf-8")
    return f"Edited {path}"


def run_glob(pattern: str) -> str:
    matches: set[str] = set()
    for match in globmod.glob(os.path.join(globmod.escape(str(WORKDIR)), pattern), recursive=True):
        path = Path(match).resolve()
        if path.is_relative_to(WORKDIR):
            matches.add(str(path.relative_to(WORKDIR)))
    return "\n".join(sorted(matches)) if matches else "(no matches)"


# == Single-source tool registration ==

TOOL_REGISTRY = ToolRegistry()
TOOL_REGISTRY.register(
    ToolSpec(
        name="bash",
        description="Run a shell command in the workspace.",
        input_schema=object_schema(
            {"command": {"type": "string"}},
            ["command"],
        ),
        handler=run_bash,
    )
)
TOOL_REGISTRY.register(
    ToolSpec(
        name="read_file",
        description="Read UTF-8 file contents from the workspace.",
        input_schema=object_schema(
            {
                "path": {"type": "string"},
                "limit": {"type": "integer", "minimum": 1},
            },
            ["path"],
        ),
        handler=run_read,
        concurrent_safe=True,
    )
)
TOOL_REGISTRY.register(
    ToolSpec(
        name="write_file",
        description="Write UTF-8 content to a workspace file.",
        input_schema=object_schema(
            {
                "path": {"type": "string"},
                "content": {"type": "string"},
            },
            ["path", "content"],
        ),
        handler=run_write,
    )
)
TOOL_REGISTRY.register(
    ToolSpec(
        name="edit_file",
        description="Replace the first exact text match in a workspace file.",
        input_schema=object_schema(
            {
                "path": {"type": "string"},
                "old_text": {"type": "string"},
                "new_text": {"type": "string"},
            },
            ["path", "old_text", "new_text"],
        ),
        handler=run_edit,
    )
)
TOOL_REGISTRY.register(
    ToolSpec(
        name="glob",
        description="Find workspace files matching a glob pattern.",
        input_schema=object_schema(
            {"pattern": {"type": "string"}},
            ["pattern"],
        ),
        handler=run_glob,
        concurrent_safe=True,
    )
)


# == Agent loop inherited from s01, now using the registry boundary ==

class LoopStopReason(str, Enum):
    FINAL_ANSWER = "final_answer"
    MAX_TOKENS = "max_tokens"
    MAX_TURNS = "max_turns"


@dataclass(frozen=True)
class AgentTurn:
    content: list[Any]
    provider_stop_reason: str | None
    tool_calls: tuple[ToolCall, ...]
    text: str

    @classmethod
    def from_response(cls, response: Any) -> AgentTurn:
        content = list(getattr(response, "content", []) or [])
        text_parts: list[str] = []
        tool_calls: list[ToolCall] = []
        for block in content:
            block_type = getattr(block, "type", None)
            if block_type == "text":
                text_parts.append(str(getattr(block, "text", "")))
            elif block_type == "tool_use":
                tool_calls.append(ToolCall.from_block(block))
        return cls(
            content=content,
            provider_stop_reason=getattr(response, "stop_reason", None),
            tool_calls=tuple(tool_calls),
            text="".join(text_parts),
        )


@dataclass(frozen=True)
class AgentLoopResult:
    stop_reason: LoopStopReason
    turns: int
    tool_calls: int
    final_text: str
    provider_stop_reason: str | None


def agent_loop(
    messages: list[dict[str, Any]],
    registry: ToolRegistry = TOOL_REGISTRY,
    max_turns: int = MAX_TURNS,
) -> AgentLoopResult:
    """Run the s01 loop while delegating every tool concern to the registry."""

    if max_turns < 1:
        raise ValueError("max_turns must be at least 1")

    tool_call_count = 0
    last_turn: AgentTurn | None = None
    for turn_number in range(1, max_turns + 1):
        response = client.messages.create(
            model=MODEL,
            system=SYSTEM,
            messages=messages,
            tools=registry.model_schemas(),
            max_tokens=8000,
        )
        turn = AgentTurn.from_response(response)
        last_turn = turn
        messages.append({"role": "assistant", "content": turn.content})

        if not turn.tool_calls:
            stop_reason = (
                LoopStopReason.MAX_TOKENS
                if turn.provider_stop_reason == "max_tokens"
                else LoopStopReason.FINAL_ANSWER
            )
            return AgentLoopResult(
                stop_reason=stop_reason,
                turns=turn_number,
                tool_calls=tool_call_count,
                final_text=turn.text,
                provider_stop_reason=turn.provider_stop_reason,
            )

        dispatch_results = registry.dispatch_many(list(turn.tool_calls))
        tool_call_count += len(dispatch_results)
        for result in dispatch_results:
            status = "ok" if result.ok else result.error_code.value
            print(f"\033[36m> {result.call.name}\033[0m [{status}] {result.content[:100]}")
        messages.append(
            {
                "role": "user",
                "content": [result.to_protocol_block() for result in dispatch_results],
            }
        )

    return AgentLoopResult(
        stop_reason=LoopStopReason.MAX_TURNS,
        turns=max_turns,
        tool_calls=tool_call_count,
        final_text=last_turn.text if last_turn else "",
        provider_stop_reason=last_turn.provider_stop_reason if last_turn else None,
    )


if __name__ == "__main__":
    print("s02: Tool Dispatch — 5 tools, one registry")
    print("输入问题，回车发送。输入 q 退出。\n")
    history: list[dict[str, Any]] = []
    while True:
        try:
            query = input("\033[36ms02 >> \033[0m")
        except (EOFError, KeyboardInterrupt):
            break
        if query.strip().lower() in ("q", "exit", ""):
            break

        history.append({"role": "user", "content": query})
        result = agent_loop(history)
        if result.final_text:
            print(result.final_text)
        if result.stop_reason is not LoopStopReason.FINAL_ANSWER:
            print(f"\033[33m[loop stopped: {result.stop_reason.value}]\033[0m")
        print()
