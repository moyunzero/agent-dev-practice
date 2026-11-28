#!/usr/bin/env python3
"""s15_prompt_assembly - select, pack, and assemble runtime context.

The system prompt is not a static string. The harness builds independently
owned segments, gives required rules priority over optional context, and emits
an audit trail for every include/drop decision.

Memory needs one extra boundary before it becomes a prompt segment. S12 returns
ranked, query-scoped recall hits; S15 decides which of those hits are safe and
useful enough to enter the current context:

    RecallHit -> scope -> confidence -> authority -> dedupe/conflict
              -> top-k/budget -> <recalled_memory> -> total prompt planner

The selector never writes back to durable memory and never guesses semantic
conflicts from prose. Callers attach an explicit ``conflict_key`` when several
records describe the same fact slot. Character and token budgets are both
observable; an injected target-model token counter can replace the deterministic
offline estimator without changing the selection contract.

The remaining runtime segments preserve the chapter's original teaching scope:
base rules, identity, recalled memory, project context, tools, expert, skills,
connectors, regional conventions, and working mode. State changes trigger
reassembly, while the offline planners remain importable without an API key.

Usage:
    python s15_prompt_assembly/code.py --demo
    python s15_prompt_assembly/code.py
"""

from __future__ import annotations


# Machine-readable learning path metadata. Tests enforce that every chapter
# declares both the inherited boundary and the new mechanism taught here.
PROGRESSION = {
    "chapter": "s15_prompt_assembly",
    "builds_on": ["s14_context_compact"],
    "adds": [
        "scope- and confidence-gated memory selection",
        "explicit current-turn, workspace, and user-default precedence",
        "stable deduplication and explicit conflict resolution",
        "top-k character/token context packing",
        "per-candidate selection and rejection decisions",
        "runtime prompt segments and total prompt budget",
    ],
    "preserves": [
        "s12 recall scope, score, rank, and provenance",
        "memory and compaction inputs",
    ],
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
# Prompt selection is intentionally reusable by the full-tour runtime.  Do not
# let an import parse the caller's CLI; only this chapter's executable owns its
# ``--provider`` argument.
if __name__ == "__main__":
    _wb_prepare_chapter_provider()
import html
import math
import os
import re
import unicodedata
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Callable, Mapping, Sequence

try:
    import readline
    readline.parse_and_bind('set bind-tty-special-chars off')
    readline.parse_and_bind('set input-meta on')
    readline.parse_and_bind('set output-meta on')
    readline.parse_and_bind('set convert-meta off')
except ImportError:
    pass

try:
    from dotenv import load_dotenv
except ImportError:
    # PromptSegment / plan_prompt 是纯标准库契约。只有在线 agent loop 才
    # 需要 provider 依赖，离线组合方不应为了 import 规划器而安装 dotenv。
    def load_dotenv(*_args, **_kwargs):
        return False
from mini_workbuddy.paths import tutorial_workbuddy_home

DEFAULT_PROMPT_BUDGET_CHARS = 12_000
DEFAULT_MEMORY_BUDGET_CHARS = 3_000
DEFAULT_MEMORY_BUDGET_TOKENS = 800

load_dotenv(override=True)
if os.getenv("ANTHROPIC_BASE_URL"): os.environ.pop("ANTHROPIC_AUTH_TOKEN", None)


def _prompt_budget_from_env() -> int:
    raw = os.environ.get("PROMPT_BUDGET_CHARS", str(DEFAULT_PROMPT_BUDGET_CHARS))
    try:
        budget = int(raw)
    except ValueError as exc:
        raise SystemExit("PROMPT_BUDGET_CHARS must be a non-negative integer") from exc
    if budget < 0:
        raise SystemExit("PROMPT_BUDGET_CHARS must be a non-negative integer")
    return budget

WORKDIR = Path.cwd()
PROMPT_BUDGET_CHARS = _prompt_budget_from_env()


def runtime_client():
    """只在在线 agent loop 真正启动时构造 provider client。"""
    model = os.environ.get("MODEL_ID")
    if not model:
        raise SystemExit(
            "MODEL_ID is not set. Copy .env.example to .env and fill in "
            "ANTHROPIC_API_KEY and MODEL_ID (see README quick start)."
        )
    try:
        from anthropic import Anthropic
    except ImportError as exc:
        raise SystemExit(
            "anthropic is required for the online agent loop; "
            "install requirements.txt first"
        ) from exc
    return Anthropic(base_url=os.getenv("ANTHROPIC_BASE_URL")), model


# ======================================================================
# Recalled memory selection and context packing
# ======================================================================


class MemoryDecisionStatus(str, Enum):
    """Whether a recalled candidate entered the rendered context."""

    SELECTED = "selected"
    REJECTED = "rejected"


class MemoryDecisionReason(str, Enum):
    """Stable reason codes for traces, tests, and offline evaluation."""

    SELECTED = "selected"
    SCOPE_MISMATCH = "scope_mismatch"
    LOW_CONFIDENCE = "low_confidence"
    DUPLICATE_CONTENT = "duplicate_content"
    AUTHORITY_LOSER = "authority_loser"
    CONFLICT_LOSER = "conflict_loser"
    TOP_K_REACHED = "top_k_reached"
    CHAR_BUDGET_EXCEEDED = "char_budget_exceeded"
    TOKEN_BUDGET_EXCEEDED = "token_budget_exceeded"


class PreferenceAuthority(str, Enum):
    """Who supplied a preference, ordered by authority at the current turn.

    Harness-required safety rules deliberately do not appear here. They remain
    required ``PromptSegment`` objects and cannot be overridden by any memory
    or user-preference candidate.
    """

    CURRENT_TURN = "current_turn"
    WORKSPACE_OVERRIDE = "workspace_override"
    USER_DEFAULT = "user_default"


_PREFERENCE_AUTHORITY_PRIORITY = {
    PreferenceAuthority.CURRENT_TURN: 3,
    PreferenceAuthority.WORKSPACE_OVERRIDE: 2,
    PreferenceAuthority.USER_DEFAULT: 1,
}


def _preference_authority(value: object) -> PreferenceAuthority:
    """Normalize a boundary value and reject invented authority levels."""

    if isinstance(value, PreferenceAuthority):
        return value
    try:
        return PreferenceAuthority(str(value).strip())
    except ValueError as exc:
        allowed = ", ".join(item.value for item in PreferenceAuthority)
        raise ValueError(f"memory authority must be one of: {allowed}") from exc


def _required_text(value: object, *, field_name: str) -> str:
    text = str(value).strip()
    if not text:
        raise ValueError(f"{field_name} must not be empty")
    return text


def _parse_utc_timestamp(value: str) -> datetime:
    """Parse one provenance time so ranking never falls back to string order."""

    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"invalid captured_at timestamp: {value!r}") from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _normalized_memory_text(value: str) -> str:
    """Create a deterministic exact-content key without claiming semantics."""

    normalized = unicodedata.normalize("NFKC", value).casefold()
    return re.sub(r"\s+", " ", normalized).strip()


