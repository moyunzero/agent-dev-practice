"""Offline contracts for S08's isolated memory-selector route."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def s08():
    module_name = "s08_model_routing_contract_test_module"
    spec = importlib.util.spec_from_file_location(
        module_name,
        ROOT / "s08_model_routing" / "code.py",
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[module_name] = module
    try:
        spec.loader.exec_module(module)
        module.DEMO_SLEEP_SCALE = 0
        yield module
    finally:
        sys.modules.pop(module_name, None)


def _request(s08, *, limit: int = 2):
    return s08.MemorySelectionRequest(
        query="previous login decision",
        candidates=(
            s08.MemoryCandidate("mem_auth", "Login token expiry decision."),
            s08.MemoryCandidate("mem_ui", "Compact settings layout preference."),
            s08.MemoryCandidate("mem_ci", "CI runs the offline verification suite."),
        ),
        limit=limit,
    )


def test_memory_selector_route_is_lite_and_zero_tool(s08) -> None:
    selector = s08.MemorySelectorRouter(s08.ModelRouter())

    route = selector.route()

    assert route.model.tier is s08.ModelTier.LITE
    assert route.tools == ()
    assert route.temperature == 0
    assert route.max_output_tokens == 256


def test_memory_selector_rejects_tool_schemas_before_model_call(s08) -> None:
    router = s08.ModelRouter()
    selector = s08.MemorySelectorRouter(router)

    with pytest.raises(ValueError, match="zero-tool"):
        selector.select(
            _request(s08),
            tool_schemas=({"name": "read_file"},),
        )

    assert sum(router.tracker.calls.values()) == 0


def test_selector_output_is_id_only_allowlisted_and_bounded(
    s08,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    router = s08.ModelRouter()
    selector = s08.MemorySelectorRouter(router)
    monkeypatch.setattr(
        s08,
        "mock_llm",
        lambda _model, _prompt, _task="": (
            "[mem_ui]\n[unknown]\n[mem_ui]\n[mem_auth]\n[mem_ci]"
        ),
    )

    result = selector.select(_request(s08, limit=2), token_override=400)

    assert result.selected_ids == ("mem_ui", "mem_auth")
    assert result.considered_ids == ("mem_auth", "mem_ui", "mem_ci")
    assert router.tracker.calls[s08.ModelTier.LITE] == 1
    assert router.tracker.tokens[s08.ModelTier.LITE] == 400


def test_generic_agent_call_cannot_bypass_selector_contract(s08) -> None:
    router = s08.ModelRouter()

    with pytest.raises(ValueError, match="MemorySelectorRouter.select"):
        router.call("memorySelector", "unbounded prompt")

    assert router.call("general-purpose", "plan the task", task="plan").startswith(
        "Plan:"
    )


@pytest.mark.parametrize(
    ("query", "candidate_ids", "limit", "error"),
    [
        ("  ", ("mem_1",), 1, "query"),
        ("query", ("mem_1",), 0, "limit"),
        ("query", ("mem_1", "mem_1"), 1, "unique"),
    ],
)
def test_memory_selection_request_rejects_ambiguous_inputs(
    s08,
    query: str,
    candidate_ids: tuple[str, ...],
    limit: int,
    error: str,
) -> None:
    candidates = tuple(
        s08.MemoryCandidate(memory_id, f"content for {memory_id}")
        for memory_id in candidate_ids
    )

    with pytest.raises(ValueError, match=error):
        s08.MemorySelectionRequest(query, candidates, limit)
