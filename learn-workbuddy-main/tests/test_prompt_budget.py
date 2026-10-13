"""Offline contracts for s15's explainable context budget planner."""

from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def s15(tmp_path_factory: pytest.TempPathFactory):
    stub_dir = ROOT / "tests" / "stubs"
    state_root = tmp_path_factory.mktemp("s15-import-state")
    sys.path.insert(0, str(stub_dir))
    saved_anthropic = sys.modules.pop("anthropic", None)
    old_model = os.environ.get("MODEL_ID")
    old_home = os.environ.get("WORKBUDDY_HOME")
    os.environ["MODEL_ID"] = "offline-test-model"
    os.environ["WORKBUDDY_HOME"] = str(state_root)
    module_name = "s15_prompt_budget_test_module"
    try:
        spec = importlib.util.spec_from_file_location(
            module_name, ROOT / "s15_prompt_assembly" / "code.py"
        )
        module = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        sys.modules[module_name] = module
        spec.loader.exec_module(module)
        yield module
    finally:
        sys.path.remove(str(stub_dir))
        sys.modules.pop(module_name, None)
        sys.modules.pop("anthropic", None)
        if saved_anthropic is not None:
            sys.modules["anthropic"] = saved_anthropic
        if old_model is None:
            os.environ.pop("MODEL_ID", None)
        else:
            os.environ["MODEL_ID"] = old_model
        if old_home is None:
            os.environ.pop("WORKBUDDY_HOME", None)
        else:
            os.environ["WORKBUDDY_HOME"] = old_home


def segment(s15, name: str, content: str | None, **kwargs):
    return s15.PromptSegment(name, lambda: content, **kwargs)


def test_required_segments_survive_and_render_in_presentation_order(s15) -> None:
    segments = [
        segment(s15, "mode", "MODE", priority=90, required=True),
        segment(s15, "base", "BASE", priority=10, required=True),
        segment(s15, "optional", "X" * 100, priority=20, budget_priority=100),
    ]
    required_prompt = "BASE" + s15.PROMPT_SEPARATOR + "MODE"

    plan = s15.plan_prompt(segments, budget_chars=len(required_prompt))

    assert plan.prompt == required_prompt
    assert plan.included_names == ("base", "mode")
    assert plan.dropped_names == ("optional",)
    assert plan.used_chars == len(required_prompt)


def test_budget_value_is_distinct_from_presentation_order(s15) -> None:
    segments = [
        segment(s15, "base", "B", priority=10, required=True),
        segment(s15, "low-value-first", "LOW", priority=20, budget_priority=10),
        segment(s15, "high-value-last", "HIGH", priority=80, budget_priority=90),
    ]
    budget = len("B" + s15.PROMPT_SEPARATOR + "HIGH")

    plan = s15.plan_prompt(segments, budget_chars=budget)

    assert plan.prompt == "B" + s15.PROMPT_SEPARATOR + "HIGH"
    assert plan.included_names == ("base", "high-value-last")
    assert plan.dropped_names == ("low-value-first",)


def test_separator_cost_is_part_of_the_budget(s15) -> None:
    segments = [
        segment(s15, "base", "A", required=True),
        segment(s15, "memory", "B", budget_priority=50),
    ]

    plan = s15.plan_prompt(segments, budget_chars=2)

    assert plan.prompt == "A"
    assert plan.dropped_names == ("memory",)


def test_optional_memory_is_atomic_and_reports_provenance(s15) -> None:
    memory = "<memory>trusted project decision</memory>"
    segments = [
        segment(
            s15, "base", "BASE", required=True,
            provenance="harness:base-rules",
        ),
        segment(
            s15, "memory", memory, budget_priority=50,
            provenance="workspace:curated-memory",
        ),
    ]

    plan = s15.plan_prompt(segments, budget_chars=len("BASE"))
    decision = next(item for item in plan.decisions if item.name == "memory")

    assert memory not in plan.prompt
    assert "trusted project" not in plan.prompt
    assert decision.status == "dropped"
    assert decision.rendered_chars == 0
    assert decision.original_chars == len(memory)
    assert decision.provenance == "workspace:curated-memory"
    assert "budget" in decision.reason


def test_inactive_segment_consumes_no_budget(s15) -> None:
    inactive = s15.PromptSegment(
        "expert", lambda: "SHOULD NOT BUILD",
        condition=lambda: False,
        provenance="runtime:expert",
    )

    plan = s15.plan_prompt([inactive], budget_chars=0)

    assert plan.prompt == ""
    assert plan.decisions[0].status == "inactive"
    assert plan.decisions[0].provenance == "runtime:expert"


def test_impossible_required_budget_fails_loudly(s15) -> None:
    segments = [segment(s15, "base", "SAFETY", required=True)]

    with pytest.raises(s15.PromptBudgetError, match="required prompt segments need"):
        s15.plan_prompt(segments, budget_chars=1)


def test_duplicate_segment_names_are_rejected(s15) -> None:
    segments = [
        segment(s15, "memory", "FIRST"),
        segment(s15, "memory", "SECOND"),
    ]

    with pytest.raises(ValueError, match="duplicate prompt segment names: memory"):
        s15.plan_prompt(segments, budget_chars=None)


def test_unbounded_plan_preserves_backwards_compatible_assembly(s15) -> None:
    segments = [
        segment(s15, "second", "SECOND", priority=20, budget_priority=1),
        segment(s15, "first", "FIRST", priority=10, budget_priority=1),
    ]

    plan = s15.plan_prompt(segments, budget_chars=None)

    assert plan.prompt == "FIRST" + s15.PROMPT_SEPARATOR + "SECOND"
    assert plan.dropped_names == ()


def test_runtime_assembly_uses_configured_budget_and_exposes_last_plan(
    s15, monkeypatch: pytest.MonkeyPatch,
) -> None:
    segments = [
        segment(s15, "base", "BASE", required=True),
        segment(s15, "optional", "OPTIONAL", budget_priority=1),
    ]
    monkeypatch.setattr(s15, "SEGMENTS", segments)
    monkeypatch.setattr(s15, "PROMPT_BUDGET_CHARS", len("BASE"))

    prompt = s15.assemble_system_prompt()

    assert prompt == "BASE"
    assert s15.LAST_PROMPT_PLAN is not None
    assert s15.LAST_PROMPT_PLAN.dropped_names == ("optional",)