@dataclass(frozen=True)
class MemoryContextProvenance:
    """Source evidence that must survive the recall-to-prompt projection."""

    source_id: str
    source_type: str
    title: str
    captured_at: str

    def __post_init__(self) -> None:
        _required_text(self.source_id, field_name="provenance source_id")
        _required_text(self.source_type, field_name="provenance source_type")
        _required_text(self.title, field_name="provenance title")
        _parse_utc_timestamp(self.captured_at)


@dataclass(frozen=True)
class MemoryContextCandidate:
    """A query-scoped recall hit projected into S15's selection contract.

    ``conflict_key`` is deliberately explicit. Detecting contradictions from
    arbitrary prose would hide a second model call inside prompt assembly; a
    typed fact producer can instead mark records that compete for one slot.
    """

    memory_id: str
    text: str
    user_scope: str
    score: float
    source_rank: int
    provenance: MemoryContextProvenance
    conflict_key: str | None = None
    authority: PreferenceAuthority = PreferenceAuthority.USER_DEFAULT

    def __post_init__(self) -> None:
        _required_text(self.memory_id, field_name="memory_id")
        _required_text(self.text, field_name="memory text")
        _required_text(self.user_scope, field_name="memory user_scope")
        if not math.isfinite(self.score) or not 0.0 <= self.score <= 1.0:
            raise ValueError("memory score must be finite and between 0 and 1")
        if self.source_rank < 1:
            raise ValueError("memory source_rank must be positive")
        if self.conflict_key is not None:
            _required_text(self.conflict_key, field_name="memory conflict_key")
        object.__setattr__(self, "authority", _preference_authority(self.authority))


@dataclass(frozen=True)
class MemorySelectionPolicy:
    """Selection gates and the memory-specific slice of context budget."""

    min_score: float = 0.35
    top_k: int = 5
    max_chars: int | None = DEFAULT_MEMORY_BUDGET_CHARS
    max_tokens: int | None = DEFAULT_MEMORY_BUDGET_TOKENS

    def __post_init__(self) -> None:
        if not math.isfinite(self.min_score) or not 0.0 <= self.min_score <= 1.0:
            raise ValueError("min_score must be finite and between 0 and 1")
        if self.top_k < 0:
            raise ValueError("top_k must be non-negative")
        if self.max_chars is not None and self.max_chars < 0:
            raise ValueError("max_chars must be non-negative or None")
        if self.max_tokens is not None and self.max_tokens < 0:
            raise ValueError("max_tokens must be non-negative or None")


@dataclass(frozen=True)
class MemorySelectionDecision:
    """One candidate's terminal outcome and the evidence for that outcome."""

    memory_id: str
    status: MemoryDecisionStatus
    reason: MemoryDecisionReason
    score: float
    source_rank: int
    authority: PreferenceAuthority
    candidate_chars: int
    candidate_tokens: int
    related_memory_id: str | None = None
    detail: str = ""


@dataclass(frozen=True)
class MemoryContextPlan:
    """Rendered memory context plus a complete, deterministic decision log."""

    context: str
    user_scope: str
    policy: MemorySelectionPolicy
    candidate_count: int
    used_chars: int
    used_tokens: int
    decisions: tuple[MemorySelectionDecision, ...]

    @property
    def selected_memory_ids(self) -> tuple[str, ...]:
        return tuple(
            decision.memory_id
            for decision in self.decisions
            if decision.status is MemoryDecisionStatus.SELECTED
        )

    @property
    def rejected_memory_ids(self) -> tuple[str, ...]:
        return tuple(
            decision.memory_id
            for decision in self.decisions
            if decision.status is MemoryDecisionStatus.REJECTED
        )


TokenCounter = Callable[[str], int]


def estimate_context_tokens(text: str) -> int:
    """Return deterministic teaching units, not a provider tokenizer claim.

    Latin word runs, individual CJK characters, and punctuation each count as
    one unit. Production adapters should inject the target model's tokenizer;
    the policy and decision report remain unchanged.
    """

    return len(
        re.findall(r"[a-zA-Z0-9_]+|[\u3400-\u9fff]|[^\s]", text)
    )


def _count_tokens(token_counter: TokenCounter, text: str) -> int:
    """Validate an injected tokenizer before its result controls admission."""

    count = token_counter(text)
    if isinstance(count, bool) or not isinstance(count, int) or count < 0:
        raise ValueError("token_counter must return a non-negative integer")
    return count


def _candidate_order(candidate: MemoryContextCandidate) -> tuple[object, ...]:
    """Rank by authority, then retrieval evidence, never input order."""

    return (
        -_PREFERENCE_AUTHORITY_PRIORITY[candidate.authority],
        -candidate.score,
        candidate.source_rank,
        -_parse_utc_timestamp(candidate.provenance.captured_at).timestamp(),
        candidate.memory_id,
    )


def render_memory_hit(candidate: MemoryContextCandidate) -> str:
    """Render one candidate atomically with its scope and provenance."""

    provenance = candidate.provenance
    conflict_attr = (
        f' conflict_key="{html.escape(candidate.conflict_key, quote=True)}"'
        if candidate.conflict_key
        else ""
    )
    return (
        f'<memory_hit memory_id="{html.escape(candidate.memory_id, quote=True)}" '
        f'score="{candidate.score:.6f}" source_rank="{candidate.source_rank}" '
        f'authority="{candidate.authority.value}" '
        f'user_scope="{html.escape(candidate.user_scope, quote=True)}" '
        f'source_id="{html.escape(provenance.source_id, quote=True)}" '
        f'source_type="{html.escape(provenance.source_type, quote=True)}" '
        f'captured_at="{html.escape(provenance.captured_at, quote=True)}"'
        f'{conflict_attr}>'
        f'{html.escape(candidate.text)}'
        "</memory_hit>"
    )


