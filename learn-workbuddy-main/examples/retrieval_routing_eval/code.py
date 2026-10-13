#!/usr/bin/env python3
"""Offline benchmark for Skill, Memory, and Reflection retrieval routing.

The example deliberately keeps ranking transparent and deterministic.  Policy
gates run before scoring, so a highly relevant but unapproved, out-of-scope, or
over-privileged candidate can never win by relevance alone.
"""

from __future__ import annotations

import argparse
import json
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Iterable


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_FIXTURES = Path(__file__).with_name("fixtures") / "cases.json"
DEFAULT_OUTPUT = ROOT / ".tmp" / "retrieval-routing-eval"

VALID_KINDS = {"skill", "memory", "reflection"}
VALID_STATUSES = {"active", "candidate", "resolved", "revoked"}
PROMPT_OVERRIDE_PATTERNS = (
    "ignore previous instructions",
    "ignore all previous instructions",
    "override the system prompt",
    "system message says",
    "developer message says",
    "忽略之前的指令",
    "覆盖系统提示",
)
STOP_TERMS = {
    "a", "an", "and", "are", "as", "at", "be", "by", "for", "from",
    "in", "is", "it", "of", "on", "or", "that", "the", "these", "this",
    "to", "was", "were", "with",
}


class RoutingContractError(ValueError):
    """Raised when fixtures or routing inputs violate the public contract."""


def _strict_dict(payload: object, *, field_name: str) -> dict:
    if not isinstance(payload, dict):
        raise RoutingContractError(f"{field_name} must be an object")
    return payload


def _strict_keys(payload: dict, *, allowed: set[str], field_name: str) -> None:
    unknown = set(payload) - allowed
    if unknown:
        raise RoutingContractError(
            f"{field_name} has unknown fields: {', '.join(sorted(unknown))}"
        )


def _text(value: object, *, field_name: str, allow_empty: bool = False) -> str:
    if not isinstance(value, str):
        raise RoutingContractError(f"{field_name} must be a string")
    cleaned = " ".join(value.split())
    if not cleaned and not allow_empty:
        raise RoutingContractError(f"{field_name} must not be empty")
    return cleaned


def _string_tuple(value: object, *, field_name: str) -> tuple[str, ...]:
    if value is None:
        return ()
    if not isinstance(value, list):
        raise RoutingContractError(f"{field_name} must be a list")
    result: list[str] = []
    for index, item in enumerate(value):
        cleaned = _text(item, field_name=f"{field_name}[{index}]")
        if cleaned not in result:
            result.append(cleaned)
    return tuple(result)


def _tokenize(text: str) -> set[str]:
    """Return deterministic English words and Chinese character bi-grams."""
    normalized = text.casefold()
    terms = {
        term
        for term in re.findall(r"[a-z0-9_]+", normalized)
        if term not in STOP_TERMS
    }
    for segment in re.findall(r"[\u4e00-\u9fff]+", normalized):
        if len(segment) == 1:
            terms.add(segment)
        else:
            terms.update(
                segment[index : index + 2] for index in range(len(segment) - 1)
            )
    return terms


@dataclass(frozen=True)
class CandidatePermissions:
    tools: tuple[str, ...] = ()
    network: bool = False

    @classmethod
    def from_dict(cls, payload: object) -> "CandidatePermissions":
        data = _strict_dict(payload or {}, field_name="candidate.permissions")
        _strict_keys(
            data,
            allowed={"tools", "network"},
            field_name="candidate.permissions",
        )
        network = data.get("network", False)
        if not isinstance(network, bool):
            raise RoutingContractError("candidate.permissions.network must be boolean")
        return cls(
            tools=_string_tuple(
                data.get("tools", []), field_name="candidate.permissions.tools"
            ),
            network=network,
        )


