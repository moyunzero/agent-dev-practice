"""Behavior tests for the first lesson's explicit agent-loop contract."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any


ROOT = Path(__file__).resolve().parents[1]


def load_s01(monkeypatch):
    """Import the lesson with the offline Anthropic stub, then replace its client."""

    stub_dir = ROOT / "tests" / "stubs"
    monkeypatch.syspath_prepend(str(stub_dir))
    monkeypatch.setenv("MODEL_ID", "offline-test-model")
    saved_anthropic = sys.modules.pop("anthropic", None)

    module_name = "s01_agent_loop_test_module"
    spec = importlib.util.spec_from_file_location(module_name, ROOT / "s01_agent_loop" / "code.py")
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[module_name] = module
    try:
        spec.loader.exec_module(module)
    finally:
        # The lesson has already captured the stub class. Restore the process-wide
        # module cache so this focused test cannot affect provider tests that run later.
        sys.modules.pop("anthropic", None)
        if saved_anthropic is not None:
            sys.modules["anthropic"] = saved_anthropic
    return module


def text_block(text: str) -> SimpleNamespace:
    return SimpleNamespace(type="text", text=text)


def tool_block(call_id: str, command: str) -> SimpleNamespace:
    return SimpleNamespace(
        type="tool_use",
        id=call_id,
        name="bash",
        input={"command": command},
    )


def response(*blocks: Any, stop_reason: str | None) -> SimpleNamespace:
    return SimpleNamespace(content=list(blocks), stop_reason=stop_reason)


class FakeMessages:
    def __init__(self, responses: list[SimpleNamespace]) -> None:
        self.responses = iter(responses)
        self.calls: list[dict[str, Any]] = []

    def create(self, **kwargs: Any) -> SimpleNamespace:
        self.calls.append(kwargs)
        return next(self.responses)


def fake_client(*responses: SimpleNamespace) -> SimpleNamespace:
    return SimpleNamespace(messages=FakeMessages(list(responses)))


def test_tool_blocks_drive_the_loop_even_when_stop_metadata_disagrees(monkeypatch) -> None:
    s01 = load_s01(monkeypatch)
    s01.client = fake_client(
        response(tool_block("call_1", "pwd"), stop_reason="end_turn"),
        response(text_block("done"), stop_reason="end_turn"),
    )
    monkeypatch.setattr(s01, "run_bash", lambda command: f"ran: {command}")
    messages = [{"role": "user", "content": "where am I?"}]

    result = s01.agent_loop(messages, max_turns=3)

    assert result.stop_reason is s01.LoopStopReason.FINAL_ANSWER
    assert result.turns == 2
    assert result.tool_calls == 1
    assert result.final_text == "done"
    assert [message["role"] for message in messages] == ["user", "assistant", "user", "assistant"]
    assert messages[2]["content"][0]["tool_use_id"] == "call_1"


def test_loop_returns_max_tokens_without_hiding_partial_text(monkeypatch) -> None:
    s01 = load_s01(monkeypatch)
    s01.client = fake_client(response(text_block("partial"), stop_reason="max_tokens"))

    result = s01.agent_loop([{"role": "user", "content": "explain"}])

    assert result.stop_reason is s01.LoopStopReason.MAX_TOKENS
    assert result.final_text == "partial"
    assert result.provider_stop_reason == "max_tokens"


def test_loop_stops_at_turn_budget_after_preserving_tool_results(monkeypatch) -> None:
    s01 = load_s01(monkeypatch)
    s01.client = fake_client(response(tool_block("call_1", "pwd"), stop_reason="tool_use"))
    monkeypatch.setattr(s01, "run_bash", lambda command: "/workspace")
    messages = [{"role": "user", "content": "where am I?"}]

    result = s01.agent_loop(messages, max_turns=1)

    assert result.stop_reason is s01.LoopStopReason.MAX_TURNS
    assert result.turns == 1
    assert result.tool_calls == 1
    assert messages[-1]["content"][0]["content"] == "/workspace"
