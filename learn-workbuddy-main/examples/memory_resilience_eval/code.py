#!/usr/bin/env python3
"""Offline fault-injection scorecard for the existing S12 Memory contract.

This example does not own another storage or retrieval implementation.  It
loads S12 as the authoritative chapter, drives its public RemoteMemoryStore
and RecallEngine APIs, and records whether durable-state failures are handled
atomically, explicitly, and without provider access.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import sys
import tempfile
import threading
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from types import ModuleType
from typing import Callable, Mapping


ROOT = Path(__file__).resolve().parents[2]
S12_CODE = ROOT / "s12_cloud_memory" / "code.py"
DEFAULT_OUTPUT = ROOT / ".tmp" / "memory-resilience-eval"
REPORT_NAME = "memory-resilience-report.json"

CAPTURED_AT = "2026-08-01T12:00:00Z"
STORED_AT = datetime(2026, 8, 1, 12, tzinfo=timezone.utc)
RECALL_AS_OF = datetime(2026, 8, 24, 12, tzinfo=timezone.utc)


@dataclass(frozen=True)
class CaseObservation:
    """One runner's explicit verdict and the evidence needed to inspect it."""

    passed: bool
    observed: str
    evidence: Mapping[str, object]


CaseRunner = Callable[[ModuleType, Path], CaseObservation]


@dataclass(frozen=True)
class CaseDefinition:
    """A failure scenario paired with the invariant it must preserve."""

    case_id: str
    contract: str
    runner: CaseRunner


@dataclass(frozen=True)
class CaseResult:
    """Serializable result kept separate from the executable case function."""

    case_id: str
    contract: str
    passed: bool
    observed: str
    evidence: Mapping[str, object]

    def to_dict(self) -> dict[str, object]:
        return {
            "case_id": self.case_id,
            "contract": self.contract,
            "passed": self.passed,
            "observed": self.observed,
            "evidence": dict(self.evidence),
        }


@dataclass(frozen=True)
class EvaluationReport:
    """Binary contract gates; safety failures cannot be averaged away."""

    cases: tuple[CaseResult, ...]
    report_path: str

    @property
    def passed(self) -> bool:
        return bool(self.cases) and all(case.passed for case in self.cases)

    @property
    def summary(self) -> dict[str, int]:
        passed = sum(case.passed for case in self.cases)
        return {
            "total": len(self.cases),
            "passed": passed,
            "failed": len(self.cases) - passed,
        }

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": 1,
            "evaluation": "memory_resilience",
            "chapter_contract": "s12_cloud_memory",
            "passed": self.passed,
            "summary": self.summary,
            "cases": [case.to_dict() for case in self.cases],
            "report_path": self.report_path,
        }


def load_memory_chapter() -> ModuleType:
    """Load the existing S12 entrypoint without constructing a model client."""

    module_name = "_learn_workbuddy_memory_resilience_s12"
    cached = sys.modules.get(module_name)
    if cached is not None:
        return cached
    spec = importlib.util.spec_from_file_location(module_name, S12_CODE)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load Memory chapter: {S12_CODE}")
    module = importlib.util.module_from_spec(spec)
    # Dataclasses consult sys.modules while the chapter executes.
    sys.modules[module_name] = module
    try:
        spec.loader.exec_module(module)
    except Exception:
        sys.modules.pop(module_name, None)
        raise
    return module


def _source(chapter: ModuleType, source_id: str, title: str):
    return chapter.MemorySource(
        source_id=source_id,
        source_type="memory_resilience_eval",
        title=title,
        captured_at=CAPTURED_AT,
    )


def _append(
    chapter: ModuleType,
    store,
    *,
    memory_id: str,
    content: str,
    source_id: str,
    title: str,
):
    """Create one fixed-time record so fault observations stay reproducible."""

    return store.append(
        kind=chapter.MemoryKind.CONVERSATION,
        content=content,
        summary=content,
        source=_source(chapter, source_id, title),
        memory_id=memory_id,
        stored_at=STORED_AT,
    )


def _concurrent_duplicate_write(
    chapter: ModuleType, case_dir: Path
) -> CaseObservation:
    """Race identical appends and require one durable winner."""

    workers = 8
    path = case_dir / "concurrent.jsonl"
    store = chapter.RemoteMemoryStore(path, user_id="alice")
    barrier = threading.Barrier(workers)
    statuses: list[str] = []
    statuses_lock = threading.Lock()

    def writer() -> None:
        barrier.wait()
        try:
            _append(
                chapter,
                store,
                memory_id="mem-concurrent",
                content="Concurrent retries preserve one immutable memory fact.",
                source_id="src-concurrent",
                title="Concurrent retry policy",
            )
        except chapter.RemoteMemoryDuplicateError:
            status = "duplicate_rejected"
        else:
            status = "created"
        with statuses_lock:
            statuses.append(status)

    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = [executor.submit(writer) for _ in range(workers)]
        for future in futures:
            future.result()

    counts = Counter(statuses)
    records = store.read_all()
    passed = (
        counts["created"] == 1
        and counts["duplicate_rejected"] == workers - 1
        and len(records) == 1
        and records[0].memory_id == "mem-concurrent"
    )
    return CaseObservation(
        passed=passed,
        observed="one_winner" if passed else "non_atomic_outcome",
        evidence={
            "writers": workers,
            "created": counts["created"],
            "duplicates_rejected": counts["duplicate_rejected"],
            "durable_records": len(records),
            "winning_memory_id": records[0].memory_id if records else None,
        },
    )