def render_memory_context(
    user_scope: str,
    candidates: Sequence[MemoryContextCandidate],
) -> str:
    """Render the selected candidates without hiding wrapper budget cost."""

    if not candidates:
        return ""
    raw_scope = _required_text(user_scope, field_name="user_scope")
    mismatched = sorted(
        candidate.memory_id
        for candidate in candidates
        if candidate.user_scope != raw_scope
    )
    if mismatched:
        raise ValueError(
            "cannot render candidates from another scope: " + ", ".join(mismatched)
        )
    scope = html.escape(raw_scope, quote=True)
    hits = "\n".join(render_memory_hit(candidate) for candidate in candidates)
    return (
        f'<recalled_memory user_scope="{scope}" selected="{len(candidates)}">\n'
        f"{hits}\n"
        "</recalled_memory>"
    )


def _decision(
    candidate: MemoryContextCandidate,
    *,
    status: MemoryDecisionStatus,
    reason: MemoryDecisionReason,
    token_counter: TokenCounter,
    related_memory_id: str | None = None,
    detail: str = "",
) -> MemorySelectionDecision:
    rendered = render_memory_hit(candidate)
    return MemorySelectionDecision(
        memory_id=candidate.memory_id,
        status=status,
        reason=reason,
        score=candidate.score,
        source_rank=candidate.source_rank,
        authority=candidate.authority,
        candidate_chars=len(rendered),
        candidate_tokens=_count_tokens(token_counter, rendered),
        related_memory_id=related_memory_id,
        detail=detail,
    )


def select_memory_context(
    candidates: Sequence[MemoryContextCandidate],
    *,
    user_scope: str,
    policy: MemorySelectionPolicy | None = None,
    token_counter: TokenCounter = estimate_context_tokens,
) -> MemoryContextPlan:
    """Select and atomically pack recalled memory under explicit constraints.

    The order is intentional: security scope and confidence are gates; exact
    duplicates within one fact slot and typed conflicts are resolved before
    scarce budget is spent. Unkeyed candidates only deduplicate with other
    unkeyed candidates; equal prose does not make different slots equivalent.
    Authority orders eligible candidates as ``current_turn`` >
    ``workspace_override`` > ``user_default``; score, source rank, capture time,
    and ID only break ties inside one authority. Top-k and budgets then pack the
    surviving records in that same order. An oversized record does not stop
    packing, so a smaller lower-ranked record can still use the remaining
    budget. Conflict losers never backfill because they represent facts
    superseded by the chosen winner, not merely expensive context.
    """

    scope = _required_text(user_scope, field_name="user_scope")
    active_policy = policy or MemorySelectionPolicy()
    candidate_ids = [candidate.memory_id for candidate in candidates]
    duplicates = sorted(
        memory_id
        for memory_id in set(candidate_ids)
        if candidate_ids.count(memory_id) > 1
    )
    if duplicates:
        raise ValueError("duplicate memory candidate ids: " + ", ".join(duplicates))

    ranked = sorted(candidates, key=_candidate_order)
    decisions: dict[str, MemorySelectionDecision] = {}
    eligible: list[MemoryContextCandidate] = []

    for candidate in ranked:
        if candidate.user_scope != scope:
            decisions[candidate.memory_id] = _decision(
                candidate,
                status=MemoryDecisionStatus.REJECTED,
                reason=MemoryDecisionReason.SCOPE_MISMATCH,
                token_counter=token_counter,
                detail=f"candidate scope {candidate.user_scope!r} != query scope {scope!r}",
            )
        elif candidate.score < active_policy.min_score:
            decisions[candidate.memory_id] = _decision(
                candidate,
                status=MemoryDecisionStatus.REJECTED,
                reason=MemoryDecisionReason.LOW_CONFIDENCE,
                token_counter=token_counter,
                detail=(
                    f"score {candidate.score:.6f} is below "
                    f"min_score {active_policy.min_score:.6f}"
                ),
            )
        else:
            eligible.append(candidate)

    deduplicated: list[MemoryContextCandidate] = []
    content_winners: dict[tuple[str | None, str], MemoryContextCandidate] = {}
    for candidate in eligible:
        # Keep slot identity through deduplication: dropping an equal-text
        # record from another slot could remove that slot's authority winner
        # and let a superseded preference survive conflict resolution.
        # None is distinct from every explicit slot; normalize named slots
        # exactly as the conflict stage below does.
        normalized_slot = (
            _normalized_memory_text(candidate.conflict_key)
            if candidate.conflict_key is not None
            else None
        )
        key = (normalized_slot, _normalized_memory_text(candidate.text))
        winner = content_winners.get(key)
        if winner is not None:
            decisions[candidate.memory_id] = _decision(
                candidate,
                status=MemoryDecisionStatus.REJECTED,
                reason=MemoryDecisionReason.DUPLICATE_CONTENT,
                token_counter=token_counter,
                related_memory_id=winner.memory_id,
                detail=(
                    f"normalized content duplicates {winner.memory_id} "
                    f"in fact slot {normalized_slot!r}"
                ),
            )
            continue
        content_winners[key] = candidate
        deduplicated.append(candidate)

    conflict_free: list[MemoryContextCandidate] = []
    conflict_winners: dict[str, MemoryContextCandidate] = {}
    for candidate in deduplicated:
        conflict_key = candidate.conflict_key
        if conflict_key is None:
            conflict_free.append(candidate)
            continue
        normalized_key = _normalized_memory_text(conflict_key)
        winner = conflict_winners.get(normalized_key)
        if winner is not None:
            authority_lost = (
                _PREFERENCE_AUTHORITY_PRIORITY[candidate.authority]
                < _PREFERENCE_AUTHORITY_PRIORITY[winner.authority]
            )
            reason = (
                MemoryDecisionReason.AUTHORITY_LOSER
                if authority_lost
                else MemoryDecisionReason.CONFLICT_LOSER
            )
            if authority_lost:
                detail = (
                    f"conflict slot {conflict_key!r}: "
                    f"{candidate.authority.value} lost to "
                    f"{winner.authority.value} candidate {winner.memory_id}"
                )
            else:
                detail = f"conflict slot {conflict_key!r} won by {winner.memory_id}"
            decisions[candidate.memory_id] = _decision(
                candidate,
                status=MemoryDecisionStatus.REJECTED,
                reason=reason,
                token_counter=token_counter,
                related_memory_id=winner.memory_id,
                detail=detail,
            )
            continue
        conflict_winners[normalized_key] = candidate
        conflict_free.append(candidate)

    selected: list[MemoryContextCandidate] = []
    for candidate in conflict_free:
        if len(selected) >= active_policy.top_k:
            decisions[candidate.memory_id] = _decision(
                candidate,
                status=MemoryDecisionStatus.REJECTED,
                reason=MemoryDecisionReason.TOP_K_REACHED,
                token_counter=token_counter,
                detail=f"top_k {active_policy.top_k} already filled",
            )
            continue

        proposed_context = render_memory_context(scope, [*selected, candidate])
        proposed_chars = len(proposed_context)
        proposed_tokens = _count_tokens(token_counter, proposed_context)
        if (
            active_policy.max_chars is not None
            and proposed_chars > active_policy.max_chars
        ):
            decisions[candidate.memory_id] = _decision(
                candidate,
                status=MemoryDecisionStatus.REJECTED,
                reason=MemoryDecisionReason.CHAR_BUDGET_EXCEEDED,
                token_counter=token_counter,
                detail=(
                    f"would use {proposed_chars} chars; "
                    f"budget is {active_policy.max_chars}"
                ),
            )
            continue
        if (
            active_policy.max_tokens is not None
            and proposed_tokens > active_policy.max_tokens
        ):
            decisions[candidate.memory_id] = _decision(
                candidate,
                status=MemoryDecisionStatus.REJECTED,
                reason=MemoryDecisionReason.TOKEN_BUDGET_EXCEEDED,
                token_counter=token_counter,
                detail=(
                    f"would use {proposed_tokens} tokens; "
                    f"budget is {active_policy.max_tokens}"
                ),
            )
            continue

        selected.append(candidate)
        decisions[candidate.memory_id] = _decision(
            candidate,
            status=MemoryDecisionStatus.SELECTED,
            reason=MemoryDecisionReason.SELECTED,
            token_counter=token_counter,
            detail="passed gates and fits top-k/context budgets",
        )

    context = render_memory_context(scope, selected)
    return MemoryContextPlan(
        context=context,
        user_scope=scope,
        policy=active_policy,
        candidate_count=len(candidates),
        used_chars=len(context),
        used_tokens=_count_tokens(token_counter, context),
        decisions=tuple(decisions[candidate.memory_id] for candidate in ranked),
    )