@dataclass(frozen=True)
class RoutingCandidate:
    candidate_id: str
    kind: str
    title: str
    summary: str
    content: str
    keywords: tuple[str, ...]
    status: str
    approved: bool
    user_scope: str | None
    workspace_scope: str | None
    task_family: str | None
    permissions: CandidatePermissions
    provenance: str

    @classmethod
    def from_dict(cls, payload: object) -> "RoutingCandidate":
        data = _strict_dict(payload, field_name="candidate")
        allowed = {
            "candidate_id", "kind", "title", "summary", "content", "keywords",
            "status", "approved", "user_scope", "workspace_scope", "task_family",
            "permissions", "provenance",
        }
        _strict_keys(data, allowed=allowed, field_name="candidate")
        kind = _text(data.get("kind"), field_name="candidate.kind")
        status = _text(data.get("status"), field_name="candidate.status")
        if kind not in VALID_KINDS:
            raise RoutingContractError(f"unsupported candidate kind: {kind}")
        if status not in VALID_STATUSES:
            raise RoutingContractError(f"unsupported candidate status: {status}")
        approved = data.get("approved")
        if not isinstance(approved, bool):
            raise RoutingContractError("candidate.approved must be boolean")

        def optional_scope(name: str) -> str | None:
            value = data.get(name)
            return None if value is None else _text(value, field_name=f"candidate.{name}")

        return cls(
            candidate_id=_text(
                data.get("candidate_id"), field_name="candidate.candidate_id"
            ),
            kind=kind,
            title=_text(data.get("title"), field_name="candidate.title"),
            summary=_text(data.get("summary"), field_name="candidate.summary"),
            content=_text(data.get("content"), field_name="candidate.content"),
            keywords=_string_tuple(
                data.get("keywords", []), field_name="candidate.keywords"
            ),
            status=status,
            approved=approved,
            user_scope=optional_scope("user_scope"),
            workspace_scope=optional_scope("workspace_scope"),
            task_family=optional_scope("task_family"),
            permissions=CandidatePermissions.from_dict(data.get("permissions", {})),
            provenance=_text(
                data.get("provenance"), field_name="candidate.provenance"
            ),
        )

    @property
    def searchable_text(self) -> str:
        return " ".join((self.title, self.summary, *self.keywords))

    @property
    def prompt_text(self) -> str:
        return (
            f"[{self.kind}:{self.candidate_id}] {self.summary} "
            f"(source: {self.provenance})"
        )


@dataclass(frozen=True)
class RoutingQuery:
    query_id: str
    text: str
    user_scope: str
    workspace_scope: str
    task_family: str | None = None
    allowed_tools: tuple[str, ...] = ()
    allow_network: bool = False
    top_k: int = 3
    prompt_budget_chars: int = 600

    @classmethod
    def from_dict(cls, payload: object) -> "RoutingQuery":
        data = _strict_dict(payload, field_name="case")
        allowed = {
            "case_id", "query", "user_scope", "workspace_scope", "task_family",
            "allowed_tools", "allow_network", "top_k", "prompt_budget_chars",
            "expected_ids", "forbidden_ids",
        }
        _strict_keys(data, allowed=allowed, field_name="case")
        allow_network = data.get("allow_network", False)
        if not isinstance(allow_network, bool):
            raise RoutingContractError("case.allow_network must be boolean")
        top_k = data.get("top_k", 3)
        budget = data.get("prompt_budget_chars", 600)
        if not isinstance(top_k, int) or not 1 <= top_k <= 20:
            raise RoutingContractError("case.top_k must be between 1 and 20")
        if not isinstance(budget, int) or budget < 1:
            raise RoutingContractError("case.prompt_budget_chars must be positive")
        family = data.get("task_family")
        return cls(
            query_id=_text(data.get("case_id"), field_name="case.case_id"),
            text=_text(data.get("query"), field_name="case.query"),
            user_scope=_text(data.get("user_scope"), field_name="case.user_scope"),
            workspace_scope=_text(
                data.get("workspace_scope"), field_name="case.workspace_scope"
            ),
            task_family=None
            if family is None
            else _text(family, field_name="case.task_family"),
            allowed_tools=_string_tuple(
                data.get("allowed_tools", []), field_name="case.allowed_tools"
            ),
            allow_network=allow_network,
            top_k=top_k,
            prompt_budget_chars=budget,
        )


