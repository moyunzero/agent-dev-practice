#!/usr/bin/env python3
from __future__ import annotations
"""
s01_agent_loop.py - The Agent Loop

The entire secret of a desktop AI assistant in one pattern:

    while the turn contains tool calls:
        response = LLM(messages, tools)
        execute tools
        append results

    +----------+      +-------+      +---------+
    |   User   | ---> |  LLM  | ---> |  Tool   |
    |  prompt  |      |       |      | execute |
    +----------+      +---+---+      +----+----+
                          ^               |
                          |   tool_result |
                          +---------------+
                          (loop continues)

This is the core loop: feed tool results back to the model until the model
returns a turn without tool calls. WorkBuddy's production-style agent bridge
starts with this loop, then adds the surrounding harness mechanisms taught in
later chapters.

Usage:
    pip install anthropic python-dotenv
    ANTHROPIC_API_KEY=... MODEL_ID=... python s01_agent_loop/code.py
"""

import os
import subprocess
from dataclasses import dataclass
from enum import Enum
from typing import Any


# Machine-readable learning path metadata. Tests enforce that every
# chapter declares what it inherits and what it adds.
PROGRESSION = {
    "chapter": "s01_agent_loop",
    "builds_on": [],
    "adds": [
        "minimal agent loop",
        "single bash tool",
        "tool_use/tool_result feedback",
        "explicit loop stop contract",
    ],
    "preserves": ["interactive CLI"],
}

# Shared learning entrypoints: --demo is offline; --provider deepseek configures real API env.
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

client = Anthropic(base_url=os.getenv("ANTHROPIC_BASE_URL"))
MODEL = os.environ.get("MODEL_ID")
if not MODEL:
    raise SystemExit(
        "MODEL_ID is not set. Copy .env.example to .env and fill in "
        "ANTHROPIC_API_KEY and MODEL_ID (see README quick start)."
    )

SYSTEM = f"You are a coding agent at {os.getcwd()}. Use bash to solve tasks. Act, don't explain."
MAX_TURNS = 8

# -- Tool definition: just bash --
TOOLS = [
    {
        "name": "bash",
        "description": "Run a shell command.",
        "input_schema": {
            "type": "object",
            "properties": {"command": {"type": "string"}},
            "required": ["command"],
        },
    }
]


# -- Explicit turn and stop contracts --
class LoopStopReason(str, Enum):
    """Why the harness stopped asking the model for another turn."""

    FINAL_ANSWER = "final_answer"
    MAX_TOKENS = "max_tokens"
    MAX_TURNS = "max_turns"


@dataclass(frozen=True)
class ToolInvocation:
    """The small provider-neutral slice of a tool_use block needed by s01."""

    tool_use_id: str
    name: str
    arguments: dict[str, Any]


@dataclass(frozen=True)
class AgentTurn:
    """One normalized model turn, before the harness decides what to do next."""

    content: list[Any]
    provider_stop_reason: str | None
    tool_calls: tuple[ToolInvocation, ...]
    text: str

    @classmethod
    def from_response(cls, response: Any) -> AgentTurn:
        """Read text and tool calls once so loop decisions use one source of truth."""

        content = list(getattr(response, "content", []) or [])
        text_parts: list[str] = []
        tool_calls: list[ToolInvocation] = []

        for block in content:
            block_type = getattr(block, "type", None)
            if block_type == "text":
                text_parts.append(str(getattr(block, "text", "")))
            elif block_type == "tool_use":
                raw_arguments = getattr(block, "input", {})
                arguments = dict(raw_arguments) if isinstance(raw_arguments, dict) else {}
                tool_calls.append(
                    ToolInvocation(
                        tool_use_id=str(getattr(block, "id", "")),
                        name=str(getattr(block, "name", "")),
                        arguments=arguments,
                    )
                )

        return cls(
            content=content,
            provider_stop_reason=getattr(response, "stop_reason", None),
            tool_calls=tuple(tool_calls),
            text="".join(text_parts),
        )


@dataclass(frozen=True)
class AgentLoopResult:
    """Observable outcome returned to the CLI, tests, or a later harness layer."""

    stop_reason: LoopStopReason
    turns: int
    tool_calls: int
    final_text: str
    provider_stop_reason: str | None