def memory_candidates_from_recall(
    result: object,
    *,
    conflict_keys: Mapping[str, str] | None = None,
    authority_by_memory_id: Mapping[str, PreferenceAuthority | str] | None = None,
) -> tuple[MemoryContextCandidate, ...]:
    """Adapt S12's public RecallResult shape without coupling chapter imports.

    The bridge uses structural attributes so S15 remains independently runnable.
    Scope, score, provider rank, and provenance are copied rather than recomputed.
    S12 records default to ``user_default``; a trusted caller can explicitly
    label a workspace override or current-turn instruction. Selection policy
    belongs here, while retrieval evidence continues to belong to S12.
    """

    query = getattr(result, "query", None)
    query_scope = getattr(query, "user_scope", None)
    converted: list[MemoryContextCandidate] = []
    for hit in getattr(result, "hits", ()):
        memory_id = _required_text(
            getattr(hit, "memory_id", ""), field_name="recall memory_id"
        )
        scope = getattr(hit, "scope", None)
        hit_scope = getattr(scope, "user_scope", query_scope)
        provenance = getattr(hit, "provenance", None)
        if provenance is None:
            provenance = getattr(hit, "source", None)
        if provenance is None:
            raise ValueError(f"recall hit {memory_id} has no provenance")
        breakdown = getattr(hit, "score_breakdown", None)
        score = getattr(breakdown, "total", getattr(hit, "score", None))
        if score is None:
            raise ValueError(f"recall hit {memory_id} has no score")
        converted.append(
            MemoryContextCandidate(
                memory_id=memory_id,
                text=_required_text(
                    getattr(hit, "snippet", ""), field_name="recall snippet"
                ),
                user_scope=_required_text(
                    hit_scope, field_name="recall user_scope"
                ),
                score=float(score),
                source_rank=int(getattr(hit, "rank", 0)),
                provenance=MemoryContextProvenance(
                    source_id=str(getattr(provenance, "source_id", "")),
                    source_type=str(getattr(provenance, "source_type", "")),
                    title=str(getattr(provenance, "title", "")),
                    captured_at=str(getattr(provenance, "captured_at", "")),
                ),
                conflict_key=(conflict_keys or {}).get(memory_id),
                authority=(authority_by_memory_id or {}).get(
                    memory_id, PreferenceAuthority.USER_DEFAULT
                ),
            )
        )
    return tuple(converted)


# ======================================================================
# Prompt Segment system
# ======================================================================

@dataclass
class PromptSegment:
    """A single segment of the system prompt.

    Each segment has:
    - name: identifier for debugging
    - builder: function that returns str | None
    - condition: function that returns bool (default: always True)
    - priority: lower = earlier in the prompt (default: 50)
    - required: a budget may never remove this segment
    - budget_priority: higher-value optional segments win scarce budget
    - provenance: source label retained in the assembly decision report

    If builder returns None, or condition returns False,
    the segment is not included.
    """
    name: str
    builder: Callable[[], str | None]
    condition: Callable[[], bool] = field(default=lambda: True)
    priority: int = 50
    required: bool = False
    budget_priority: int = 50
    provenance: str = "runtime"

    def build(self) -> str | None:
        if not self.condition():
            return None
        return self.builder()


PROMPT_SEPARATOR = "\n\n---\n\n"


class PromptBudgetError(ValueError):
    """Raised when required prompt segments cannot fit the configured budget."""


@dataclass(frozen=True)
class SegmentDecision:
    """One explainable include/drop decision made by the budget planner."""

    name: str
    priority: int
    required: bool
    budget_priority: int
    provenance: str
    status: str
    original_chars: int
    rendered_chars: int
    reason: str


@dataclass(frozen=True)
class PromptPlan:
    """Rendered prompt plus the decisions that produced it."""

    prompt: str
    budget_chars: int | None
    used_chars: int
    decisions: tuple[SegmentDecision, ...]

    @property
    def included_names(self) -> tuple[str, ...]:
        return tuple(
            decision.name for decision in self.decisions
            if decision.status == "included"
        )

    @property
    def dropped_names(self) -> tuple[str, ...]:
        return tuple(
            decision.name for decision in self.decisions
            if decision.status == "dropped"
        )


def _rendered_length(contents: list[str]) -> int:
    if not contents:
        return 0
    return sum(len(content) for content in contents) + (
        len(contents) - 1
    ) * len(PROMPT_SEPARATOR)


