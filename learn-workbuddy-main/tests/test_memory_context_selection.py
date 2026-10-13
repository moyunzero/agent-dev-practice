"""Offline contracts for s15's memory selection and context packing path."""

from __future__ import annotations

import importlib.util
import os
import sys
from itertools import permutations
from pathlib import Path
from types import SimpleNamespace

import pytest


ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def s14():
    module_name = "s14_retrieval_evidence_test_module"
    spec = importlib.util.spec_from_file_location(
        module_name, ROOT / "s14_context_compact" / "code.py"
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    yield module
    sys.modules.pop(module_name, None)


@pytest.fixture(scope="module")
def s15(tmp_path_factory: pytest.TempPathFactory):
    stub_dir = ROOT / "tests" / "stubs"
    state_root = tmp_path_factory.mktemp("s15-memory-selection-state")
    sys.path.insert(0, str(stub_dir))
    saved_anthropic = sys.modules.pop("anthropic", None)
    old_model = os.environ.get("MODEL_ID")
    old_home = os.environ.get("WORKBUDDY_HOME")
    os.environ["MODEL_ID"] = "offline-test-model"
    os.environ["WORKBUDDY_HOME"] = str(state_root)
    module_name = "s15_memory_selection_test_module"
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


def candidate(
    s15,
    memory_id: str,
    text: str,
    *,
    score: float = 0.8,
    user_scope: str = "scope-a",
    source_rank: int = 1,
    captured_at: str = "2026-08-17T08:00:00Z",
    conflict_key: str | None = None,
    authority: str = "user_default",
):
    return s15.MemoryContextCandidate(
        memory_id=memory_id,
        text=text,
        user_scope=user_scope,
        score=score,
        source_rank=source_rank,
        provenance=s15.MemoryContextProvenance(
            source_id=f"source-{memory_id}",
            source_type="conversation",
            title=f"Memory {memory_id}",
            captured_at=captured_at,
        ),
        conflict_key=conflict_key,
        authority=authority,
    )


def decision_by_id(plan):
    return {decision.memory_id: decision for decision in plan.decisions}


def test_scope_and_confidence_are_gates_before_prompt_context(s15) -> None:
    candidates = [
        candidate(s15, "selected", "Keep the release checklist", score=0.91),
        candidate(
            s15,
            "cross-scope",
            "Private data from another user",
            score=0.99,
            user_scope="scope-b",
        ),
        candidate(s15, "low", "Weak lexical coincidence", score=0.39),
    ]

    plan = s15.select_memory_context(
        candidates,
        user_scope="scope-a",
        policy=s15.MemorySelectionPolicy(min_score=0.4),
    )
    decisions = decision_by_id(plan)

    assert plan.selected_memory_ids == ("selected",)
    assert "Private data" not in plan.context
    assert "Weak lexical" not in plan.context
    assert decisions["cross-scope"].reason is s15.MemoryDecisionReason.SCOPE_MISMATCH
    assert decisions["low"].reason is s15.MemoryDecisionReason.LOW_CONFIDENCE


def test_deduplication_and_conflict_resolution_are_stable(s15) -> None:
    winner = candidate(
        s15,
        "python-new",
        "Prefer Python for automation",
        score=0.95,
        conflict_key="preference:automation-language",
    )
    duplicate = candidate(
        s15,
        "python-copy",
        "  prefer  PYTHON for automation  ",
        score=0.80,
        source_rank=2,
        conflict_key="preference:automation-language",
    )
    conflict = candidate(
        s15,
        "typescript-old",
        "Prefer TypeScript for automation",
        score=0.70,
        source_rank=3,
        conflict_key="preference:automation-language",
    )
    independent = candidate(
        s15,
        "timezone",
        "Use Asia/Shanghai timezone",
        score=0.85,
        conflict_key="preference:timezone",
    )
    policy = s15.MemorySelectionPolicy(min_score=0.1, top_k=5)

    forward = s15.select_memory_context(
        [winner, duplicate, conflict, independent],
        user_scope="scope-a",
        policy=policy,
    )
    reverse = s15.select_memory_context(
        [independent, conflict, duplicate, winner],
        user_scope="scope-a",
        policy=policy,
    )
    decisions = decision_by_id(forward)

    assert forward.context == reverse.context
    assert forward.selected_memory_ids == ("python-new", "timezone")
    assert decisions["python-copy"].reason is s15.MemoryDecisionReason.DUPLICATE_CONTENT
    assert decisions["python-copy"].related_memory_id == "python-new"
    assert decisions["typescript-old"].reason is s15.MemoryDecisionReason.CONFLICT_LOSER
    assert decisions["typescript-old"].related_memory_id == "python-new"


@pytest.mark.parametrize("first_slot", [None, "preference:analysis-language"])
def test_deduplication_preserves_other_slots_for_conflict_resolution(
    s15, first_slot: str | None,
) -> None:
    current = candidate(
        s15, "current-python", "Use Python", conflict_key=first_slot,
        authority="current_turn",
    )
    workspace = candidate(
        s15, "workspace-python", "Use Python",
        conflict_key="preference:automation-language", authority="workspace_override",
    )
    default = candidate(
        s15, "old-bash", "Use Bash",
        conflict_key="preference:automation-language", authority="user_default",
    )
    policy = s15.MemorySelectionPolicy(max_chars=None, max_tokens=None)
    plans = [
        s15.select_memory_context(order, user_scope="scope-a", policy=policy)
        for order in permutations([current, workspace, default])
    ]

    for plan in plans:
        assert plan.selected_memory_ids == ("current-python", "workspace-python")
        decisions = decision_by_id(plan)
        assert decisions["old-bash"].reason is s15.MemoryDecisionReason.AUTHORITY_LOSER
        assert decisions["old-bash"].related_memory_id == "workspace-python"
        assert "Use Bash" not in plan.context
        assert plan.context == plans[0].context
        assert plan.decisions == plans[0].decisions


@pytest.mark.parametrize(
    "winner_slot, duplicate_slot",
    [
        (None, None),
        ("preference:language", "preference:language"),
        ("preference:language", "  ＰＲＥＦＥＲＥＮＣＥ：ＬＡＮＧＵＡＧＥ  "),
    ],
)
def test_same_slot_deduplication_normalizes_text_and_slot(
    s15, winner_slot: str | None, duplicate_slot: str | None,
) -> None:
    winner = candidate(
        s15, "winner", "Use Python", conflict_key=winner_slot,
        score=0.5, authority="workspace_override",
    )
    duplicate = candidate(
        s15, "duplicate", "  ＵＳＥ   ＰＹＴＨＯＮ  ", conflict_key=duplicate_slot,
        score=0.99, authority="user_default",
    )
    for order in permutations([winner, duplicate]):
        plan = s15.select_memory_context(order, user_scope="scope-a")
        assert plan.selected_memory_ids == ("winner",)
        rejected = decision_by_id(plan)["duplicate"]
        assert rejected.reason is s15.MemoryDecisionReason.DUPLICATE_CONTENT
        assert rejected.related_memory_id == "winner"


def test_cross_slot_duplicate_does_not_backfill_superseded_fact_under_budget(s15) -> None:
    current = candidate(
        s15, "current", "Use Python", authority="current_turn",
    )
    workspace = candidate(
        s15, "workspace", "Use Python", authority="workspace_override",
        conflict_key="preference:automation-language",
    )
    default = candidate(
        s15, "default", "Bash", authority="user_default",
        conflict_key="preference:automation-language",
    )
    # The cheaper default would fit beside current, but it has already lost
    # its fact slot. Budget packing must not resurrect a superseded preference.
    char_budget = len(s15.render_memory_context("scope-a", [current, default]))
    assert len(s15.render_memory_context("scope-a", [current, workspace])) > char_budget
    plan = s15.select_memory_context(
        [default, workspace, current], user_scope="scope-a",
        policy=s15.MemorySelectionPolicy(max_chars=char_budget, max_tokens=None),
    )
    assert plan.selected_memory_ids == ("current",)
    decisions = decision_by_id(plan)
    assert decisions["workspace"].reason is s15.MemoryDecisionReason.CHAR_BUDGET_EXCEEDED
    assert decisions["default"].reason is s15.MemoryDecisionReason.AUTHORITY_LOSER
    assert decisions["default"].related_memory_id == "workspace"


def test_authority_precedes_score_rank_time_and_input_order(s15) -> None:
    conflict_key = "preference:automation-language"
    user_default = candidate(
        s15,
        "python-default",
        "Prefer Python for automation",
        score=0.99,
        source_rank=1,
        captured_at="2026-08-19T10:00:00Z",
        conflict_key=conflict_key,
        authority="user_default",
    )
    workspace = candidate(
        s15,
        "typescript-workspace",
        "Use TypeScript in this workspace",
        score=0.80,
        source_rank=2,
        captured_at="2026-08-18T10:00:00Z",
        conflict_key=conflict_key,
        authority="workspace_override",
    )
    current_turn = candidate(
        s15,
        "go-current-turn",
        "For this turn, use Go",
        score=0.41,
        source_rank=3,
        captured_at="2026-08-17T10:00:00Z",
        conflict_key=conflict_key,
        authority="current_turn",
    )
    policy = s15.MemorySelectionPolicy(min_score=0.4, top_k=3)

    forward = s15.select_memory_context(
        [user_default, workspace, current_turn],
        user_scope="scope-a",
        policy=policy,
    )
    reverse = s15.select_memory_context(
        [current_turn, workspace, user_default],
        user_scope="scope-a",
        policy=policy,
    )
    decisions = decision_by_id(forward)

    assert forward.context == reverse.context
    assert forward.selected_memory_ids == ("go-current-turn",)
    assert 'authority="current_turn"' in forward.context
    assert decisions["typescript-workspace"].reason is (
        s15.MemoryDecisionReason.AUTHORITY_LOSER
    )
    assert decisions["python-default"].reason is (
        s15.MemoryDecisionReason.AUTHORITY_LOSER
    )
    assert decisions["python-default"].related_memory_id == "go-current-turn"
    assert "user_default lost to current_turn" in decisions["python-default"].detail


def test_authority_orders_independent_candidates_under_top_k(s15) -> None:
    high_score_default = candidate(
        s15,
        "high-score-default",
        "Default answer style",
        score=0.99,
        conflict_key="preference:style",
    )
    current_turn = candidate(
        s15,
        "current-turn-format",
        "Use a table for this answer",
        score=0.50,
        conflict_key="preference:format",
        authority="current_turn",
    )

    plan = s15.select_memory_context(
        [high_score_default, current_turn],
        user_scope="scope-a",
        policy=s15.MemorySelectionPolicy(min_score=0.1, top_k=1),
    )
    decisions = decision_by_id(plan)

    assert plan.selected_memory_ids == ("current-turn-format",)
    assert decisions["high-score-default"].reason is (
        s15.MemoryDecisionReason.TOP_K_REACHED
    )


def test_authority_never_bypasses_scope_or_confidence_gates(s15) -> None:
    cross_scope = candidate(
        s15,
        "cross-scope-current",
        "Private current-turn instruction",
        score=1.0,
        user_scope="scope-b",
        authority="current_turn",
    )
    low_confidence = candidate(
        s15,
        "weak-current",
        "Uncertain current-turn extraction",
        score=0.2,
        authority="current_turn",
    )

    plan = s15.select_memory_context(
        [cross_scope, low_confidence],
        user_scope="scope-a",
        policy=s15.MemorySelectionPolicy(min_score=0.4),
    )
    decisions = decision_by_id(plan)

    assert plan.selected_memory_ids == ()
    assert decisions["cross-scope-current"].reason is (
        s15.MemoryDecisionReason.SCOPE_MISMATCH
    )
    assert decisions["weak-current"].reason is s15.MemoryDecisionReason.LOW_CONFIDENCE


def test_character_budget_skips_oversized_hit_and_backfills_until_top_k(s15) -> None:
    oversized = candidate(s15, "oversized", "X" * 1_000, score=0.99)
    second = candidate(s15, "second", "Short useful memory", score=0.90)
    third = candidate(s15, "third", "Another useful memory", score=0.80)
    fourth = candidate(s15, "fourth", "Outside top k", score=0.70)
    two_small = s15.render_memory_context("scope-a", [second, third])

    plan = s15.select_memory_context(
        [fourth, oversized, third, second],
        user_scope="scope-a",
        policy=s15.MemorySelectionPolicy(
            min_score=0.1,
            top_k=2,
            max_chars=len(two_small),
            max_tokens=10_000,
        ),
    )
    decisions = decision_by_id(plan)

    assert plan.context == two_small
    assert plan.selected_memory_ids == ("second", "third")
    assert decisions["oversized"].reason is s15.MemoryDecisionReason.CHAR_BUDGET_EXCEEDED
    assert decisions["fourth"].reason is s15.MemoryDecisionReason.TOP_K_REACHED
    assert plan.used_chars == len(plan.context)


def test_injected_token_counter_enforces_target_model_budget(s15) -> None:
    expensive = candidate(s15, "expensive", "TOKEN TOKEN TOKEN", score=0.9)
    compact = candidate(s15, "compact", "TOKEN", score=0.8)

    plan = s15.select_memory_context(
        [expensive, compact],
        user_scope="scope-a",
        policy=s15.MemorySelectionPolicy(
            min_score=0.1,
            top_k=2,
            max_chars=10_000,
            max_tokens=1,
        ),
        token_counter=lambda text: text.count("TOKEN"),
    )
    decisions = decision_by_id(plan)

    assert plan.selected_memory_ids == ("compact",)
    assert decisions["expensive"].reason is s15.MemoryDecisionReason.TOKEN_BUDGET_EXCEEDED
    assert plan.used_tokens == 1


def test_recall_adapter_preserves_scope_score_rank_and_provenance(s15) -> None:
    result = SimpleNamespace(
        query=SimpleNamespace(user_scope="scope-a"),
        hits=(
            SimpleNamespace(
                memory_id="memory-1",
                snippet="Use source-grounded answers",
                rank=2,
                scope=SimpleNamespace(user_scope="scope-a"),
                provenance=SimpleNamespace(
                    source_id="transcript-7",
                    source_type="transcript",
                    title="Confirmed preference",
                    captured_at="2026-08-16T09:00:00Z",
                ),
                score_breakdown=SimpleNamespace(total=0.87),
            ),
        ),
    )

    converted = s15.memory_candidates_from_recall(
        result,
        conflict_keys={"memory-1": "preference:grounding"},
        authority_by_memory_id={"memory-1": "workspace_override"},
    )

    assert converted == (
        s15.MemoryContextCandidate(
            memory_id="memory-1",
            text="Use source-grounded answers",
            user_scope="scope-a",
            score=0.87,
            source_rank=2,
            provenance=s15.MemoryContextProvenance(
                source_id="transcript-7",
                source_type="transcript",
                title="Confirmed preference",
                captured_at="2026-08-16T09:00:00Z",
            ),
            conflict_key="preference:grounding",
            authority=s15.PreferenceAuthority.WORKSPACE_OVERRIDE,
        ),
    )
    defaulted = s15.memory_candidates_from_recall(
        result,
        conflict_keys={"memory-1": "preference:grounding"},
    )
    assert defaulted[0].authority is s15.PreferenceAuthority.USER_DEFAULT


def test_unknown_authority_fails_closed(s15) -> None:
    with pytest.raises(ValueError, match="memory authority must be one of"):
        candidate(
            s15,
            "invented-authority",
            "An untrusted caller cannot invent a higher tier",
            authority="system_override",
        )


def test_required_harness_rules_are_not_part_of_preference_precedence(s15) -> None:
    current_turn = candidate(
        s15,
        "current-turn",
        "Use a concise response for this turn",
        score=1.0,
        authority="current_turn",
    )
    memory_plan = s15.select_memory_context(
        [current_turn],
        user_scope="scope-a",
        policy=s15.MemorySelectionPolicy(min_score=0.1),
    )
    safety = s15.PromptSegment(
        "safety", lambda: "HARNESS SAFETY", required=True, priority=10
    )
    preferences = s15.PromptSegment(
        "preferences",
        lambda: memory_plan.context,
        budget_priority=100,
        priority=20,
    )

    prompt_plan = s15.plan_prompt(
        [preferences, safety], budget_chars=len("HARNESS SAFETY")
    )

    assert prompt_plan.prompt == "HARNESS SAFETY"
    assert prompt_plan.included_names == ("safety",)
    assert prompt_plan.dropped_names == ("preferences",)


def test_selected_memory_evidence_survives_lossy_compaction(
    s14,
    s15,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    winner = candidate(
        s15,
        "python-new",
        "Prefer Python for automation",
        score=0.95,
        conflict_key="preference:automation-language",
    )
    loser = candidate(
        s15,
        "typescript-old",
        "Prefer TypeScript for automation",
        score=0.70,
        source_rank=2,
        conflict_key="preference:automation-language",
    )
    plan = s15.select_memory_context(
        [loser, winner],
        user_scope="scope-a",
        policy=s15.MemorySelectionPolicy(min_score=0.1),
    )
    selected_ids = set(plan.selected_memory_ids)
    selected = [item for item in (loser, winner) if item.memory_id in selected_ids]
    evidence = s14.capture_retrieval_evidence(selected)
    state = s14.DurableContextState(retrieval_evidence=evidence)
    messages = [
        {
            "role": "user" if index % 2 == 0 else "assistant",
            "content": f"turn {index}: " + "disposable detail " * 40,
        }
        for index in range(10)
    ]
    monkeypatch.setattr(s14, "TOKEN_THRESHOLD", 1)

    result = s14.compact_context(
        messages,
        state,
        summarizer=lambda _conversation: "Old memory content was compressed.",
        verbose=False,
    )
    rendered = s14.render_durable_context(result.durable_state)

    assert result.durable_state is state
    assert result.durable_state.retrieval_evidence == evidence
    assert "conversation_summary" in result.applied_layers
    assert evidence == (
        s14.RetrievalEvidence(
            memory_id="python-new",
            source_id="source-python-new",
            source_type="conversation",
            source_title="Memory python-new",
            captured_at="2026-08-17T08:00:00Z",
            score=0.95,
            source_rank=1,
            conflict_key="preference:automation-language",
        ),
    )
    assert "source-python-new" in rendered
    assert "score=0.95" in rendered
    assert "conflict_winner=preference:automation-language" in rendered
    assert "typescript-old" not in rendered


def test_empty_input_is_explicit_and_duplicate_ids_fail_closed(s15) -> None:
    empty = s15.select_memory_context([], user_scope="scope-a")

    assert empty.context == ""
    assert empty.used_chars == 0
    assert empty.used_tokens == 0
    assert empty.decisions == ()

    duplicate = candidate(s15, "same-id", "one")
    with pytest.raises(ValueError, match="duplicate memory candidate ids: same-id"):
        s15.select_memory_context(
            [duplicate, candidate(s15, "same-id", "two")],
            user_scope="scope-a",
        )

    with pytest.raises(ValueError, match="another scope"):
        s15.render_memory_context(
            "scope-a",
            [candidate(s15, "other", "private", user_scope="scope-b")],
        )

    with pytest.raises(ValueError, match="non-negative integer"):
        s15.select_memory_context(
            [candidate(s15, "counter", "context")],
            user_scope="scope-a",
            token_counter=lambda _text: -1,
        )