def _id_collision(chapter: ModuleType, case_dir: Path) -> CaseObservation:
    """Prove that a stable identity cannot authorize a different payload."""

    store = chapter.RemoteMemoryStore(case_dir / "collision.jsonl", user_id="alice")
    original = "Approved deployment policy requires verification before publish."
    conflicting = "Publishing may skip verification."
    _append(
        chapter,
        store,
        memory_id="mem-policy",
        content=original,
        source_id="src-policy",
        title="Deployment policy",
    )
    rejected_error: str | None = None
    try:
        _append(
            chapter,
            store,
            memory_id="mem-policy",
            content=conflicting,
            source_id="src-conflict",
            title="Conflicting deployment policy",
        )
    except chapter.RemoteMemoryDuplicateError as exc:
        rejected_error = type(exc).__name__

    records = store.read_all()
    passed = (
        rejected_error == "RemoteMemoryDuplicateError"
        and len(records) == 1
        and records[0].content == original
        and records[0].source.source_id == "src-policy"
    )
    return CaseObservation(
        passed=passed,
        observed="collision_rejected" if passed else "collision_accepted",
        evidence={
            "rejected_error": rejected_error,
            "durable_records": len(records),
            "retained_content": records[0].content if records else None,
            "retained_source_id": records[0].source.source_id if records else None,
        },
    )


def _scope_isolation(chapter: ModuleType, case_dir: Path) -> CaseObservation:
    """Use one physical path and require a mismatched user to fail closed."""

    path = case_dir / "shared-path.jsonl"
    alice = chapter.RemoteMemoryStore(path, user_id="alice")
    _append(
        chapter,
        alice,
        memory_id="mem-private",
        content="Alice keeps a private workspace preference.",
        source_id="src-private",
        title="Private preference",
    )
    rejected_error: str | None = None
    try:
        chapter.RemoteMemoryStore(path, user_id="bob").read_all()
    except chapter.RemoteMemoryScopeError as exc:
        rejected_error = type(exc).__name__

    alice_records = alice.read_all()
    passed = rejected_error == "RemoteMemoryScopeError" and len(alice_records) == 1
    return CaseObservation(
        passed=passed,
        observed="scope_rejected" if passed else "scope_leaked",
        evidence={
            "rejected_error": rejected_error,
            "owner_records": len(alice_records),
            "owner_scope": alice.user_scope,
        },
    )


def _corrupt_store(chapter: ModuleType, case_dir: Path) -> CaseObservation:
    """Inject a torn JSONL record and require explicit corruption detection."""

    path = case_dir / "corrupt.jsonl"
    store = chapter.RemoteMemoryStore(path, user_id="alice")
    _append(
        chapter,
        store,
        memory_id="mem-valid",
        content="The first record is valid durable evidence.",
        source_id="src-valid",
        title="Valid evidence",
    )
    # Simulate a crashed or external writer leaving a torn final record.  The
    # reader must never skip it and continue with a partially trusted history.
    with path.open("a", encoding="utf-8") as handle:
        handle.write('{"memory_id":"mem-torn"\n')

    rejected_error: str | None = None
    error_message: str | None = None
    try:
        store.read_all()
    except chapter.RemoteMemoryCorruptionError as exc:
        rejected_error = type(exc).__name__
        error_message = str(exc)

    passed = rejected_error == "RemoteMemoryCorruptionError"
    return CaseObservation(
        passed=passed,
        observed="corruption_detected" if passed else "corruption_ignored",
        evidence={
            "rejected_error": rejected_error,
            "message": error_message,
            "injected_line": 2,
        },
    )