def plan_prompt(
    segments: list[PromptSegment],
    *,
    budget_chars: int | None = DEFAULT_PROMPT_BUDGET_CHARS,
) -> PromptPlan:
    """Build and select prompt segments under an explicit character budget.

    Required segments are admitted first. Optional segments are considered by
    descending ``budget_priority`` with stable presentation priority/name tie
    breaks. Selected content is finally rendered by presentation ``priority``.

    A segment is an atomic trust/provenance block: the planner drops an
    optional block in full instead of silently slicing memory or instructions.
    Builders may create their own compact projection before this boundary.
    """
    if budget_chars is not None and budget_chars < 0:
        raise ValueError("budget_chars must be non-negative or None")
    names = [segment.name for segment in segments]
    duplicate_names = sorted({name for name in names if names.count(name) > 1})
    if duplicate_names:
        raise ValueError(
            "duplicate prompt segment names: " + ", ".join(duplicate_names)
        )

    built: list[tuple[PromptSegment, str]] = []
    for segment in segments:
        content = segment.build()
        if content:
            built.append((segment, content))

    required = [(segment, content) for segment, content in built if segment.required]
    optional = [(segment, content) for segment, content in built if not segment.required]
    selected: dict[str, tuple[PromptSegment, str]] = {
        segment.name: (segment, content) for segment, content in required
    }

    required_contents = [
        content for _, content in sorted(
            required, key=lambda item: (item[0].priority, item[0].name)
        )
    ]
    required_chars = _rendered_length(required_contents)
    if budget_chars is not None and required_chars > budget_chars:
        required_names = ", ".join(segment.name for segment, _ in required)
        raise PromptBudgetError(
            f"required prompt segments need {required_chars} chars, "
            f"but budget is {budget_chars}: {required_names}"
        )

    rejected: dict[str, str] = {}
    for segment, content in sorted(
        optional,
        key=lambda item: (-item[0].budget_priority, item[0].priority, item[0].name),
    ):
        candidate = list(selected.values()) + [(segment, content)]
        ordered_contents = [
            value for _, value in sorted(
                candidate, key=lambda item: (item[0].priority, item[0].name)
            )
        ]
        candidate_chars = _rendered_length(ordered_contents)
        if budget_chars is None or candidate_chars <= budget_chars:
            selected[segment.name] = (segment, content)
        else:
            rejected[segment.name] = (
                f"needs {candidate_chars} chars after higher-value segments; "
                f"budget is {budget_chars}"
            )

    ordered_selected = sorted(
        selected.values(), key=lambda item: (item[0].priority, item[0].name)
    )
    prompt = PROMPT_SEPARATOR.join(content for _, content in ordered_selected)

    decisions: list[SegmentDecision] = []
    built_by_identity = {id(segment): content for segment, content in built}
    for segment in sorted(segments, key=lambda item: (item.priority, item.name)):
        built_content = built_by_identity.get(id(segment))
        if built_content is None:
            decisions.append(SegmentDecision(
                name=segment.name, priority=segment.priority,
                required=segment.required, budget_priority=segment.budget_priority,
                provenance=segment.provenance, status="inactive",
                original_chars=0, rendered_chars=0,
                reason="condition false or builder returned empty content",
            ))
        elif segment.name in selected:
            decisions.append(SegmentDecision(
                name=segment.name, priority=segment.priority,
                required=segment.required, budget_priority=segment.budget_priority,
                provenance=segment.provenance, status="included",
                original_chars=len(built_content), rendered_chars=len(built_content),
                reason="required segment" if segment.required else "fits budget by value order",
            ))
        else:
            decisions.append(SegmentDecision(
                name=segment.name, priority=segment.priority,
                required=segment.required, budget_priority=segment.budget_priority,
                provenance=segment.provenance, status="dropped",
                original_chars=len(built_content), rendered_chars=0,
                reason=rejected[segment.name],
            ))

    return PromptPlan(
        prompt=prompt,
        budget_chars=budget_chars,
        used_chars=len(prompt),
        decisions=tuple(decisions),
    )


# ======================================================================
# Runtime state (changes trigger reassembly)
# ======================================================================

active_expert: dict | None = None
loaded_skills: list[dict] = []
work_mode: str = "craft"  # craft | plan | ask
region: str = "CN"
connectors: list[dict] = []

# S12 recall output is installed as runtime state, just like skills or an
# expert. Reassembly reruns selection because the active query scope and the
# target model's budget may have changed since the previous provider turn.
recalled_memory_candidates: tuple[MemoryContextCandidate, ...] = ()
recalled_memory_user_scope: str | None = None
memory_selection_policy = MemorySelectionPolicy()
memory_token_counter: TokenCounter = estimate_context_tokens
LAST_MEMORY_CONTEXT_PLAN: MemoryContextPlan | None = None


# ======================================================================
# Segment builders
# ======================================================================

def build_base_instructions() -> str:
    """Segment 1: Base instructions — always included."""
    return f"""你是一个桌面 AI 助手 (WorkBuddy 教学版)。

工作目录: {WORKDIR}

核心规则:
- 使用工具解决问题, 不要只说不做
- 遵循权限系统, 危险操作需用户确认
- 工具执行前后有 hooks 扩展点
- 回答简洁, 先行动后解释"""


def build_identity() -> str | None:
    """Segment 2: Identity injection — SOUL/IDENTITY/USER files.

    In real WorkBuddy, these files live at ~/.workbuddy/.
    Teaching version: check if they exist, read and inject.
    """
    parts = []
    identity_dir = tutorial_workbuddy_home()

    for name, filename in [("SOUL", "persona/core.md"),
                            ("IDENTITY", "persona/identity.md"),
                            ("USER", "persona/user.md")]:
        filepath = identity_dir / filename
        if filepath.exists():
            content = filepath.read_text().strip()
            if content:
                parts.append(f"## {name}\n{content}")

    if not parts:
        # Simulated identity (in real usage, user creates these files)
        parts.append("## SOUL\n你是 CodeBuddy, 一个务实高效的编程助手。")
        parts.append("## USER\n用户是开发者, 偏好简洁直接的回答。")

    return "\n\n".join(parts)


def build_cloud_memory() -> str | None:
    """Segment 3: select and pack current S12 recall candidates.

    The historical function name remains as a compatibility entrypoint, but
    the returned block is no longer a hard-coded profile. No current recall
    means the segment is inactive instead of injecting stale example data.
    """

    global LAST_MEMORY_CONTEXT_PLAN
    if not recalled_memory_candidates or recalled_memory_user_scope is None:
        LAST_MEMORY_CONTEXT_PLAN = None
        return None
    LAST_MEMORY_CONTEXT_PLAN = select_memory_context(
        recalled_memory_candidates,
        user_scope=recalled_memory_user_scope,
        policy=memory_selection_policy,
        token_counter=memory_token_counter,
    )
    return LAST_MEMORY_CONTEXT_PLAN.context or None