@dataclass(frozen=True)
class EvalCase:
    query: RoutingQuery
    expected_ids: tuple[str, ...]
    forbidden_ids: tuple[str, ...]

    @classmethod
    def from_dict(cls, payload: object) -> "EvalCase":
        data = _strict_dict(payload, field_name="case")
        return cls(
            query=RoutingQuery.from_dict(data),
            expected_ids=_string_tuple(
                data.get("expected_ids", []), field_name="case.expected_ids"
            ),
            forbidden_ids=_string_tuple(
                data.get("forbidden_ids", []), field_name="case.forbidden_ids"
            ),
        )


@dataclass(frozen=True)
class RankedCandidate:
    candidate: RoutingCandidate
    score: float
    matched_terms: tuple[str, ...]
    prompt_text: str

    def to_dict(self) -> dict:
        return {
            "candidate_id": self.candidate.candidate_id,
            "kind": self.candidate.kind,
            "score": self.score,
            "matched_terms": list(self.matched_terms),
            "prompt_text": self.prompt_text,
        }


@dataclass(frozen=True)
class RoutingResult:
    query_id: str
    ranked: tuple[RankedCandidate, ...]
    rejected: dict[str, str]
    prompt_chars: int
    top_k: int
    prompt_budget_chars: int

    @property
    def selected_ids(self) -> tuple[str, ...]:
        return tuple(item.candidate.candidate_id for item in self.ranked)

    def to_dict(self) -> dict:
        return {
            "query_id": self.query_id,
            "selected_ids": list(self.selected_ids),
            "ranked": [item.to_dict() for item in self.ranked],
            "rejected": dict(sorted(self.rejected.items())),
            "prompt_chars": self.prompt_chars,
            "top_k": self.top_k,
            "prompt_budget_chars": self.prompt_budget_chars,
        }


def _contains_prompt_override(candidate: RoutingCandidate) -> bool:
    haystack = f"{candidate.summary} {candidate.content}".casefold()
    return any(pattern in haystack for pattern in PROMPT_OVERRIDE_PATTERNS)


def policy_denial(candidate: RoutingCandidate, query: RoutingQuery) -> str | None:
    """Return the first fail-closed denial before relevance scoring."""
    if candidate.status != "active":
        return f"status is {candidate.status}, not active"
    if not candidate.approved:
        return "candidate is not approved"
    if _contains_prompt_override(candidate):
        return "candidate contains a prompt override pattern"
    if candidate.user_scope not in (None, query.user_scope):
        return "user scope mismatch"
    if candidate.workspace_scope not in (None, query.workspace_scope):
        return "workspace scope mismatch"
    if candidate.task_family is not None and candidate.task_family != query.task_family:
        return "task family mismatch"
    if not set(candidate.permissions.tools).issubset(query.allowed_tools):
        return "required tools exceed the query grant"
    if candidate.permissions.network and not query.allow_network:
        return "network access exceeds the query grant"
    return None