def _restart_recall(chapter: ModuleType, case_dir: Path) -> CaseObservation:
    """Recreate store/engine objects and compare source-bearing recall output."""

    path = case_dir / "restart.jsonl"
    store = chapter.RemoteMemoryStore(path, user_id="alice")
    _append(
        chapter,
        store,
        memory_id="mem-retry-policy",
        content="Memory harness retries preserve provenance and stable identity.",
        source_id="src-retry-policy",
        title="Memory retry policy",
    )
    _append(
        chapter,
        store,
        memory_id="mem-unrelated",
        content="The product launch notes describe a visual theme.",
        source_id="src-unrelated",
        title="Product notes",
    )

    query = "How should the memory harness preserve retry provenance?"
    before_digest = hashlib.sha256(path.read_bytes()).hexdigest()
    first = chapter.RecallEngine(store).recall(
        query,
        limit=2,
        query_id="query-resilience",
        as_of=RECALL_AS_OF,
    )
    restarted_store = chapter.RemoteMemoryStore(path, user_id="alice")
    restarted = chapter.RecallEngine(restarted_store).recall(
        query,
        limit=2,
        query_id="query-resilience",
        as_of=RECALL_AS_OF,
    )
    after_digest = hashlib.sha256(path.read_bytes()).hexdigest()

    first_hits = [hit.to_dict() for hit in first.hits]
    restarted_hits = [hit.to_dict() for hit in restarted.hits]
    hit_ids = [hit.memory_id for hit in restarted.hits]
    provenance_ids = [hit.provenance.source_id for hit in restarted.hits]
    store_unchanged = before_digest == after_digest
    provenance_preserved = (
        hit_ids[:1] == ["mem-retry-policy"]
        and provenance_ids[:1] == ["src-retry-policy"]
    )
    passed = (
        first_hits == restarted_hits
        and store_unchanged
        and provenance_preserved
        and len(restarted_store.read_all()) == 2
    )
    return CaseObservation(
        passed=passed,
        observed="recall_replayed" if passed else "recall_drifted",
        evidence={
            "hit_ids": hit_ids,
            "provenance_ids": provenance_ids,
            "stable_result": first_hits == restarted_hits,
            "store_unchanged": store_unchanged,
            "provenance_preserved": provenance_preserved,
            "durable_records": len(restarted_store.read_all()),
        },
    )


DEFAULT_CASES = (
    CaseDefinition(
        case_id="concurrent_duplicate_write",
        contract="Concurrent identical writes leave exactly one durable record.",
        runner=_concurrent_duplicate_write,
    ),
    CaseDefinition(
        case_id="id_collision",
        contract="An existing memory identity cannot accept a different payload.",
        runner=_id_collision,
    ),
    CaseDefinition(
        case_id="scope_isolation",
        contract="A mismatched user scope fails closed on the same storage path.",
        runner=_scope_isolation,
    ),
    CaseDefinition(
        case_id="corrupt_store",
        contract="Malformed durable evidence is reported instead of skipped.",
        runner=_corrupt_store,
    ),
    CaseDefinition(
        case_id="restart_recall",
        contract="Recall stays deterministic, source-bearing, and non-mutating after restart.",
        runner=_restart_recall,
    ),
)


def evaluate_cases(
    chapter: ModuleType,
    output_dir: Path,
    *,
    cases: tuple[CaseDefinition, ...] = DEFAULT_CASES,
) -> EvaluationReport:
    """Run independent cases and preserve unexpected errors as failed evidence."""

    if not cases:
        raise ValueError("memory resilience evaluation needs at least one case")
    output_dir = Path(output_dir).expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    report_path = output_dir / REPORT_NAME
    results: list[CaseResult] = []

    # Each invocation receives clean storage paths, so re-running the scorecard
    # cannot turn yesterday's durable records into today's false positives.
    with tempfile.TemporaryDirectory(prefix="memory-resilience-cases-") as tmp:
        workspace = Path(tmp)
        for case in cases:
            case_dir = workspace / case.case_id
            case_dir.mkdir(parents=True, exist_ok=True)
            try:
                observation = case.runner(chapter, case_dir)
            except Exception as exc:  # keep one broken case from hiding the rest
                observation = CaseObservation(
                    passed=False,
                    observed="unexpected_exception",
                    evidence={
                        "error_type": type(exc).__name__,
                        "message": str(exc),
                    },
                )
            results.append(
                CaseResult(
                    case_id=case.case_id,
                    contract=case.contract,
                    passed=observation.passed,
                    observed=observation.observed,
                    evidence=observation.evidence,
                )
            )

    report = EvaluationReport(tuple(results), str(report_path))
    report_path.write_text(
        json.dumps(report.to_dict(), ensure_ascii=False, indent=2, sort_keys=True)
        + "\n",
        encoding="utf-8",
    )
    return report


def run_evaluation(output_dir: Path = DEFAULT_OUTPUT) -> EvaluationReport:
    """Load S12 and run the default resilience contract gates."""

    return evaluate_cases(load_memory_chapter(), output_dir)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run the keyless Memory resilience fault-injection scorecard."
    )
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()

    report = run_evaluation(args.output_dir)
    print("Memory resilience evaluation")
    for case in report.cases:
        status = "PASS" if case.passed else "FAIL"
        print(f"[{status}] {case.case_id}: {case.observed}")
    print(f"Passed: {report.summary['passed']}/{report.summary['total']}")
    print(f"Report: {report.report_path}")
    print("RESULT: OK" if report.passed else "RESULT: FAILED")
    return 0 if report.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
