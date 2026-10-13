#!/usr/bin/env python3
"""离线验证回答中的 claim、citation 与本轮 evidence set 是否一致。"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from types import ModuleType
from typing import Iterable, Mapping


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

RAG_CODE = ROOT / "examples" / "source_grounded_rag" / "code.py"
DEFAULT_CORPUS = ROOT / "examples" / "source_grounded_rag" / "fixtures" / "corpus"
DEFAULT_CASES = Path(__file__).parent / "fixtures" / "cases.json"
DEFAULT_OUTPUT = ROOT / ".tmp" / "answer-grounding-eval"
MAX_CLAIM_CHARS = 1_000
MAX_QUOTE_CHARS = 500


class GroundingContractError(ValueError):
    """回答、引用或评测 fixture 不满足公开契约。"""


def _require_text(
    value: object,
    *,
    field_name: str,
    max_chars: int,
    collapse_whitespace: bool = True,
) -> str:
    if not isinstance(value, str):
        raise GroundingContractError(f"{field_name} must be a string")
    text = value.strip()
    if collapse_whitespace:
        text = " ".join(text.split())
    if not text:
        raise GroundingContractError(f"{field_name} must not be empty")
    if len(text) > max_chars:
        raise GroundingContractError(
            f"{field_name} exceeds {max_chars} characters"
        )
    return text


def _object(value: object, *, field_name: str) -> dict[str, object]:
    if not isinstance(value, dict):
        raise GroundingContractError(f"{field_name} must be an object")
    return value


def _only_fields(
    payload: Mapping[str, object], allowed: set[str], *, field_name: str
) -> None:
    unknown = sorted(set(payload) - allowed)
    if unknown:
        raise GroundingContractError(
            f"{field_name} has unknown fields: {', '.join(unknown)}"
        )


def _normalize_claim(text: str) -> str:
    return " ".join(text.casefold().split())


def _load_rag() -> ModuleType:
    name = "_learn_workbuddy_answer_grounding_rag"
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, RAG_CODE)
    if spec is None or spec.loader is None:
        raise GroundingContractError(f"cannot load RAG module: {RAG_CODE}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    try:
        spec.loader.exec_module(module)
    except BaseException:
        sys.modules.pop(name, None)
        raise
    return module


@dataclass(frozen=True)
class EvidenceRecord:
    label: str
    chunk_id: str
    source_path: str
    citation: str
    content_hash: str
    text: str

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class EvidenceSet:
    evidence_set_id: str
    query: str
    records: tuple[EvidenceRecord, ...]

    @classmethod
    def from_search_result(cls, result: object) -> "EvidenceSet":
        records = tuple(
            EvidenceRecord(
                label=hit.label,
                chunk_id=hit.chunk.chunk_id,
                source_path=hit.chunk.source_path,
                citation=hit.chunk.citation,
                content_hash=hit.chunk.content_hash,
                text=hit.chunk.text,
            )
            for hit in result.hits
        )
        labels = [record.label for record in records]
        if len(labels) != len(set(labels)):
            raise GroundingContractError("evidence labels must be unique")
        material = {
            "query": result.query,
            "records": [
                {
                    "label": record.label,
                    "chunk_id": record.chunk_id,
                    "citation": record.citation,
                    "content_hash": record.content_hash,
                }
                for record in records
            ],
        }
        digest = hashlib.sha256(
            json.dumps(
                material,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()[:24]
        return cls(f"evidence_{digest}", result.query, records)

    def to_dict(self) -> dict[str, object]:
        return {
            "evidence_set_id": self.evidence_set_id,
            "query": self.query,
            "records": [record.to_dict() for record in self.records],
        }


@dataclass(frozen=True)
class CitationRef:
    label: str
    citation: str
    quote: str

    @classmethod
    def from_dict(cls, value: object) -> "CitationRef":
        payload = _object(value, field_name="citation")
        _only_fields(
            payload, {"label", "citation", "quote"}, field_name="citation"
        )
        return cls(
            label=_require_text(
                payload.get("label"), field_name="citation.label", max_chars=40
            ),
            citation=_require_text(
                payload.get("citation"),
                field_name="citation.citation",
                max_chars=300,
            ),
            quote=_require_text(
                payload.get("quote"),
                field_name="citation.quote",
                max_chars=MAX_QUOTE_CHARS,
                collapse_whitespace=False,
            ),
        )


@dataclass(frozen=True)
class AnswerClaim:
    claim_id: str
    text: str
    citations: tuple[CitationRef, ...]

    @classmethod
    def from_dict(cls, value: object) -> "AnswerClaim":
        payload = _object(value, field_name="claim")
        _only_fields(payload, {"claim_id", "text", "citations"}, field_name="claim")
        citations = payload.get("citations")
        if not isinstance(citations, list):
            raise GroundingContractError("claim.citations must be an array")
        return cls(
            claim_id=_require_text(
                payload.get("claim_id"), field_name="claim.claim_id", max_chars=80
            ),
            text=_require_text(
                payload.get("text"),
                field_name="claim.text",
                max_chars=MAX_CLAIM_CHARS,
            ),
            citations=tuple(CitationRef.from_dict(item) for item in citations),
        )


@dataclass(frozen=True)
class GroundedAnswer:
    evidence_set_id: str
    claims: tuple[AnswerClaim, ...]
    abstained: bool
    abstention_reason: str | None

    @classmethod
    def from_dict(cls, value: object) -> "GroundedAnswer":
        payload = _object(value, field_name="answer")
        _only_fields(
            payload,
            {"evidence_set_id", "claims", "abstained", "abstention_reason"},
            field_name="answer",
        )
        claims = payload.get("claims")
        if not isinstance(claims, list):
            raise GroundingContractError("answer.claims must be an array")
        parsed = tuple(AnswerClaim.from_dict(item) for item in claims)
        claim_ids = [claim.claim_id for claim in parsed]
        if len(claim_ids) != len(set(claim_ids)):
            raise GroundingContractError("answer claim_id values must be unique")
        abstained = payload.get("abstained")
        if not isinstance(abstained, bool):
            raise GroundingContractError("answer.abstained must be a boolean")
        reason = payload.get("abstention_reason")
        if reason is not None:
            reason = _require_text(
                reason, field_name="answer.abstention_reason", max_chars=500
            )
        return cls(
            evidence_set_id=_require_text(
                payload.get("evidence_set_id"),
                field_name="answer.evidence_set_id",
                max_chars=100,
            ),
            claims=parsed,
            abstained=abstained,
            abstention_reason=reason,
        )

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class VerificationIssue:
    code: str
    detail: str
    claim_id: str | None = None
    citation_label: str | None = None


@dataclass(frozen=True)
class VerificationReport:
    passed: bool
    issues: tuple[VerificationIssue, ...]
    claim_count: int
    cited_claims: int
    citation_count: int
    valid_citations: int

    def to_dict(self) -> dict[str, object]:
        return {
            "passed": self.passed,
            "issues": [asdict(issue) for issue in self.issues],
            "claim_count": self.claim_count,
            "cited_claims": self.cited_claims,
            "citation_count": self.citation_count,
            "valid_citations": self.valid_citations,
        }


class AnswerVerifier:
    """只验证可确定的 Harness 事实，不声称判断自然语言蕴含。"""

    def __init__(self, index: object, evidence_set: EvidenceSet):
        self.index = index
        self.evidence_set = evidence_set

    def verify(self, answer: GroundedAnswer) -> VerificationReport:
        issues: list[VerificationIssue] = []
        records = {record.label: record for record in self.evidence_set.records}
        chunks = {chunk.chunk_id: chunk for chunk in self.index.chunks}
        cited_claims = 0
        citation_count = 0
        valid_citations = 0

        if answer.evidence_set_id != self.evidence_set.evidence_set_id:
            issues.append(
                VerificationIssue(
                    "evidence_set_mismatch",
                    "answer was not bound to the current query evidence set",
                )
            )
        if answer.abstained:
            if answer.claims:
                issues.append(
                    VerificationIssue(
                        "abstention_has_claims",
                        "an abstention cannot also assert factual claims",
                    )
                )
            if not answer.abstention_reason:
                issues.append(
                    VerificationIssue(
                        "missing_abstention_reason",
                        "an abstention needs an explicit reason",
                    )
                )
        else:
            if not answer.claims:
                issues.append(
                    VerificationIssue(
                        "empty_answer", "a non-abstaining answer needs at least one claim"
                    )
                )
            if answer.abstention_reason:
                issues.append(
                    VerificationIssue(
                        "unexpected_abstention_reason",
                        "a non-abstaining answer cannot carry an abstention reason",
                    )
                )

        for claim in answer.claims:
            if not claim.citations:
                issues.append(
                    VerificationIssue(
                        "uncited_claim",
                        "every factual claim needs at least one citation",
                        claim_id=claim.claim_id,
                    )
                )
                continue
            cited_claims += 1
            seen_refs: set[tuple[str, str, str]] = set()
            for ref in claim.citations:
                citation_count += 1
                identity = (ref.label, ref.citation, ref.quote)
                if identity in seen_refs:
                    issues.append(
                        VerificationIssue(
                            "duplicate_citation",
                            "the same citation cannot inflate claim support",
                            claim_id=claim.claim_id,
                            citation_label=ref.label,
                        )
                    )
                    continue
                seen_refs.add(identity)
                record = records.get(ref.label)
                if record is None:
                    issues.append(
                        VerificationIssue(
                            "unknown_citation",
                            "citation label was not selected into the current prompt",
                            claim_id=claim.claim_id,
                            citation_label=ref.label,
                        )
                    )
                    continue
                if ref.citation != record.citation:
                    issues.append(
                        VerificationIssue(
                            "citation_metadata_mismatch",
                            "citation path or line range does not match its label",
                            claim_id=claim.claim_id,
                            citation_label=ref.label,
                        )
                    )
                    continue
                chunk = chunks.get(record.chunk_id)
                if chunk is None:
                    issues.append(
                        VerificationIssue(
                            "missing_evidence_chunk",
                            "selected evidence no longer exists in the active index",
                            claim_id=claim.claim_id,
                            citation_label=ref.label,
                        )
                    )
                    continue
                fresh, reason = self.index.validate_chunk(chunk)
                if not fresh:
                    issues.append(
                        VerificationIssue(
                            "stale_evidence",
                            reason,
                            claim_id=claim.claim_id,
                            citation_label=ref.label,
                        )
                    )
                    continue
                if ref.quote not in record.text:
                    issues.append(
                        VerificationIssue(
                            "quote_not_in_evidence",
                            "supporting quote is not an exact span of the cited evidence",
                            claim_id=claim.claim_id,
                            citation_label=ref.label,
                        )
                    )
                    continue
                valid_citations += 1

        return VerificationReport(
            passed=not issues,
            issues=tuple(issues),
            claim_count=len(answer.claims),
            cited_claims=cited_claims,
            citation_count=citation_count,
            valid_citations=valid_citations,
        )


@dataclass(frozen=True)
class CitationSpec:
    source_path: str
    quote: str
    label: str | None = None
    citation: str | None = None

    @classmethod
    def from_dict(cls, value: object) -> "CitationSpec":
        payload = _object(value, field_name="citation_spec")
        _only_fields(
            payload,
            {"source_path", "quote", "label", "citation"},
            field_name="citation_spec",
        )
        label = payload.get("label")
        citation = payload.get("citation")
        return cls(
            source_path=_require_text(
                payload.get("source_path"),
                field_name="citation_spec.source_path",
                max_chars=300,
            ),
            quote=_require_text(
                payload.get("quote"),
                field_name="citation_spec.quote",
                max_chars=MAX_QUOTE_CHARS,
                collapse_whitespace=False,
            ),
            label=(
                None
                if label is None
                else _require_text(label, field_name="citation_spec.label", max_chars=40)
            ),
            citation=(
                None
                if citation is None
                else _require_text(
                    citation, field_name="citation_spec.citation", max_chars=300
                )
            ),
        )


@dataclass(frozen=True)
class ClaimSpec:
    claim_id: str
    text: str
    citations: tuple[CitationSpec, ...]

    @classmethod
    def from_dict(cls, value: object) -> "ClaimSpec":
        payload = _object(value, field_name="claim_spec")
        _only_fields(
            payload, {"claim_id", "text", "citations"}, field_name="claim_spec"
        )
        citations = payload.get("citations")
        if not isinstance(citations, list):
            raise GroundingContractError("claim_spec.citations must be an array")
        return cls(
            claim_id=_require_text(
                payload.get("claim_id"), field_name="claim_spec.claim_id", max_chars=80
            ),
            text=_require_text(
                payload.get("text"),
                field_name="claim_spec.text",
                max_chars=MAX_CLAIM_CHARS,
            ),
            citations=tuple(CitationSpec.from_dict(item) for item in citations),
        )


@dataclass(frozen=True)
class AnswerSpec:
    claims: tuple[ClaimSpec, ...]
    abstained: bool
    abstention_reason: str | None
    evidence_set_override: str | None = None

    @classmethod
    def from_dict(cls, value: object) -> "AnswerSpec":
        payload = _object(value, field_name="answer_spec")
        _only_fields(
            payload,
            {"claims", "abstained", "abstention_reason", "evidence_set_override"},
            field_name="answer_spec",
        )
        claims = payload.get("claims")
        if not isinstance(claims, list):
            raise GroundingContractError("answer_spec.claims must be an array")
        abstained = payload.get("abstained")
        if not isinstance(abstained, bool):
            raise GroundingContractError("answer_spec.abstained must be a boolean")
        reason = payload.get("abstention_reason")
        override = payload.get("evidence_set_override")
        return cls(
            claims=tuple(ClaimSpec.from_dict(item) for item in claims),
            abstained=abstained,
            abstention_reason=(
                None
                if reason is None
                else _require_text(
                    reason, field_name="answer_spec.abstention_reason", max_chars=500
                )
            ),
            evidence_set_override=(
                None
                if override is None
                else _require_text(
                    override,
                    field_name="answer_spec.evidence_set_override",
                    max_chars=100,
                )
            ),
        )


@dataclass(frozen=True)
class GoldClaim:
    text: str
    sources: tuple[str, ...]

    @classmethod
    def from_dict(cls, value: object) -> "GoldClaim":
        payload = _object(value, field_name="gold_claim")
        _only_fields(payload, {"text", "sources"}, field_name="gold_claim")
        sources = payload.get("sources")
        if not isinstance(sources, list) or not sources:
            raise GroundingContractError("gold_claim.sources must be a non-empty array")
        return cls(
            text=_require_text(
                payload.get("text"), field_name="gold_claim.text", max_chars=MAX_CLAIM_CHARS
            ),
            sources=tuple(
                _require_text(item, field_name="gold_claim.source", max_chars=300)
                for item in sources
            ),
        )


@dataclass(frozen=True)
class AnswerEvalCase:
    case_id: str
    query: str
    expected_sources: tuple[str, ...]
    should_abstain: bool
    answer: AnswerSpec
    gold_claims: tuple[GoldClaim, ...]
    expected_pass: bool
    expected_issue_codes: tuple[str, ...]
    top_k: int = 2
    prompt_budget_chars: int = 1_800

    @classmethod
    def from_dict(cls, value: object) -> "AnswerEvalCase":
        payload = _object(value, field_name="case")
        allowed = {
            "case_id",
            "query",
            "expected_sources",
            "should_abstain",
            "answer",
            "gold_claims",
            "expected_pass",
            "expected_issue_codes",
            "top_k",
            "prompt_budget_chars",
        }
        _only_fields(payload, allowed, field_name="case")
        expected_sources = payload.get("expected_sources")
        gold_claims = payload.get("gold_claims")
        issue_codes = payload.get("expected_issue_codes")
        if not isinstance(expected_sources, list):
            raise GroundingContractError("case.expected_sources must be an array")
        if not isinstance(gold_claims, list):
            raise GroundingContractError("case.gold_claims must be an array")
        if not isinstance(issue_codes, list):
            raise GroundingContractError("case.expected_issue_codes must be an array")
        should_abstain = payload.get("should_abstain")
        expected_pass = payload.get("expected_pass")
        if not isinstance(should_abstain, bool) or not isinstance(expected_pass, bool):
            raise GroundingContractError(
                "case.should_abstain and case.expected_pass must be booleans"
            )
        top_k = int(payload.get("top_k", 2))
        budget = int(payload.get("prompt_budget_chars", 1_800))
        if not 1 <= top_k <= 20 or budget < 1:
            raise GroundingContractError("case retrieval limits are invalid")
        parsed_gold = tuple(GoldClaim.from_dict(item) for item in gold_claims)
        if should_abstain and parsed_gold:
            raise GroundingContractError("abstention case cannot declare gold claims")
        return cls(
            case_id=_require_text(
                payload.get("case_id"), field_name="case.case_id", max_chars=100
            ),
            query=_require_text(
                payload.get("query"), field_name="case.query", max_chars=1_000
            ),
            expected_sources=tuple(
                _require_text(item, field_name="case.expected_source", max_chars=300)
                for item in expected_sources
            ),
            should_abstain=should_abstain,
            answer=AnswerSpec.from_dict(payload.get("answer")),
            gold_claims=parsed_gold,
            expected_pass=expected_pass,
            expected_issue_codes=tuple(
                _require_text(item, field_name="case.issue_code", max_chars=100)
                for item in issue_codes
            ),
            top_k=top_k,
            prompt_budget_chars=budget,
        )


def load_cases(path: Path) -> tuple[AnswerEvalCase, ...]:
    try:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise GroundingContractError(f"cannot read cases: {exc}") from exc
    document = _object(payload, field_name="fixture")
    _only_fields(document, {"cases"}, field_name="fixture")
    cases = document.get("cases")
    if not isinstance(cases, list) or not cases:
        raise GroundingContractError("fixture.cases must be a non-empty array")
    parsed = tuple(AnswerEvalCase.from_dict(item) for item in cases)
    case_ids = [case.case_id for case in parsed]
    if len(case_ids) != len(set(case_ids)):
        raise GroundingContractError("case_id values must be unique")
    return parsed


def materialize_answer(spec: AnswerSpec, evidence_set: EvidenceSet) -> GroundedAnswer:
    """把可读 fixture source_path 解析为模型实际看到的 label/citation。"""

    claims: list[dict[str, object]] = []
    for claim in spec.claims:
        citations: list[dict[str, str]] = []
        for citation_spec in claim.citations:
            matching = [
                record
                for record in evidence_set.records
                if record.source_path == citation_spec.source_path
                and citation_spec.quote in record.text
            ]
            if not matching:
                matching = [
                    record
                    for record in evidence_set.records
                    if record.source_path == citation_spec.source_path
                ]
            record = matching[0] if matching else None
            citations.append(
                {
                    "label": citation_spec.label
                    or (record.label if record is not None else "S999"),
                    "citation": citation_spec.citation
                    or (
                        record.citation
                        if record is not None
                        else f"{citation_spec.source_path}#L1-L1"
                    ),
                    "quote": citation_spec.quote,
                }
            )
        claims.append(
            {
                "claim_id": claim.claim_id,
                "text": claim.text,
                "citations": citations,
            }
        )
    return GroundedAnswer.from_dict(
        {
            "evidence_set_id": spec.evidence_set_override
            or evidence_set.evidence_set_id,
            "claims": claims,
            "abstained": spec.abstained,
            "abstention_reason": spec.abstention_reason,
        }
    )


@dataclass(frozen=True)
class GoldReport:
    passed: bool
    issues: tuple[VerificationIssue, ...]
    supported_claims: int
    aligned_claims: int

    def to_dict(self) -> dict[str, object]:
        return {
            "passed": self.passed,
            "issues": [asdict(issue) for issue in self.issues],
            "supported_claims": self.supported_claims,
            "aligned_claims": self.aligned_claims,
        }


def evaluate_gold_alignment(
    answer: GroundedAnswer,
    case: AnswerEvalCase,
    evidence_set: EvidenceSet,
) -> GoldReport:
    """用显式 fixture gold 检查语义；不把 runtime verifier 冒充 judge。"""

    issues: list[VerificationIssue] = []
    records = {record.label: record for record in evidence_set.records}
    gold = {_normalize_claim(item.text): item for item in case.gold_claims}
    seen: set[str] = set()
    supported = 0
    aligned = 0

    if case.should_abstain:
        if not answer.abstained:
            issues.append(
                VerificationIssue(
                    "expected_abstention",
                    "the fixture contains no answerable evidence",
                )
            )
        return GoldReport(not issues, tuple(issues), 0, 0)
    if answer.abstained:
        issues.append(
            VerificationIssue(
                "unexpected_abstention", "the fixture contains supported gold claims"
            )
        )

    for claim in answer.claims:
        normalized = _normalize_claim(claim.text)
        expected = gold.get(normalized)
        if expected is None:
            issues.append(
                VerificationIssue(
                    "unsupported_claim",
                    "claim text is not present in the explicit benchmark gold set",
                    claim_id=claim.claim_id,
                )
            )
            continue
        supported += 1
        seen.add(normalized)
        cited_sources = {
            records[ref.label].source_path
            for ref in claim.citations
            if ref.label in records
        }
        if not cited_sources or not cited_sources.issubset(set(expected.sources)):
            issues.append(
                VerificationIssue(
                    "wrong_gold_source",
                    "claim citations do not align with its fixture support sources",
                    claim_id=claim.claim_id,
                )
            )
            continue
        aligned += 1

    for normalized, expected in gold.items():
        if normalized not in seen:
            issues.append(
                VerificationIssue(
                    "missing_expected_claim",
                    f"answer omitted supported claim: {expected.text}",
                )
            )
    return GoldReport(not issues, tuple(issues), supported, aligned)


@dataclass(frozen=True)
class CaseResult:
    case_id: str
    expected_pass: bool
    observed_pass: bool
    expectation_met: bool
    expected_issue_codes: tuple[str, ...]
    observed_issue_codes: tuple[str, ...]
    expected_sources_retrieved: bool
    search: dict[str, object]
    evidence_set: dict[str, object]
    answer: dict[str, object]
    runtime_verification: dict[str, object]
    gold_evaluation: dict[str, object]

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class EvaluationMetrics:
    verdict_accuracy: float
    claim_citation_coverage: float
    citation_validity_rate: float
    gold_source_alignment: float
    unsupported_claim_rate: float
    negative_abstention_accuracy: float
    adversarial_rejection_rate: float
    deterministic_replay: float


@dataclass(frozen=True)
class EvaluationReport:
    passed: bool
    metrics: EvaluationMetrics
    cases: tuple[CaseResult, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "passed": self.passed,
            "metrics": asdict(self.metrics),
            "cases": [case.to_dict() for case in self.cases],
        }


def _rate(numerator: int, denominator: int, *, empty: float) -> float:
    return round(numerator / denominator, 6) if denominator else empty


def evaluate(
    index: object, cases: Iterable[AnswerEvalCase], *, rag: ModuleType | None = None
) -> EvaluationReport:
    rag = rag or _load_rag()
    parsed_cases = tuple(cases)
    if not parsed_cases:
        raise GroundingContractError("evaluation needs at least one case")
    retriever = rag.OfflineBM25Retriever(index)
    results: list[CaseResult] = []
    valid_claims = cited_valid_claims = valid_citations = citations = 0
    gold_claims = aligned_claims = 0
    unsupported_accepted = accepted_claims = 0
    negative_total = negative_correct = 0
    adversarial_total = adversarial_rejected = 0
    deterministic = True

    for case in parsed_cases:
        search = retriever.search(
            case.query,
            top_k=case.top_k,
            prompt_budget_chars=case.prompt_budget_chars,
        )
        evidence_set = EvidenceSet.from_search_result(search)
        answer = materialize_answer(case.answer, evidence_set)
        verifier = AnswerVerifier(index, evidence_set)
        runtime = verifier.verify(answer)
        replay = verifier.verify(answer)
        deterministic = deterministic and runtime.to_dict() == replay.to_dict()
        gold_report = evaluate_gold_alignment(answer, case, evidence_set)
        retrieved_sources = {record.source_path for record in evidence_set.records}
        sources_ok = set(case.expected_sources).issubset(retrieved_sources)
        observed_codes = {
            issue.code for issue in (*runtime.issues, *gold_report.issues)
        }
        if not sources_ok:
            observed_codes.add("expected_source_not_retrieved")
        observed_pass = runtime.passed and gold_report.passed and sources_ok
        issues_ok = set(case.expected_issue_codes).issubset(observed_codes)
        expectation_met = observed_pass == case.expected_pass and issues_ok

        if case.expected_pass and not case.should_abstain:
            valid_claims += runtime.claim_count
            cited_valid_claims += runtime.cited_claims
            citations += runtime.citation_count
            valid_citations += runtime.valid_citations
            gold_claims += len(case.gold_claims)
            aligned_claims += gold_report.aligned_claims
        if observed_pass:
            accepted_claims += runtime.claim_count
            unsupported_accepted += sum(
                issue.code == "unsupported_claim" for issue in gold_report.issues
            )
        if case.should_abstain:
            negative_total += 1
            negative_correct += int(
                (answer.abstained and observed_pass)
                or (not answer.abstained and not observed_pass)
            )
        if not case.expected_pass:
            adversarial_total += 1
            adversarial_rejected += int(not observed_pass)

        results.append(
            CaseResult(
                case_id=case.case_id,
                expected_pass=case.expected_pass,
                observed_pass=observed_pass,
                expectation_met=expectation_met,
                expected_issue_codes=case.expected_issue_codes,
                observed_issue_codes=tuple(sorted(observed_codes)),
                expected_sources_retrieved=sources_ok,
                search=search.to_dict(),
                evidence_set=evidence_set.to_dict(),
                answer=answer.to_dict(),
                runtime_verification=runtime.to_dict(),
                gold_evaluation=gold_report.to_dict(),
            )
        )

    metrics = EvaluationMetrics(
        verdict_accuracy=_rate(
            sum(result.expectation_met for result in results), len(results), empty=0.0
        ),
        claim_citation_coverage=_rate(
            cited_valid_claims, valid_claims, empty=1.0
        ),
        citation_validity_rate=_rate(valid_citations, citations, empty=1.0),
        gold_source_alignment=_rate(aligned_claims, gold_claims, empty=1.0),
        unsupported_claim_rate=_rate(
            unsupported_accepted, accepted_claims, empty=0.0
        ),
        negative_abstention_accuracy=_rate(
            negative_correct, negative_total, empty=1.0
        ),
        adversarial_rejection_rate=_rate(
            adversarial_rejected, adversarial_total, empty=1.0
        ),
        deterministic_replay=float(deterministic),
    )
    passed = (
        metrics.verdict_accuracy == 1
        and metrics.claim_citation_coverage == 1
        and metrics.citation_validity_rate == 1
        and metrics.gold_source_alignment == 1
        and metrics.unsupported_claim_rate == 0
        and metrics.negative_abstention_accuracy == 1
        and metrics.adversarial_rejection_rate == 1
        and metrics.deterministic_replay == 1
    )
    return EvaluationReport(passed, metrics, tuple(results))


def run_evaluation(
    corpus: Path,
    cases_path: Path,
    output_dir: Path,
    *,
    rag: ModuleType | None = None,
) -> dict[str, object]:
    rag = rag or _load_rag()
    output_dir = Path(output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    index = rag.SourceIndex(Path(corpus), output_dir / "source-index.json")
    sync_report = index.sync()
    report = evaluate(index, load_cases(cases_path), rag=rag)
    manifest: dict[str, object] = {
        "ok": report.passed,
        "index_sync": asdict(sync_report),
        **report.to_dict(),
        "artifacts": {
            "source_index": str(index.index_path.resolve()),
        },
    }
    report_path = output_dir / "answer-grounding-report.json"
    manifest["artifacts"]["report"] = str(report_path.resolve())
    report_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Evaluate answer claims against the exact evidence selected for one query."
    )
    parser.add_argument("--corpus", type=Path, default=DEFAULT_CORPUS)
    parser.add_argument("--cases", type=Path, default=DEFAULT_CASES)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()

    manifest = run_evaluation(args.corpus, args.cases, args.output_dir)
    metrics = manifest["metrics"]
    cases = manifest["cases"]
    print("[1] Source-grounded retrieval")
    print(f"    cases={len(cases)}; each answer binds to a deterministic evidence_set_id")
    print("[2] Runtime citation integrity")
    print(
        "    coverage="
        f"{metrics['claim_citation_coverage']:.3f}; "
        f"validity={metrics['citation_validity_rate']:.3f}"
    )
    print("[3] Fixture-backed claim alignment")
    print(
        f"    gold_alignment={metrics['gold_source_alignment']:.3f}; "
        f"unsupported_rate={metrics['unsupported_claim_rate']:.3f}"
    )
    print("[4] Abstention and adversarial cases")
    print(
        f"    abstention={metrics['negative_abstention_accuracy']:.3f}; "
        f"rejection={metrics['adversarial_rejection_rate']:.3f}"
    )
    print(f"[5] Report\n    {manifest['artifacts']['report']}")
    print("RESULT: OK" if manifest["ok"] else "RESULT: FAILED")
    return 0 if manifest["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