class OfflineRouter:
    """Policy-first, explainable lexical router for heterogeneous candidates."""

    def __init__(self, candidates: Iterable[RoutingCandidate], *, min_score: float = 0.2):
        if not 0 < min_score <= 1:
            raise ValueError("min_score must be in (0, 1]")
        self.candidates = tuple(candidates)
        ids = [candidate.candidate_id for candidate in self.candidates]
        if len(ids) != len(set(ids)):
            raise RoutingContractError("candidate_id values must be unique")
        self.min_score = min_score

    def route(self, query: RoutingQuery) -> RoutingResult:
        query_terms = _tokenize(query.text)
        if not query_terms:
            raise RoutingContractError("query has no searchable terms")

        rejected: dict[str, str] = {}
        scored: list[tuple[float, str, RoutingCandidate, tuple[str, ...]]] = []
        for candidate in self.candidates:
            denial = policy_denial(candidate, query)
            if denial:
                rejected[candidate.candidate_id] = denial
                continue
            candidate_terms = _tokenize(candidate.searchable_text)
            matched = tuple(sorted(query_terms & candidate_terms))
            if not matched:
                rejected[candidate.candidate_id] = "no lexical overlap"
                continue
            coverage = len(matched) / len(query_terms)
            precision = len(matched) / max(len(candidate_terms), 1)
            score = round(0.8 * coverage + 0.2 * precision, 6)
            if score < self.min_score:
                rejected[candidate.candidate_id] = "score below abstention threshold"
                continue
            scored.append((score, candidate.candidate_id, candidate, matched))

        scored.sort(key=lambda item: (-item[0], item[1]))
        selected: list[RankedCandidate] = []
        prompt_chars = 0
        for score, _candidate_id, candidate, matched in scored:
            if len(selected) >= query.top_k:
                rejected[candidate.candidate_id] = "top-k limit reached"
                continue
            prompt_text = candidate.prompt_text
            separator = 1 if selected else 0
            if prompt_chars + separator + len(prompt_text) > query.prompt_budget_chars:
                rejected[candidate.candidate_id] = "prompt budget exceeded"
                continue
            selected.append(RankedCandidate(candidate, score, matched, prompt_text))
            prompt_chars += separator + len(prompt_text)

        return RoutingResult(
            query_id=query.query_id,
            ranked=tuple(selected),
            rejected=rejected,
            prompt_chars=prompt_chars,
            top_k=query.top_k,
            prompt_budget_chars=query.prompt_budget_chars,
        )