def build_project_context() -> str:
    """Segment 4: Project context — file structure, working directory."""
    # List top-level files/dirs in workdir
    try:
        entries = sorted(WORKDIR.iterdir(), key=lambda p: (p.is_file(), p.name))
        tree_lines = []
        for e in entries[:20]:  # Limit to 20 entries
            if e.name.startswith('.'):
                continue
            tree_lines.append(f"  {'📁' if e.is_dir() else '📄'} {e.name}")
        tree = "\n".join(tree_lines) if tree_lines else "  (empty)"
    except Exception:
        tree = "  (unable to read)"

    return f"""## 项目上下文

工作目录: {WORKDIR}
目录结构:
{tree}"""


def build_tool_descriptions() -> str:
    """Segment 5: Tool descriptions — dynamically generated from TOOLS."""
    if not TOOLS:
        return ""
    lines = ["## 可用工具"]
    for tool in TOOLS:
        params = tool.get("input_schema", {}).get("properties", {})
        param_str = ", ".join(params.keys()) if params else "none"
        lines.append(f"- **{tool['name']}**({param_str}): {tool['description']}")
    return "\n".join(lines)


def build_expert_instructions() -> str | None:
    """Segment 6: Expert instructions — only when expert is active."""
    if not active_expert:
        return None
    return f"""## 专家模式: {active_expert['name']}

{active_expert['instructions']}"""


def build_skill_instructions() -> str | None:
    """Segment 7: Skill instructions — loaded skills' SKILL.md content."""
    if not loaded_skills:
        return None
    parts = []
    for skill in loaded_skills:
        parts.append(f"## 技能: {skill['title']}\n{skill['content']}")
    return "\n\n".join(parts)


def build_connector_status() -> str | None:
    """Segment 8: Connector status — available MCP connectors."""
    if not connectors:
        return None
    lines = ["## 连接器状态"]
    for conn in connectors:
        status = "已连接" if conn.get("connected") else "未连接"
        lines.append(f"- {conn['name']}: {status} ({len(conn.get('tools', []))} tools)")
    return "\n".join(lines)


def build_regional_conventions() -> str:
    """Segment 9: Regional conventions — stock colors, currency, dates."""
    if region == "CN":
        return """## 区域约定
- 股市涨跌颜色: 红涨绿跌 (中国市场惯例)
- 货币: CNY (¥)
- 日期格式: YYYY-MM-DD
- 语言: 简体中文"""
    else:
        return """## Regional Conventions
- Stock colors: green up, red down
- Currency: USD ($)
- Date format: MM/DD/YYYY
- Language: English"""


def build_work_mode() -> str:
    """Segment 10: Working mode — craft / plan / ask."""
    modes = {
        "craft": "## 工作模式: Craft\n直接动手, 使用工具完成任务。默认模式。",
        "plan": "## 工作模式: Plan\n先制定计划, 列出步骤, 等用户确认后再执行。",
        "ask": "## 工作模式: Ask\n只回答问题, 不主动执行操作。适合咨询场景。",
    }
    return modes.get(work_mode, modes["craft"])


# ======================================================================
# Segment registry
# ======================================================================

SEGMENTS: list[PromptSegment] = [
    PromptSegment(
        "base", build_base_instructions, priority=10, required=True,
        provenance="harness:base-rules",
    ),
    PromptSegment(
        "identity", build_identity, priority=20, budget_priority=90,
        provenance="user:persona",
    ),
    PromptSegment(
        "memory", build_cloud_memory, priority=25, budget_priority=60,
        provenance="remote:ranked-recall-selection",
    ),
    PromptSegment(
        "project", build_project_context, priority=30, budget_priority=80,
        provenance="workspace:project-context",
    ),
    PromptSegment(
        "tools", build_tool_descriptions, priority=40, required=True,
        provenance="harness:tool-registry",
    ),
    PromptSegment("expert", build_expert_instructions,
                  condition=lambda: active_expert is not None, priority=50,
                  budget_priority=85, provenance="runtime:active-expert"),
    PromptSegment("skills", build_skill_instructions,
                  condition=lambda: len(loaded_skills) > 0, priority=55,
                  budget_priority=75, provenance="runtime:loaded-skills"),
    PromptSegment("connectors", build_connector_status,
                  condition=lambda: len(connectors) > 0, priority=60,
                  budget_priority=40, provenance="runtime:connectors"),
    PromptSegment(
        "region", build_regional_conventions, priority=70,
        budget_priority=20, provenance="runtime:region",
    ),
    PromptSegment(
        "mode", build_work_mode, priority=80, required=True,
        provenance="harness:work-mode",
    ),
]


LAST_PROMPT_PLAN: PromptPlan | None = None


def assemble_system_prompt(
    verbose: bool = False,
    *,
    budget_chars: int | None = None,
) -> str:
    """Assemble system prompt from segments.

    1. Build each segment and keep its provenance
    2. Reserve required segments
    3. Select optional segments by budget value
    4. Render selected segments in presentation order
    """
    global LAST_PROMPT_PLAN
    if budget_chars is None:
        budget_chars = PROMPT_BUDGET_CHARS
    LAST_PROMPT_PLAN = plan_prompt(SEGMENTS, budget_chars=budget_chars)

    if verbose:
        if LAST_MEMORY_CONTEXT_PLAN is not None:
            print(
                f"\n\033[90m{'memory':<18} {'authority':<18} {'rank':>5} {'score':>8} "
                f"{'status':>9} reason / detail\033[0m"
            )
            for decision in LAST_MEMORY_CONTEXT_PLAN.decisions:
                print(
                    f"\033[90m{decision.memory_id:<18} "
                    f"{decision.authority.value:<18} "
                    f"{decision.source_rank:>5} {decision.score:>8.3f} "
                    f"{decision.status.value:>9} {decision.reason.value} / "
                    f"{decision.detail}\033[0m"
                )
            memory_budget = LAST_MEMORY_CONTEXT_PLAN.policy
            print(
                f"\033[90mmemory used "
                f"{LAST_MEMORY_CONTEXT_PLAN.used_chars:,}/"
                f"{memory_budget.max_chars} chars; "
                f"{LAST_MEMORY_CONTEXT_PLAN.used_tokens:,}/"
                f"{memory_budget.max_tokens} tokens; selected="
                f"{list(LAST_MEMORY_CONTEXT_PLAN.selected_memory_ids)}"
                f"\033[0m\n"
            )
        print(
            f"\n\033[90m{'segment':<12} {'order':>5} {'value':>5} "
            f"{'status':>9} {'chars':>7} source / reason\033[0m"
        )
        for decision in LAST_PROMPT_PLAN.decisions:
            print(
                f"\033[90m{decision.name:<12} {decision.priority:>5} "
                f"{decision.budget_priority:>5} {decision.status:>9} "
                f"{decision.rendered_chars:>7} {decision.provenance} / "
                f"{decision.reason}\033[0m"
            )
        budget = "unbounded" if budget_chars is None else f"{budget_chars:,}"
        print(
            f"\033[90mused {LAST_PROMPT_PLAN.used_chars:,} / {budget} chars; "
            f"dropped={list(LAST_PROMPT_PLAN.dropped_names)}\033[0m\n"
        )

    return LAST_PROMPT_PLAN.prompt


