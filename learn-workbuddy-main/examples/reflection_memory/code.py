#!/usr/bin/env python3
"""Offline example: turn failed trajectories into reviewable reflection memory.

Failure is evidence that one approach did not work; it is not evidence for the
correct fix.  This example therefore requires repeated, distinct failures and
a held-out successful recovery before it can create a reflection candidate.
The candidate must then pass explicit checks and receive human approval before
it becomes prompt-injectable memory.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import tempfile
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Mapping, Sequence


SAFE_ID = re.compile(r"^[a-z0-9][a-z0-9._-]{1,63}$")
SAFE_TOOL = re.compile(r"^[a-zA-Z0-9_.-]{1,64}$")
BLOCKED_TEXT = (
    "rm -rf",
    "sudo ",
    "curl ",
    "invoke-webrequest",
    "ignore previous",
    "disregard previous",
    "system prompt",
    "developer message",
    "<system",
    "authorization:",
    "api_key",
    "api-key",
    "token=",
    "secret=",
    "password=",
    "begin private key",
)
FORBIDDEN_STEP_FIELDS = {
    "arguments",
    "command",
    "input",
    "output",
    "stderr",
    "stdout",
    "traceback",
}
EXECUTABLE_TEXT_MARKERS = (
    "```",
    "`",
    "&&",
    "||",
    "bash -c",
    "powershell -command",
    "python -c",
    "python -m",
)
MAX_TEXT_CHARS = 500
MAX_CONTEXT_REFLECTIONS = 3
_DIRECTORY_FSYNC_SUPPORTED = os.name != "nt"


class ReflectionError(RuntimeError):
    """Raised when evidence, evaluation, or memory lifecycle gates fail."""


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _contains_blocked_text(value: str) -> str | None:
    lowered = value.casefold()
    return next((pattern for pattern in BLOCKED_TEXT if pattern in lowered), None)


def _validate_id(value: object, *, field_name: str) -> str:
    normalized = str(value).strip().casefold()
    if not SAFE_ID.fullmatch(normalized):
        raise ReflectionError(f"{field_name} must match {SAFE_ID.pattern}")
    return normalized


def _validate_text(
    value: object,
    *,
    field_name: str,
    max_chars: int = MAX_TEXT_CHARS,
) -> str:
    normalized = " ".join(str(value).split())
    if not normalized:
        raise ReflectionError(f"{field_name} must not be empty")
    if len(normalized) > max_chars:
        raise ReflectionError(f"{field_name} exceeds {max_chars} characters")
    blocked = _contains_blocked_text(normalized)
    if blocked:
        raise ReflectionError(f"{field_name} contains blocked text: {blocked}")
    return normalized


def _validate_intent(value: object, *, field_name: str) -> str:
    normalized = _validate_text(value, field_name=field_name)
    lowered = normalized.casefold()
    marker = next(
        (item for item in EXECUTABLE_TEXT_MARKERS if item in lowered), None
    )
    if marker:
        raise ReflectionError(
            f"{field_name} contains executable detail: {marker}"
        )
    return normalized


def _fsync_directory(path: Path) -> None:
    """Persist a replaced directory entry where directory handles are supported."""

    if not _DIRECTORY_FSYNC_SUPPORTED:
        return
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _atomic_write_text(path: Path, content: str) -> None:
    """Expose either the old file or the complete new file, never a partial one."""

    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        _fsync_directory(path.parent)
    finally:
        temporary.unlink(missing_ok=True)


@dataclass(frozen=True)
class StepEvidence:
    intent: str
    tool: str
    ok: bool
    error_type: str | None = None

    @property
    def failure_signature(self) -> tuple[str, str, str]:
        if self.ok or self.error_type is None:
            raise ReflectionError("only failed steps have a failure signature")
        return (self.intent.casefold(), self.tool, self.error_type)


@dataclass(frozen=True)
class TrajectoryEvidence:
    trace_id: str
    task_family: str
    task: str
    split: str
    outcome: str
    steps: tuple[StepEvidence, ...]
    recovery_for: tuple[str, ...]
    source_digest: str

    @property
    def successful(self) -> bool:
        return (
            self.outcome == "success"
            and bool(self.steps)
            and all(step.ok for step in self.steps)
        )

    @property
    def failed(self) -> bool:
        return self.outcome == "failure" and any(not step.ok for step in self.steps)

    @property
    def first_failed_step(self) -> StepEvidence:
        for step in self.steps:
            if not step.ok:
                return step
        raise ReflectionError(f"trajectory {self.trace_id} has no failed step")


@dataclass(frozen=True)
class ReflectionCandidate:
    candidate_id: str
    task_family: str
    signature_id: str
    failed_intent: str
    failed_tool: str
    error_type: str
    avoid_when: str
    lesson: str
    source_failure_trace_ids: tuple[str, ...]
    source_failure_digests: tuple[str, ...]
    recovery_trace_id: str
    recovery_digest: str
    created_at: str

    def to_dict(self) -> dict[str, object]:
        payload = asdict(self)
        payload["source_failure_trace_ids"] = list(
            self.source_failure_trace_ids
        )
        payload["source_failure_digests"] = list(self.source_failure_digests)
        return payload


@dataclass(frozen=True)
class ReflectionEvaluation:
    candidate_id: str
    recovery_trace_id: str
    checks: Mapping[str, bool]
    passed: bool
    evaluated_at: str

    def to_dict(self) -> dict[str, object]:
        return {
            "candidate_id": self.candidate_id,
            "recovery_trace_id": self.recovery_trace_id,
            "checks": dict(self.checks),
            "passed": self.passed,
            "evaluated_at": self.evaluated_at,
        }


class ReflectionStore:
    """Filesystem boundary for evidence, candidates, releases, and audit events."""

    def __init__(self, root: Path):
        self.root = root.expanduser().resolve()
        self.traces_dir = self.root / "traces"
        self.candidates_dir = self.root / "candidates"
        self.reflections_dir = self.root / "reflections"
        self.audit_path = self.root / "reflection-audit.jsonl"
        for directory in (
            self.traces_dir,
            self.candidates_dir,
            self.reflections_dir,
        ):
            directory.mkdir(parents=True, exist_ok=True)

    def append_audit(self, action: str, details: Mapping[str, object]) -> None:
        event = {"timestamp": _utc_now(), "action": action, "details": dict(details)}
        with self.audit_path.open("a", encoding="utf-8", newline="\n") as handle:
            handle.write(json.dumps(event, sort_keys=True, ensure_ascii=False) + "\n")
            handle.flush()
            os.fsync(handle.fileno())

    def write_trajectory(
        self,
        *,
        trace_id: str,
        task_family: str,
        task: str,
        split: str,
        outcome: str,
        steps: Sequence[Mapping[str, object]],
        recovery_for: Sequence[str] = (),
    ) -> Path:
        safe_trace_id = _validate_id(trace_id, field_name="trace_id")
        if split not in {"train", "validation"}:
            raise ReflectionError("trajectory split must be train or validation")
        if outcome not in {"success", "failure"}:
            raise ReflectionError("trajectory outcome must be success or failure")

        records: list[dict[str, object]] = [
            {
                "type": "trajectory",
                "trace_id": safe_trace_id,
                "task_family": _validate_id(task_family, field_name="task_family"),
                "task": _validate_text(task, field_name="task"),
                "split": split,
                "outcome": outcome,
                "recovery_for": sorted(
                    {
                        _validate_id(item, field_name="recovery_for item")
                        for item in recovery_for
                    }
                ),
            }
        ]
        for index, step in enumerate(steps, start=1):
            unexpected = set(step) - {"intent", "tool", "ok", "error_type"}
            if unexpected:
                raise ReflectionError(
                    f"step {index} contains forbidden or unknown fields: "
                    + ", ".join(sorted(unexpected))
                )
            tool = str(step.get("tool", "")).strip()
            if not SAFE_TOOL.fullmatch(tool):
                raise ReflectionError(f"step {index} has invalid tool name")
            if not isinstance(step.get("ok"), bool):
                raise ReflectionError(f"step {index} ok must be a boolean")
            ok = step["ok"] is True
            raw_error_type = step.get("error_type")
            if ok and raw_error_type not in {None, ""}:
                raise ReflectionError(f"step {index} successful step has error_type")
            if not ok and raw_error_type in {None, ""}:
                raise ReflectionError(f"step {index} failed step needs error_type")
            records.append(
                {
                    "type": "step",
                    "intent": _validate_intent(
                        step.get("intent", ""),
                        field_name=f"step {index} intent",
                    ),
                    "tool": tool,
                    "ok": ok,
                    **(
                        {
                            "error_type": _validate_id(
                                raw_error_type,
                                field_name=f"step {index} error_type",
                            )
                        }
                        if not ok
                        else {}
                    ),
                }
            )

        rendered = "".join(
            json.dumps(record, sort_keys=True, ensure_ascii=False) + "\n"
            for record in records
        )
        if blocked := _contains_blocked_text(rendered):
            raise ReflectionError(f"trajectory contains blocked text: {blocked}")

        path = self.traces_dir / f"{safe_trace_id}.jsonl"
        _atomic_write_text(path, rendered)
        self.append_audit("trajectory_written", {"trace_id": safe_trace_id})
        return path

    def load_trajectory(self, path: Path) -> TrajectoryEvidence:
        raw = path.read_bytes()
        text = raw.decode("utf-8")
        if blocked := _contains_blocked_text(text):
            raise ReflectionError(f"trajectory contains blocked text: {blocked}")
        try:
            records = [json.loads(line) for line in text.splitlines() if line.strip()]
        except json.JSONDecodeError as exc:
            raise ReflectionError(f"invalid trajectory JSONL: {path.name}") from exc
        if not records or not isinstance(records[0], dict):
            raise ReflectionError("trajectory must start with a metadata record")

        header = records[0]
        allowed_header = {
            "type",
            "trace_id",
            "task_family",
            "task",
            "split",
            "outcome",
            "recovery_for",
        }
        if header.get("type") != "trajectory" or set(header) - allowed_header:
            raise ReflectionError("trajectory metadata has unknown fields")
        split = str(header.get("split", ""))
        outcome = str(header.get("outcome", ""))
        if split not in {"train", "validation"}:
            raise ReflectionError("trajectory split must be train or validation")
        if outcome not in {"success", "failure"}:
            raise ReflectionError("trajectory outcome must be success or failure")

        recovery_payload = header.get("recovery_for", [])
        if not isinstance(recovery_payload, list):
            raise ReflectionError("recovery_for must be a list")
        recovery_for = tuple(
            sorted(
                {
                    _validate_id(item, field_name="recovery_for item")
                    for item in recovery_payload
                }
            )
        )

        steps: list[StepEvidence] = []
        for line_number, record in enumerate(records[1:], start=2):
            if not isinstance(record, dict) or record.get("type") != "step":
                raise ReflectionError(f"line {line_number} must be a step record")
            unexpected = set(record) - {"type", "intent", "tool", "ok", "error_type"}
            if unexpected:
                unsafe = sorted(unexpected & FORBIDDEN_STEP_FIELDS)
                label = "forbidden" if unsafe else "unknown"
                raise ReflectionError(
                    f"line {line_number} has {label} fields: "
                    + ", ".join(sorted(unexpected))
                )
            tool = str(record.get("tool", "")).strip()
            if not SAFE_TOOL.fullmatch(tool):
                raise ReflectionError(f"line {line_number} has invalid tool name")
            ok = record.get("ok") is True
            raw_error_type = record.get("error_type")
            if ok and raw_error_type not in {None, ""}:
                raise ReflectionError(f"line {line_number} successful step has error_type")
            if not ok and raw_error_type in {None, ""}:
                raise ReflectionError(f"line {line_number} failed step needs error_type")
            error_type = (
                _validate_id(raw_error_type, field_name=f"line {line_number} error_type")
                if not ok
                else None
            )
            steps.append(
                StepEvidence(
                    intent=_validate_intent(
                        record.get("intent", ""),
                        field_name=f"line {line_number} intent",
                    ),
                    tool=tool,
                    ok=ok,
                    error_type=error_type,
                )
            )

        trajectory = TrajectoryEvidence(
            trace_id=_validate_id(header.get("trace_id"), field_name="trace_id"),
            task_family=_validate_id(
                header.get("task_family"), field_name="task_family"
            ),
            task=_validate_text(header.get("task"), field_name="task"),
            split=split,
            outcome=outcome,
            steps=tuple(steps),
            recovery_for=recovery_for,
            source_digest=hashlib.sha256(raw).hexdigest(),
        )
        if outcome == "success" and not trajectory.successful:
            raise ReflectionError("success trajectory contains a failed or empty procedure")
        if outcome == "failure" and not trajectory.failed:
            raise ReflectionError("failure trajectory must contain a failed step")
        return trajectory

    def candidate_dir(self, candidate_id: str) -> Path:
        return self.candidates_dir / _validate_id(
            candidate_id, field_name="candidate_id"
        )

    def save_candidate(self, candidate: ReflectionCandidate) -> Path:
        directory = self.candidate_dir(candidate.candidate_id)
        _atomic_write_text(
            directory / "candidate.json",
            json.dumps(
                candidate.to_dict(), indent=2, sort_keys=True, ensure_ascii=False
            )
            + "\n",
        )
        path = directory / "REFLECTION.md"
        _atomic_write_text(path, render_reflection(candidate, status="candidate"))
        self.append_audit(
            "reflection_candidate_created",
            {
                "candidate_id": candidate.candidate_id,
                "source_failure_trace_ids": candidate.source_failure_trace_ids,
                "recovery_trace_id": candidate.recovery_trace_id,
            },
        )
        return path

    def save_evaluation(self, report: ReflectionEvaluation) -> Path:
        path = self.candidate_dir(report.candidate_id) / "evaluation.json"
        _atomic_write_text(
            path,
            json.dumps(
                report.to_dict(), indent=2, sort_keys=True, ensure_ascii=False
            )
            + "\n",
        )
        self.append_audit(
            "reflection_candidate_evaluated",
            {"candidate_id": report.candidate_id, "passed": report.passed},
        )
        return path

    def _reflection_root(self, task_family: str, signature_id: str) -> Path:
        return (
            self.reflections_dir
            / _validate_id(task_family, field_name="task_family")
            / _validate_id(signature_id, field_name="signature_id")
        )

    def promote(
        self,
        candidate: ReflectionCandidate,
        report: ReflectionEvaluation,
        *,
        approved_by: str,
    ) -> Path:
        if not approved_by.strip():
            raise ReflectionError("explicit approved_by is required")
        approver = _validate_text(
            approved_by, field_name="approved_by", max_chars=100
        )
        if (
            report.candidate_id != candidate.candidate_id
            or report.recovery_trace_id != candidate.recovery_trace_id
            or not report.passed
            or not report.checks
            or not all(report.checks.values())
        ):
            raise ReflectionError("candidate must have a matching passing evaluation")

        evaluation_path = self.candidate_dir(candidate.candidate_id) / "evaluation.json"
        if not evaluation_path.exists():
            raise ReflectionError("candidate has no stored evaluation evidence")
        candidate_path = self.candidate_dir(candidate.candidate_id) / "candidate.json"
        if not candidate_path.exists():
            raise ReflectionError("candidate has no stored provenance")
        stored_candidate = json.loads(candidate_path.read_text(encoding="utf-8"))
        if stored_candidate != candidate.to_dict():
            raise ReflectionError("stored candidate does not match promotion request")
        stored_report = json.loads(evaluation_path.read_text(encoding="utf-8"))
        if stored_report != report.to_dict():
            raise ReflectionError("stored evaluation does not match promotion request")

        root = self._reflection_root(candidate.task_family, candidate.signature_id)
        manifest_path = root / "manifest.json"
        if manifest_path.exists():
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        else:
            manifest = {
                "task_family": candidate.task_family,
                "signature_id": candidate.signature_id,
                "status": "candidate",
                "active_version": None,
                "history": [],
            }

        for item in manifest["history"]:
            if item["candidate_id"] == candidate.candidate_id:
                return root / f"v{item['version']}" / "REFLECTION.md"

        version = len(manifest["history"]) + 1
        version_dir = root / f"v{version}"
        reflection_path = version_dir / "REFLECTION.md"
        activated_at = _utc_now()
        release_payload = {
            **candidate.to_dict(),
            "status": "active",
            "version": version,
            "approved_by": approver,
            "activated_at": activated_at,
            "evaluated_at": report.evaluated_at,
        }
        _atomic_write_text(
            version_dir / "reflection.json",
            json.dumps(
                release_payload, indent=2, sort_keys=True, ensure_ascii=False
            )
            + "\n",
        )
        _atomic_write_text(
            reflection_path,
            render_reflection(
                candidate,
                status="active",
                version=version,
                approved_by=approver,
            ),
        )
        manifest["status"] = "active"
        manifest["active_version"] = version
        for key in (
            "resolved_at",
            "resolved_by_digest",
            "resolved_by_trace_id",
            "resolved_version",
        ):
            manifest.pop(key, None)
        manifest["history"].append(
            {
                "version": version,
                "candidate_id": candidate.candidate_id,
                "approved_by": approver,
                "activated_at": activated_at,
                "reflection_path": str(reflection_path),
            }
        )
        _atomic_write_text(
            manifest_path,
            json.dumps(manifest, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        )
        self.append_audit(
            "reflection_promoted",
            {
                "candidate_id": candidate.candidate_id,
                "signature_id": candidate.signature_id,
                "task_family": candidate.task_family,
                "version": version,
                "approved_by": approver,
            },
        )
        return reflection_path

    def resolve(
        self,
        *,
        task_family: str,
        signature_id: str,
        resolved_by: TrajectoryEvidence,
    ) -> Path:
        family = _validate_id(task_family, field_name="task_family")
        if not resolved_by.successful or resolved_by.task_family != family:
            raise ReflectionError(
                "resolution evidence must be a successful trajectory in the same task family"
            )
        root = self._reflection_root(family, signature_id)
        manifest_path = root / "manifest.json"
        if not manifest_path.exists():
            raise ReflectionError("reflection manifest does not exist")
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if manifest.get("status") == "resolved":
            if manifest.get("resolved_by_trace_id") != resolved_by.trace_id:
                raise ReflectionError("reflection was resolved by different evidence")
            return manifest_path
        if manifest.get("status") != "active" or manifest.get("active_version") is None:
            raise ReflectionError("only an active reflection can be resolved")

        previous_version = manifest["active_version"]
        manifest["status"] = "resolved"
        manifest["active_version"] = None
        manifest["resolved_version"] = previous_version
        manifest["resolved_at"] = _utc_now()
        manifest["resolved_by_trace_id"] = resolved_by.trace_id
        manifest["resolved_by_digest"] = resolved_by.source_digest
        _atomic_write_text(
            manifest_path,
            json.dumps(manifest, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        )
        self.append_audit(
            "reflection_resolved",
            {
                "signature_id": signature_id,
                "task_family": family,
                "resolved_by_trace_id": resolved_by.trace_id,
                "resolved_version": previous_version,
            },
        )
        return manifest_path

    def get_context_for_agent(
        self,
        *,
        task_family: str,
        limit: int = MAX_CONTEXT_REFLECTIONS,
    ) -> str:
        family = _validate_id(task_family, field_name="task_family")
        if limit < 0:
            raise ValueError("limit must not be negative")
        if limit == 0:
            return "(no active reflections)"
        family_root = self.reflections_dir / family
        if not family_root.exists():
            return "(no active reflections)"

        active: list[dict[str, object]] = []
        for manifest_path in sorted(family_root.glob("*/manifest.json")):
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            version = manifest.get("active_version")
            if manifest.get("status") != "active" or not isinstance(version, int):
                continue
            record_path = manifest_path.parent / f"v{version}" / "reflection.json"
            record = json.loads(record_path.read_text(encoding="utf-8"))
            active.append(record)

        if not active:
            return "(no active reflections)"
        active.sort(
            key=lambda item: (
                str(item["evaluated_at"]),
                len(item["source_failure_trace_ids"]),
                str(item["candidate_id"]),
            ),
            reverse=True,
        )
        selected = active[:limit]
        lines = ["## Relevant reflections", ""]
        for item in selected:
            lines.append(f"- When {item['avoid_when']} {item['lesson']}")
        return "\n".join(lines)


class ReflectionPipeline:
    """Deterministic failed-run reflection with recovery and approval gates."""

    def __init__(self, store: ReflectionStore, *, minimum_support: int = 2):
        if minimum_support < 2:
            raise ValueError("minimum_support must be at least 2")
        self.store = store
        self.minimum_support = minimum_support

    def triage(
        self,
        trajectories: Iterable[TrajectoryEvidence],
        *,
        task_family: str,
    ) -> tuple[list[TrajectoryEvidence], list[TrajectoryEvidence], dict[str, str]]:
        family = _validate_id(task_family, field_name="task_family")
        failures: list[TrajectoryEvidence] = []
        recoveries: list[TrajectoryEvidence] = []
        rejected: dict[str, str] = {}
        for trajectory in trajectories:
            reason: str | None = None
            if trajectory.task_family != family:
                reason = "different task family"
            elif trajectory.split == "train" and trajectory.failed:
                failures.append(trajectory)
            elif trajectory.split == "validation" and trajectory.successful:
                recoveries.append(trajectory)
            else:
                reason = "not failed training evidence or successful recovery evidence"
            if reason:
                rejected[trajectory.trace_id] = reason
        return (
            sorted(failures, key=lambda item: item.trace_id),
            sorted(recoveries, key=lambda item: item.trace_id),
            rejected,
        )

    def group_failures(
        self, failures: Iterable[TrajectoryEvidence]
    ) -> dict[tuple[str, str, str], list[TrajectoryEvidence]]:
        groups: dict[tuple[str, str, str], list[TrajectoryEvidence]] = {}
        for trajectory in failures:
            groups.setdefault(
                trajectory.first_failed_step.failure_signature, []
            ).append(trajectory)
        return {
            signature: sorted(items, key=lambda item: item.trace_id)
            for signature, items in sorted(groups.items())
        }

    def distill(
        self,
        failures: Sequence[TrajectoryEvidence],
        *,
        recovery: TrajectoryEvidence,
        task_family: str,
    ) -> ReflectionCandidate:
        family = _validate_id(task_family, field_name="task_family")
        if len(failures) < self.minimum_support:
            raise ReflectionError(
                f"need at least {self.minimum_support} failed training trajectories"
            )
        failure_ids = tuple(sorted(item.trace_id for item in failures))
        failure_digests = tuple(
            item.source_digest for item in sorted(failures, key=lambda item: item.trace_id)
        )
        if len(set(failure_ids)) != len(failure_ids):
            raise ReflectionError("minimum support requires distinct trajectory IDs")
        if len(set(failure_digests)) != len(failure_digests):
            raise ReflectionError("minimum support requires distinct trajectory digests")
        if any(
            item.task_family != family or item.split != "train" or not item.failed
            for item in failures
        ):
            raise ReflectionError("distillation received ineligible failure evidence")

        expected = failures[0].first_failed_step.failure_signature
        if any(
            item.first_failed_step.failure_signature != expected
            for item in failures[1:]
        ):
            raise ReflectionError("failed trajectories do not share one stable signature")
        if (
            recovery.task_family != family
            or recovery.split != "validation"
            or not recovery.successful
        ):
            raise ReflectionError("recovery must be successful held-out evidence")
        if not set(failure_ids).issubset(recovery.recovery_for):
            raise ReflectionError("recovery must reference every supporting failure")
        if recovery.trace_id in failure_ids or recovery.source_digest in failure_digests:
            raise ReflectionError("recovery evidence must be held out")

        failed_intent, failed_tool, error_type = expected
        signature_seed = json.dumps(
            {
                "task_family": family,
                "failed_intent": failed_intent,
                "failed_tool": failed_tool,
                "error_type": error_type,
            },
            sort_keys=True,
        )
        signature_id = "failure-" + hashlib.sha256(
            signature_seed.encode("utf-8")
        ).hexdigest()[:16]
        candidate_seed = json.dumps(
            {
                "signature_id": signature_id,
                "failure_ids": failure_ids,
                "recovery_id": recovery.trace_id,
            },
            sort_keys=True,
        )
        candidate_id = "reflection-" + hashlib.sha256(
            candidate_seed.encode("utf-8")
        ).hexdigest()[:16]
        failed_action = failures[0].first_failed_step.intent.rstrip(" .!?")
        failed_action = failed_action[:1].lower() + failed_action[1:]
        recovery_intents = "; ".join(
            step.intent.rstrip(" .!?") for step in recovery.steps[:3]
        )
        candidate = ReflectionCandidate(
            candidate_id=candidate_id,
            task_family=family,
            signature_id=signature_id,
            failed_intent=failures[0].first_failed_step.intent,
            failed_tool=failed_tool,
            error_type=error_type,
            avoid_when=f"attempting to {failed_action} produces {error_type}.",
            lesson=f"Prefer the recovered procedure: {recovery_intents}.",
            source_failure_trace_ids=failure_ids,
            source_failure_digests=failure_digests,
            recovery_trace_id=recovery.trace_id,
            recovery_digest=recovery.source_digest,
            created_at=_utc_now(),
        )
        self.store.save_candidate(candidate)
        return candidate

    def evaluate(
        self,
        candidate: ReflectionCandidate,
        *,
        failures: Sequence[TrajectoryEvidence],
        recovery: TrajectoryEvidence,
    ) -> ReflectionEvaluation:
        failure_ids = tuple(sorted(item.trace_id for item in failures))
        failure_digests = tuple(
            item.source_digest for item in sorted(failures, key=lambda item: item.trace_id)
        )
        source_signatures = {
            item.first_failed_step.failure_signature for item in failures
        }
        candidate_signature = (
            candidate.failed_intent.casefold(),
            candidate.failed_tool,
            candidate.error_type,
        )
        rendered = render_reflection(candidate, status="candidate")
        checks = {
            "minimum_support": len(failure_ids) >= self.minimum_support,
            "distinct_trace_ids": len(set(failure_ids)) == len(failure_ids),
            "distinct_source_digests": len(set(failure_digests))
            == len(failure_digests),
            "matching_failure_signature": source_signatures == {candidate_signature},
            "candidate_sources_match": candidate.source_failure_trace_ids
            == failure_ids
            and candidate.source_failure_digests == failure_digests,
            "held_out_recovery": recovery.trace_id not in failure_ids
            and recovery.source_digest not in failure_digests,
            "same_task_family": recovery.task_family == candidate.task_family,
            "recovery_succeeded": recovery.split == "validation"
            and recovery.successful,
            "recovery_references_failures": set(failure_ids).issubset(
                recovery.recovery_for
            ),
            "recovery_provenance_matches": candidate.recovery_trace_id
            == recovery.trace_id
            and candidate.recovery_digest == recovery.source_digest,
            "content_safety_scan": _contains_blocked_text(rendered) is None,
            "bounded_memory": len(candidate.avoid_when) <= MAX_TEXT_CHARS
            and len(candidate.lesson) <= MAX_TEXT_CHARS,
            "non_executable_memory": set(candidate.to_dict()).isdisjoint(
                FORBIDDEN_STEP_FIELDS
            )
            and not any(
                marker in (candidate.avoid_when + candidate.lesson).casefold()
                for marker in EXECUTABLE_TEXT_MARKERS
            ),
        }
        report = ReflectionEvaluation(
            candidate_id=candidate.candidate_id,
            recovery_trace_id=recovery.trace_id,
            checks=checks,
            passed=all(checks.values()),
            evaluated_at=_utc_now(),
        )
        self.store.save_evaluation(report)
        return report


def render_reflection(
    candidate: ReflectionCandidate,
    *,
    status: str,
    version: int | None = None,
    approved_by: str | None = None,
) -> str:
    lines = [
        f"# Reflection: {candidate.task_family}",
        "",
        f"- Status: {status}",
        f"- Signature: {candidate.signature_id}",
    ]
    if version is not None:
        lines.append(f"- Version: {version}")
    if approved_by is not None:
        lines.append(f"- Approved by: {approved_by}")
    lines.extend(
        [
            "",
            "## Avoid when",
            "",
            candidate.avoid_when[:1].upper() + candidate.avoid_when[1:],
            "",
            "## Lesson",
            "",
            candidate.lesson,
            "",
            "## Evidence boundary",
            "",
            (
                f"- Supported by {len(candidate.source_failure_trace_ids)} distinct "
                "failed trajectories and one held-out recovery."
            ),
            "- Raw commands, tool output, paths, and stack traces are not copied here.",
            "- This memory cannot grant tools or bypass the harness permission gate.",
            "",
        ]
    )
    return "\n".join(lines)


def seed_demo_trajectories(store: ReflectionStore) -> list[TrajectoryEvidence]:
    failed_steps = [
        {
            "intent": "Run tests before inspecting the project configuration.",
            "tool": "bash",
            "ok": False,
            "error_type": "configuration-error",
        }
    ]
    failure_ids = ("failed-run-1", "failed-run-2")
    paths = [
        store.write_trajectory(
            trace_id=trace_id,
            task_family="python-test-recovery",
            task="Recover a Python test run after configuration discovery fails.",
            split="train",
            outcome="failure",
            steps=failed_steps,
        )
        for trace_id in failure_ids
    ]
    paths.append(
        store.write_trajectory(
            trace_id="recovery-run-1",
            task_family="python-test-recovery",
            task="Recover a Python test run after configuration discovery fails.",
            split="validation",
            outcome="success",
            recovery_for=failure_ids,
            steps=[
                {
                    "intent": "Inspect the project test configuration.",
                    "tool": "read_file",
                    "ok": True,
                },
                {
                    "intent": "Run the smallest relevant test target.",
                    "tool": "bash",
                    "ok": True,
                },
                {
                    "intent": "Record the recovery result for review.",
                    "tool": "bash",
                    "ok": True,
                },
            ],
        )
    )
    paths.append(
        store.write_trajectory(
            trace_id="unrelated-run-1",
            task_family="other-task-family",
            task="Unrelated successful work.",
            split="validation",
            outcome="success",
            steps=[
                {"intent": "Complete unrelated work.", "tool": "read_file", "ok": True}
            ],
        )
    )
    return [store.load_trajectory(path) for path in paths]


def run_demo(
    home: Path,
    *,
    approve: bool = False,
    approved_by: str = "demo-user",
) -> dict[str, object]:
    store = ReflectionStore(home)
    pipeline = ReflectionPipeline(store)
    trajectories = seed_demo_trajectories(store)
    failures, recoveries, rejected = pipeline.triage(
        trajectories, task_family="python-test-recovery"
    )
    groups = pipeline.group_failures(failures)
    supporting_failures = next(iter(groups.values()))
    recovery = recoveries[0]
    candidate = pipeline.distill(
        supporting_failures,
        recovery=recovery,
        task_family="python-test-recovery",
    )
    report = pipeline.evaluate(
        candidate,
        failures=supporting_failures,
        recovery=recovery,
    )
    promoted_path = (
        store.promote(candidate, report, approved_by=approved_by) if approve else None
    )
    context = store.get_context_for_agent(task_family=candidate.task_family)
    manifest: dict[str, object] = {
        "home": str(store.root),
        "candidate_id": candidate.candidate_id,
        "candidate_path": str(
            store.candidate_dir(candidate.candidate_id) / "REFLECTION.md"
        ),
        "evaluation_path": str(
            store.candidate_dir(candidate.candidate_id) / "evaluation.json"
        ),
        "evaluation_passed": report.passed,
        "source_failure_trace_ids": list(candidate.source_failure_trace_ids),
        "recovery_trace_id": recovery.trace_id,
        "rejected_traces": rejected,
        "promotion_requested": approve,
        "promoted_reflection_path": str(promoted_path) if promoted_path else None,
        "context": context,
        "audit_path": str(store.audit_path),
    }
    _atomic_write_text(
        store.root / "run_manifest.json",
        json.dumps(manifest, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
    )
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Distill repeated failed trajectories and a successful recovery into "
            "reviewable reflection memory."
        )
    )
    parser.add_argument(
        "--home",
        type=Path,
        default=Path(".tmp/reflection-memory"),
        help="artifact directory (default: .tmp/reflection-memory)",
    )
    parser.add_argument(
        "--approve",
        action="store_true",
        help="simulate explicit human approval after evaluation passes",
    )
    parser.add_argument(
        "--approved-by",
        default="demo-user",
        help="identity recorded when --approve is supplied",
    )
    args = parser.parse_args()
    manifest = run_demo(
        args.home,
        approve=args.approve,
        approved_by=args.approved_by,
    )

    print("Reflection memory demo")
    print("Home:", manifest["home"])
    print("Candidate:", manifest["candidate_path"])
    print(
        "Failure evidence:",
        ", ".join(manifest["source_failure_trace_ids"]),
    )
    print("Recovery evidence:", manifest["recovery_trace_id"])
    print("Held-out evaluation passed:", manifest["evaluation_passed"])
    if manifest["promoted_reflection_path"]:
        print("Approved reflection:", manifest["promoted_reflection_path"])
        print(manifest["context"])
    else:
        print("Promotion: stopped at the human approval gate (use --approve to continue)")
    print("Audit:", manifest["audit_path"])


if __name__ == "__main__":
    main()