@dataclass(frozen=True)
class EvaluationMetrics:
    recall_at_k: float
    mrr: float
    false_positive_rate: float
    abstention_accuracy: float
    scope_leak_rate: float
    permission_leak_rate: float
    budget_violation_rate: float

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class EvaluationReport:
    metrics: EvaluationMetrics
    passed: bool
    case_results: tuple[dict, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict:
        return {
            "metrics": self.metrics.to_dict(),
            "passed": self.passed,
            "case_results": list(self.case_results),
        }


def evaluate(router: OfflineRouter, cases: Iterable[EvalCase]) -> EvaluationReport:
    cases = tuple(cases)
    if not cases:
        raise RoutingContractError("evaluation needs at least one case")

    relevant_cases = 0
    recall_sum = 0.0
    reciprocal_rank_sum = 0.0
    forbidden_total = 0
    forbidden_selected = 0
    abstention_cases = 0
    correct_abstentions = 0
    scope_leaks = 0
    permission_leaks = 0
    selected_total = 0
    budget_violations = 0
    case_results: list[dict] = []

    for case in cases:
        result = router.route(case.query)
        selected = result.selected_ids
        selected_set = set(selected)
        expected_set = set(case.expected_ids)
        forbidden_set = set(case.forbidden_ids)

        if expected_set:
            relevant_cases += 1
            recall_sum += len(selected_set & expected_set) / len(expected_set)
            ranks = [
                index
                for index, candidate_id in enumerate(selected, start=1)
                if candidate_id in expected_set
            ]
            reciprocal_rank_sum += 0.0 if not ranks else 1.0 / min(ranks)
        else:
            abstention_cases += 1
            correct_abstentions += int(not selected)

        forbidden_total += len(forbidden_set)
        forbidden_selected += len(selected_set & forbidden_set)
        selected_total += len(result.ranked)
        budget_violations += int(
            len(result.ranked) > case.query.top_k
            or result.prompt_chars > case.query.prompt_budget_chars
        )
        for ranked in result.ranked:
            candidate = ranked.candidate
            if candidate.user_scope not in (None, case.query.user_scope):
                scope_leaks += 1
            elif candidate.workspace_scope not in (None, case.query.workspace_scope):
                scope_leaks += 1
            elif (
                candidate.task_family is not None
                and candidate.task_family != case.query.task_family
            ):
                scope_leaks += 1
            if not set(candidate.permissions.tools).issubset(case.query.allowed_tools):
                permission_leaks += 1
            elif candidate.permissions.network and not case.query.allow_network:
                permission_leaks += 1

        case_results.append(
            {
                "case_id": case.query.query_id,
                "expected_ids": list(case.expected_ids),
                "forbidden_ids": list(case.forbidden_ids),
                **result.to_dict(),
            }
        )

    metrics = EvaluationMetrics(
        recall_at_k=round(recall_sum / relevant_cases, 6) if relevant_cases else 1.0,
        mrr=round(reciprocal_rank_sum / relevant_cases, 6) if relevant_cases else 1.0,
        false_positive_rate=round(forbidden_selected / forbidden_total, 6)
        if forbidden_total
        else 0.0,
        abstention_accuracy=round(correct_abstentions / abstention_cases, 6)
        if abstention_cases
        else 1.0,
        scope_leak_rate=round(scope_leaks / selected_total, 6)
        if selected_total
        else 0.0,
        permission_leak_rate=round(permission_leaks / selected_total, 6)
        if selected_total
        else 0.0,
        budget_violation_rate=round(budget_violations / len(cases), 6),
    )
    passed = (
        metrics.recall_at_k >= 0.9
        and metrics.mrr >= 0.9
        and metrics.false_positive_rate == 0
        and metrics.abstention_accuracy == 1
        and metrics.scope_leak_rate == 0
        and metrics.permission_leak_rate == 0
        and metrics.budget_violation_rate == 0
    )
    return EvaluationReport(metrics, passed, tuple(case_results))


def load_fixtures(path: Path = DEFAULT_FIXTURES) -> tuple[tuple[RoutingCandidate, ...], tuple[EvalCase, ...]]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    data = _strict_dict(payload, field_name="fixtures")
    _strict_keys(data, allowed={"candidates", "cases"}, field_name="fixtures")
    candidates_raw = data.get("candidates")
    cases_raw = data.get("cases")
    if not isinstance(candidates_raw, list) or not isinstance(cases_raw, list):
        raise RoutingContractError("fixtures candidates and cases must be lists")
    candidates = tuple(RoutingCandidate.from_dict(item) for item in candidates_raw)
    cases = tuple(EvalCase.from_dict(item) for item in cases_raw)
    known_ids = {candidate.candidate_id for candidate in candidates}
    for case in cases:
        unknown = (set(case.expected_ids) | set(case.forbidden_ids)) - known_ids
        if unknown:
            raise RoutingContractError(
                f"case {case.query.query_id} references unknown candidates: "
                + ", ".join(sorted(unknown))
            )
    return candidates, cases


def run_benchmark(fixtures: Path, output_dir: Path) -> dict:
    candidates, cases = load_fixtures(fixtures)
    report = evaluate(OfflineRouter(candidates), cases)
    output_dir.mkdir(parents=True, exist_ok=True)
    report_path = output_dir / "retrieval-routing-report.json"
    report_path.write_text(
        json.dumps(report.to_dict(), ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return {
        "fixtures": str(Path(fixtures).resolve()),
        "report_path": str(report_path.resolve()),
        "candidate_count": len(candidates),
        "case_count": len(cases),
        **report.to_dict(),
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run the offline Skill/Memory/Reflection routing benchmark."
    )
    parser.add_argument("--fixtures", type=Path, default=DEFAULT_FIXTURES)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    manifest = run_benchmark(args.fixtures, args.output_dir)
    print("Retrieval and routing evaluation")
    print("Candidates:", manifest["candidate_count"])
    print("Cases:", manifest["case_count"])
    for name, value in manifest["metrics"].items():
        print(f"{name}: {value:.6f}")
    print("Passed:", manifest["passed"])
    print("Report:", manifest["report_path"])
    return 0 if manifest["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