# ======================================================================
# Reassembly triggers
# ======================================================================

SYSTEM_PROMPT = ""


def reassemble_prompt():
    """Reassemble the system prompt and update the global."""
    global SYSTEM_PROMPT
    SYSTEM_PROMPT = assemble_system_prompt()
    print(f"\033[90m[prompt] 重新组装, 长度: {len(SYSTEM_PROMPT):,} 字符\033[0m")


def set_recalled_memory(
    candidates: Sequence[MemoryContextCandidate],
    *,
    user_scope: str,
    policy: MemorySelectionPolicy | None = None,
    token_counter: TokenCounter = estimate_context_tokens,
) -> None:
    """Install current-query recall candidates and trigger prompt reassembly.

    Runtime state stores candidates, not a pre-rendered string. Replanning here
    guarantees that a scope/policy/tokenizer change cannot reuse context chosen
    under the previous turn's constraints.
    """

    global recalled_memory_candidates
    global recalled_memory_user_scope
    global memory_selection_policy
    global memory_token_counter
    recalled_memory_candidates = tuple(candidates)
    recalled_memory_user_scope = _required_text(
        user_scope, field_name="recalled memory user_scope"
    )
    memory_selection_policy = policy or MemorySelectionPolicy()
    memory_token_counter = token_counter
    reassemble_prompt()
    selected = (
        list(LAST_MEMORY_CONTEXT_PLAN.selected_memory_ids)
        if LAST_MEMORY_CONTEXT_PLAN is not None
        else []
    )
    print(
        f"\033[32m[prompt] recall 候选 {len(candidates)} 条, "
        f"已选择 {selected}\033[0m"
    )


def clear_recalled_memory() -> None:
    """Remove query-scoped recall state so it cannot leak into another turn."""

    global recalled_memory_candidates
    global recalled_memory_user_scope
    global LAST_MEMORY_CONTEXT_PLAN
    recalled_memory_candidates = ()
    recalled_memory_user_scope = None
    LAST_MEMORY_CONTEXT_PLAN = None
    reassemble_prompt()


def load_skill(title: str, content: str):
    """Load a skill — triggers prompt reassembly."""
    loaded_skills.append({"title": title, "content": content})
    reassemble_prompt()
    print(f"\033[32m[prompt] 技能 '{title}' 已加载\033[0m")


def set_expert(name: str, instructions: str):
    """Set active expert — triggers prompt reassembly."""
    global active_expert
    active_expert = {"name": name, "instructions": instructions}
    reassemble_prompt()
    print(f"\033[32m[prompt] 专家 '{name}' 已激活\033[0m")


def switch_mode(mode: str):
    """Switch work mode — triggers prompt reassembly."""
    global work_mode
    if mode not in ("craft", "plan", "ask"):
        print(f"未知模式: {mode}")
        return
    work_mode = mode
    reassemble_prompt()
    print(f"\033[32m[prompt] 工作模式切换为 '{mode}'\033[0m")


def add_connector(name: str, tool_count: int = 5):
    """Add a connector — triggers prompt reassembly."""
    connectors.append({
        "name": name,
        "connected": True,
        "tools": [f"{name}_tool_{i}" for i in range(tool_count)],
    })
    reassemble_prompt()
    print(f"\033[32m[prompt] 连接器 '{name}' 已连接 ({tool_count} tools)\033[0m")


def load_demo_recalled_memory() -> None:
    """Install a keyless fixture that exposes every important selector gate."""

    def demo_candidate(
        memory_id: str,
        text: str,
        *,
        score: float,
        rank: int,
        conflict_key: str | None = None,
        user_scope: str = "demo-user-scope",
        authority: PreferenceAuthority = PreferenceAuthority.USER_DEFAULT,
    ) -> MemoryContextCandidate:
        return MemoryContextCandidate(
            memory_id=memory_id,
            text=text,
            user_scope=user_scope,
            score=score,
            source_rank=rank,
            provenance=MemoryContextProvenance(
                source_id=f"demo-transcript:{memory_id}",
                source_type="transcript",
                title="S15 offline selection fixture",
                captured_at=f"2026-08-{18-rank:02d}T09:00:00Z",
            ),
            conflict_key=conflict_key,
            authority=authority,
        )

    set_recalled_memory(
        [
            demo_candidate(
                "python-default",
                "Prefer Python for automation tasks by default.",
                score=0.93,
                rank=1,
                conflict_key="preference:automation-language",
            ),
            demo_candidate(
                "typescript-workspace",
                "Use TypeScript for automation in this workspace.",
                score=0.86,
                rank=2,
                conflict_key="preference:automation-language",
                authority=PreferenceAuthority.WORKSPACE_OVERRIDE,
            ),
            demo_candidate(
                "python-current-turn",
                "For this turn, implement the automation in Python.",
                score=0.72,
                rank=3,
                conflict_key="preference:automation-language",
                authority=PreferenceAuthority.CURRENT_TURN,
            ),
            demo_candidate(
                "source-grounding",
                "Answers should cite the source evidence.",
                score=0.81,
                rank=4,
                conflict_key="preference:source-grounding",
            ),
            demo_candidate(
                "weak-overlap",
                "An incidental lexical match.",
                score=0.18,
                rank=5,
            ),
            demo_candidate(
                "other-user",
                "This must never cross the user boundary.",
                score=0.99,
                rank=1,
                user_scope="another-user-scope",
            ),
        ],
        user_scope="demo-user-scope",
        policy=MemorySelectionPolicy(
            min_score=0.35,
            top_k=2,
            max_chars=1_200,
            max_tokens=400,
        ),
    )


# ======================================================================
# Tools (simplified)
# ======================================================================

def run_bash(command: str) -> str:
    import subprocess
    try:
        r = subprocess.run(command, shell=True, cwd=WORKDIR,
                           capture_output=True, text=True, timeout=30)
        return (r.stdout + r.stderr).strip()[:3000] or "(no output)"
    except Exception as e:
        return f"Error: {e}"

