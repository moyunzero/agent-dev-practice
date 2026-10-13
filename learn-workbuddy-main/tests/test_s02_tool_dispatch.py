"""Behavior tests for s02's single-source tool dispatch boundary."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest


ROOT = Path(__file__).resolve().parents[1]


def load_s02(monkeypatch):
    """Import the standalone lesson with the offline Anthropic stub."""

    stub_dir = ROOT / "tests" / "stubs"
    monkeypatch.syspath_prepend(str(stub_dir))
    monkeypatch.setenv("MODEL_ID", "offline-test-model")
    saved_anthropic = sys.modules.pop("anthropic", None)

    module_name = "s02_tool_dispatch_test_module"
    spec = importlib.util.spec_from_file_location(module_name, ROOT / "s02_tool_dispatch" / "code.py")
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[module_name] = module
    try:
        spec.loader.exec_module(module)
    finally:
        sys.modules.pop("anthropic", None)
        if saved_anthropic is not None:
            sys.modules["anthropic"] = saved_anthropic
    return module


def test_registry_is_the_only_source_for_schema_and_handler(monkeypatch) -> None:
    s02 = load_s02(monkeypatch)
    registry = s02.ToolRegistry()
    calls: list[str] = []
    source_schema = s02.object_schema({"text": {"type": "string"}}, ["text"])
    spec = s02.ToolSpec(
        name="echo",
        description="Echo text.",
        input_schema=source_schema,
        handler=lambda text: calls.append(text) or text,
    )
    registry.register(spec)

    source_schema["required"].clear()
    schemas = registry.model_schemas()
    assert schemas[0]["input_schema"]["required"] == ["text"]
    schemas[0]["input_schema"]["required"].clear()
    result = registry.dispatch(s02.ToolCall("call_1", "echo", {"text": "hello"}))

    assert result.ok
    assert result.content == "hello"
    assert calls == ["hello"]
    assert registry.model_schemas()[0]["input_schema"]["required"] == ["text"]
    with pytest.raises(ValueError, match="duplicate tool name"):
        registry.register(spec)


@pytest.mark.parametrize(
    ("arguments", "message"),
    [
        ({}, "missing required argument"),
        ({"count": "two"}, "must be integer"),
        ({"count": 2, "extra": True}, "unknown argument"),
        ([2], "must be an object"),
    ],
)
def test_invalid_arguments_are_returned_without_calling_handler(
    monkeypatch,
    arguments: Any,
    message: str,
) -> None:
    s02 = load_s02(monkeypatch)
    called = False

    def handler(count: int) -> str:
        nonlocal called
        called = True
        return str(count)

    registry = s02.ToolRegistry()
    registry.register(
        s02.ToolSpec(
            name="count",
            description="Count.",
            input_schema=s02.object_schema({"count": {"type": "integer"}}, ["count"]),
            handler=handler,
        )
    )

    result = registry.dispatch(s02.ToolCall("call_1", "count", arguments))

    assert result.error_code is s02.ToolErrorCode.INVALID_ARGUMENTS
    assert message in result.content
    assert result.to_protocol_block()["is_error"] is True
    assert called is False


def test_unknown_tools_and_handler_exceptions_become_structured_errors(monkeypatch) -> None:
    s02 = load_s02(monkeypatch)
    registry = s02.ToolRegistry()
    registry.register(
        s02.ToolSpec(
            name="explode",
            description="Raise an error.",
            input_schema=s02.object_schema({}, []),
            handler=lambda: (_ for _ in ()).throw(RuntimeError("boom")),
        )
    )

    unknown = registry.dispatch(s02.ToolCall("call_1", "missing", {}))
    failed = registry.dispatch(s02.ToolCall("call_2", "explode", {}))

    assert unknown.error_code is s02.ToolErrorCode.UNKNOWN_TOOL
    assert failed.error_code is s02.ToolErrorCode.EXECUTION_ERROR
    assert failed.content.endswith("boom")


def test_mutating_batch_takes_conservative_serial_path(monkeypatch) -> None:
    s02 = load_s02(monkeypatch)
    events: list[str] = []
    registry = s02.ToolRegistry()
    schema = s02.object_schema({"value": {"type": "string"}}, ["value"])
    registry.register(
        s02.ToolSpec("write", "Write.", schema, lambda value: events.append(f"write:{value}") or value)
    )
    registry.register(
        s02.ToolSpec(
            "read",
            "Read.",
            schema,
            lambda value: events.append(f"read:{value}") or value,
            concurrent_safe=True,
        )
    )

    results = registry.dispatch_many(
        [
            s02.ToolCall("call_1", "write", {"value": "a"}),
            s02.ToolCall("call_2", "read", {"value": "b"}),
        ]
    )

    assert events == ["write:a", "read:b"]
    assert [result.call.tool_use_id for result in results] == ["call_1", "call_2"]


def test_workspace_path_guard_is_preserved(monkeypatch, tmp_path: Path) -> None:
    s02 = load_s02(monkeypatch)
    monkeypatch.setattr(s02, "WORKDIR", tmp_path.resolve())

    assert s02.safe_path("notes/today.md") == tmp_path / "notes" / "today.md"
    with pytest.raises(ValueError, match="escapes workspace"):
        s02.safe_path("../outside.txt")


def test_bash_uses_workspace_scoped_environment(monkeypatch, tmp_path: Path) -> None:
    """The standalone lesson teaches the same subprocess boundary as the mini harness."""

    s02 = load_s02(monkeypatch)
    monkeypatch.setattr(s02, "WORKDIR", tmp_path.resolve())
    monkeypatch.setenv("OPENAI_API_KEY", "openai-secret")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "anthropic-secret")
    monkeypatch.setenv("SSH_AUTH_SOCK", "/tmp/private-agent.sock")
    monkeypatch.setenv("WORKBUDDY_TEST_SECRET", "parent-only")
    command = (
        "printf '%s\\n%s\\n%s\\n%s\\n%s\\n' "
        '"${OPENAI_API_KEY-unset}" "${ANTHROPIC_API_KEY-unset}" '
        '"${SSH_AUTH_SOCK-unset}" "${WORKBUDDY_TEST_SECRET-unset}" '
        '"$HOME|$PWD|${PATH:+set}"'
    )

    result = s02.run_bash(command)

    assert result.splitlines() == [
        "unset",
        "unset",
        "unset",
        "unset",
        f"{tmp_path.resolve()}|{tmp_path.resolve()}|set",
    ]


def test_agent_loop_advertises_and_executes_the_same_registry(monkeypatch) -> None:
    s02 = load_s02(monkeypatch)
    registry = s02.ToolRegistry()
    registry.register(
        s02.ToolSpec(
            name="echo",
            description="Echo text.",
            input_schema=s02.object_schema({"text": {"type": "string"}}, ["text"]),
            handler=lambda text: text.upper(),
        )
    )
    responses = iter(
        [
            SimpleNamespace(
                content=[
                    SimpleNamespace(
                        type="tool_use",
                        id="call_1",
                        name="echo",
                        input={"text": "hello"},
                    )
                ],
                stop_reason="tool_use",
            ),
            SimpleNamespace(
                content=[SimpleNamespace(type="text", text="done")],
                stop_reason="end_turn",
            ),
        ]
    )
    requests: list[dict[str, Any]] = []

    def create(**kwargs: Any) -> SimpleNamespace:
        requests.append(kwargs)
        return next(responses)

    s02.client = SimpleNamespace(messages=SimpleNamespace(create=create))
    messages = [{"role": "user", "content": "echo hello"}]

    result = s02.agent_loop(messages, registry=registry, max_turns=3)

    assert result.stop_reason is s02.LoopStopReason.FINAL_ANSWER
    assert result.tool_calls == 1
    assert requests[0]["tools"] == registry.model_schemas()
    assert messages[2]["content"] == [
        {"type": "tool_result", "tool_use_id": "call_1", "content": "HELLO"}
    ]