# -- Tool execution --
def run_bash(command: str) -> str:
    dangerous = ["rm -rf /", "sudo", "shutdown", "reboot", "> /dev/"]
    if any(item in command for item in dangerous):
        return "Error: Dangerous command blocked"
    try:
        completed = subprocess.run(
            command,
            shell=True,
            cwd=os.getcwd(),
            capture_output=True,
            text=True,
            timeout=120,
        )
        output = (completed.stdout + completed.stderr).strip()
        return output[:50000] if output else "(no output)"
    except subprocess.TimeoutExpired:
        return "Error: Timeout (120s)"
    except (FileNotFoundError, OSError) as exc:
        return f"Error: {exc}"


def execute_bash_call(call: ToolInvocation) -> dict[str, Any]:
    """Execute the only tool advertised by s01 and encode its result."""

    command = call.arguments.get("command")
    if not isinstance(command, str) or not command.strip():
        output = "Error: bash requires a non-empty command"
    else:
        print(f"\033[33m$ {command}\033[0m")
        output = run_bash(command)
        print(output[:200])

    return {
        "type": "tool_result",
        "tool_use_id": call.tool_use_id,
        "content": output,
    }


def stop_reason_for(turn: AgentTurn) -> LoopStopReason | None:
    """Return None to continue, otherwise the explicit harness stop reason."""

    # Inspect content instead of trusting stop_reason alone. This also works
    # when a provider reports its stop metadata later than its content blocks.
    if turn.tool_calls:
        return None
    if turn.provider_stop_reason == "max_tokens":
        return LoopStopReason.MAX_TOKENS
    return LoopStopReason.FINAL_ANSWER


# -- The core pattern: call the model, execute tool blocks, and stop explicitly --
def agent_loop(messages: list[dict[str, Any]], max_turns: int = MAX_TURNS) -> AgentLoopResult:
    if max_turns < 1:
        raise ValueError("max_turns must be at least 1")

    tool_call_count = 0
    last_turn: AgentTurn | None = None

    for turn_number in range(1, max_turns + 1):
        response = client.messages.create(
            model=MODEL,
            system=SYSTEM,
            messages=messages,
            tools=TOOLS,
            max_tokens=8000,
        )
        turn = AgentTurn.from_response(response)
        last_turn = turn

        # Append the complete assistant turn before executing any requested I/O.
        messages.append({"role": "assistant", "content": turn.content})

        # A turn without tool calls is terminal; the exact reason remains visible.
        stop_reason = stop_reason_for(turn)
        if stop_reason is not None:
            return AgentLoopResult(
                stop_reason=stop_reason,
                turns=turn_number,
                tool_calls=tool_call_count,
                final_text=turn.text,
                provider_stop_reason=turn.provider_stop_reason,
            )

        # Execute every tool call from this turn and collect protocol-shaped results.
        results = [execute_bash_call(call) for call in turn.tool_calls]
        tool_call_count += len(results)

        # Feed tool results back as one user turn; the next iteration continues.
        messages.append({"role": "user", "content": results})

    # The final tool results stay in messages for inspection, but the harness
    # refuses to start an unbounded ninth turn without an explicit caller choice.
    return AgentLoopResult(
        stop_reason=LoopStopReason.MAX_TURNS,
        turns=max_turns,
        tool_calls=tool_call_count,
        final_text=last_turn.text if last_turn else "",
        provider_stop_reason=last_turn.provider_stop_reason if last_turn else None,
    )


# -- Entry point --
if __name__ == "__main__":
    print("s01: Agent Loop")
    print("输入问题，回车发送。输入 q 退出。\n")

    history: list[dict[str, Any]] = []
    while True:
        try:
            query = input("\033[36ms01 >> \033[0m")
        except (EOFError, KeyboardInterrupt):
            break
        if query.strip().lower() in ("q", "exit", ""):
            break

        history.append({"role": "user", "content": query})
        result = agent_loop(history)

        # Print the model's final text response, or make an incomplete stop visible.
        if result.final_text:
            print(result.final_text)
        if result.stop_reason is not LoopStopReason.FINAL_ANSWER:
            print(f"\033[33m[loop stopped: {result.stop_reason.value}]\033[0m")
        print()