def run_read(path: str) -> str:
    try:
        p = (WORKDIR / path).resolve()
        if not p.is_relative_to(WORKDIR):
            return "Error: path escapes workspace"
        return p.read_text()[:3000]
    except Exception as e:
        return f"Error: {e}"

def run_glob(pattern: str) -> str:
    import glob as g
    def inside_workdir(match: str) -> bool:
        try:
            try:
                resolved = Path(match).resolve(strict=True)
            except FileNotFoundError:  # 悬空链接：和原来一样按非严格方式解析
                resolved = Path(match).resolve()
            return resolved.is_relative_to(WORKDIR)
        except (RuntimeError, OSError):  # 符号链接环等无法解析的单项直接跳过
            return False

    matches = g.glob(os.path.join(g.escape(str(WORKDIR)), pattern))
    results = sorted(r for r in matches if inside_workdir(r))[:20]
    return "\n".join(Path(r).name for r in results) if results else "(no matches)"


TOOLS = [
    {"name": "bash", "description": "Run a shell command.",
     "input_schema": {"type": "object",
         "properties": {"command": {"type": "string"}}, "required": ["command"]}},
    {"name": "read_file", "description": "Read file contents.",
     "input_schema": {"type": "object",
         "properties": {"path": {"type": "string"}}, "required": ["path"]}},
    {"name": "glob", "description": "Find files matching a pattern.",
     "input_schema": {"type": "object",
         "properties": {"pattern": {"type": "string"}}, "required": ["pattern"]}},
]

TOOL_HANDLERS = {"bash": run_bash, "read_file": run_read, "glob": run_glob}


# ======================================================================
# Agent Loop
# ======================================================================

def agent_loop(messages: list):
    """Agent loop using the assembled system prompt."""
    client, model = runtime_client()
    while True:
        response = client.messages.create(
            model=model, system=SYSTEM_PROMPT, messages=messages,
            tools=TOOLS, max_tokens=8000,
        )
        messages.append({"role": "assistant", "content": response.content})

        if response.stop_reason != "tool_use":
            return

        results = []
        for block in response.content:
            if block.type != "tool_use":
                continue
            handler = TOOL_HANDLERS.get(block.name)
            output = handler(**block.input) if handler else f"Unknown: {block.name}"
            display = str(output)[:100].replace('\n', ' ')
            print(f"  \033[36m> {block.name}\033[0m {display}")
            results.append({"type": "tool_result",
                            "tool_use_id": block.id, "content": output})
        messages.append({"role": "user", "content": results})


# ======================================================================
# Main
# ======================================================================

if __name__ == "__main__":
    print("=" * 60)
    print("s15: Prompt Assembly — 运行时分段拼接")
    print("=" * 60)

    # Initial assembly
    reassemble_prompt()
    assemble_system_prompt(verbose=True)

    print("\033[90m命令:\033[0m")
    print("\033[90m  prompt   — 查看系统提示片段结构\033[0m")
    print("\033[90m  skill    — 模拟加载技能 (触发重新组装)\033[0m")
    print("\033[90m  expert   — 模拟切换专家 (触发重新组装)\033[0m")
    print("\033[90m  mode X   — 切换工作模式 craft/plan/ask\033[0m")
    print("\033[90m  conn     — 模拟连接器上线 (触发重新组装)\033[0m")
    print("\033[90m  memory   — 加载离线召回候选并查看选择/拒绝原因\033[0m")
    print("\033[90m  memory clear — 清除本轮召回, 防止跨查询泄漏\033[0m")
    print("\033[90m  stats    — 查看系统提示统计\033[0m")
    print()

    history = []
    while True:
        try:
            query = input("\033[36ms15 >> \033[0m")
        except (EOFError, KeyboardInterrupt):
            break
        if query.strip().lower() in ("q", "exit"):
            break

        cmd = query.strip().lower()

        if cmd == "prompt":
            assemble_system_prompt(verbose=True)
            print(f"\033[90m系统提示总长度: {len(SYSTEM_PROMPT):,} 字符\033[0m")
            print(f"\033[90m前 500 字符预览:\n{SYSTEM_PROMPT[:500]}\033[0m")
            continue

        if cmd == "skill":
            load_skill(
                "git-commit",
                "当用户要求提交代码时, 使用 /commit 命令。\n"
                "1. 检查 git status\n"
                "2. 暂存相关文件\n"
                "3. 生成规范的 commit message"
            )
            continue

        if cmd == "expert":
            set_expert("SoftwareCompany",
                       "你是软件公司架构师。专注于:\n"
                       "- 技术选型和架构设计\n"
                       "- 代码质量和可维护性\n"
                       "- 团队协作和工程实践")
            continue

        if cmd.startswith("mode "):
            switch_mode(query.strip().split(" ", 1)[1])
            continue

        if cmd == "conn":
            add_connector("github", tool_count=8)
            continue

        if cmd == "memory":
            load_demo_recalled_memory()
            assemble_system_prompt(verbose=True)
            continue

        if cmd == "memory clear":
            clear_recalled_memory()
            print("\033[32m[prompt] 本轮 recall 已清除\033[0m")
            continue

        if cmd == "stats":
            print(f"\033[90m系统提示长度: {len(SYSTEM_PROMPT):,} 字符\033[0m")
            print(f"\033[90m估算 token: {len(SYSTEM_PROMPT)//4:,}\033[0m")
            print(f"\033[90m已加载技能: {len(loaded_skills)}\033[0m")
            print(f"\033[90m激活专家: {active_expert['name'] if active_expert else '无'}\033[0m")
            print(f"\033[90m工作模式: {work_mode}\033[0m")
            print(f"\033[90m连接器: {len(connectors)}\033[0m")
            if LAST_MEMORY_CONTEXT_PLAN is None:
                print("\033[90mRecall: 无当前查询候选\033[0m")
            else:
                print(
                    f"\033[90mRecall: {LAST_MEMORY_CONTEXT_PLAN.candidate_count} "
                    f"候选 / {len(LAST_MEMORY_CONTEXT_PLAN.selected_memory_ids)} "
                    f"已选择 / {LAST_MEMORY_CONTEXT_PLAN.used_chars} chars / "
                    f"{LAST_MEMORY_CONTEXT_PLAN.used_tokens} tokens\033[0m"
                )
            continue

        # Normal query — send to agent
        history.append({"role": "user", "content": query})
        agent_loop(history)

        for block in history[-1]["content"]:
            if getattr(block, "type", None) == "text":
                print(block.text)
        print()
