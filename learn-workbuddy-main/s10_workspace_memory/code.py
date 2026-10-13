#!/usr/bin/env python3
"""s10_workspace_memory - project-scoped log-and-distill memory.

Session transcripts (s09) preserve what happened in one conversation.  This
chapter adds a different contract: select durable project facts, keep their
append-only evidence, and derive a compact view that a later session can load.

The implementation is intentionally local and provider-neutral.  Distillation
uses explicit rules instead of an API call, so scope, idempotency, atomic
writes, and restart recovery can all be exercised offline.

Usage:
    python s10_workspace_memory/code.py --demo
    python s10_workspace_memory/code.py
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import uuid
from copy import deepcopy
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timedelta, timezone
from enum import Enum
from pathlib import Path
from typing import Iterable, Mapping


# Machine-readable learning path metadata.  The chapter keeps s09's
# append-only evidence principle, but memory is a selective derived view rather
# than a second conversation transcript.
PROGRESSION = {
    "chapter": "s10_workspace_memory",
    "builds_on": ["s09_jsonl_transcript"],
    "adds": [
        "workspace-scoped fact log",
        "policy-driven memory distillation",
        "keyed memory supersession",
        "human conflict adjudication with append-only audit",
        "crash-recoverable adjudication transaction journal",
        "atomic curated memory view",
    ],
    "preserves": ["append-only evidence and restart recovery"],
}


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from mini_workbuddy.chapter_demo import maybe_run_chapter_demo
from mini_workbuddy.chapter_demo import prepare_chapter_provider

maybe_run_chapter_demo(__file__, PROGRESSION)
prepare_chapter_provider()

from anthropic import Anthropic
from dotenv import load_dotenv


try:
    import readline

    readline.parse_and_bind("set bind-tty-special-chars off")
    readline.parse_and_bind("set input-meta on")
    readline.parse_and_bind("set output-meta on")
    readline.parse_and_bind("set convert-meta off")
except ImportError:
    pass


load_dotenv(override=True)
if os.getenv("ANTHROPIC_BASE_URL"):
    os.environ.pop("ANTHROPIC_AUTH_TOKEN", None)


SCHEMA_VERSION = 2
SUPPORTED_FACT_SCHEMAS = frozenset({1, SCHEMA_VERSION})
SUPPORTED_CURATED_SCHEMAS = frozenset({1, SCHEMA_VERSION})
DEFAULT_RETENTION_DAYS = 30
MAX_FACT_CHARS = 2_000
MAX_CONTEXT_FACTS = 6
MAX_MEMORY_KEY_CHARS = 120
MAX_ADJUDICATION_TEXT_CHARS = 1_000
MAX_EVENT_ID_CHARS = 200
MEMORY_KEY_PATTERN = re.compile(r"^[a-z][a-z0-9]*(?:[._-][a-z0-9]+)*$")
EVENT_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,199}$")
CONFLICT_SCHEMA_VERSION = 1
ADJUDICATION_SCHEMA_VERSION = 1
RESOLUTION_TRANSACTION_SCHEMA_VERSION = 1
WORKDIR = Path.cwd()
_DIRECTORY_FSYNC_SUPPORTED = os.name != "nt"


def _fsync_directory(path: Path) -> None:
    """Persist a renamed directory entry where directory handles are supported.

    POSIX platforms allow opening a directory and passing its descriptor to
    ``fsync``.  Windows does not expose that operation through ``os.open``;
    the temporary file has still been flushed and synced before ``os.replace``
    makes the complete new version visible.
    """

    if not _DIRECTORY_FSYNC_SUPPORTED:
        return
    directory = os.open(path, os.O_RDONLY)
    try:
        os.fsync(directory)
    finally:
        os.close(directory)


def _discard_incomplete_jsonl_tail(path: Path) -> None:
    """Remove bytes that never formed a newline-terminated durable record.

    Readers deliberately ignore an unterminated final line after a crash.  A
    later append must first discard that ignored fragment, otherwise the next
    valid JSON object would be concatenated onto it and corrupt the log.
    """

    if not path.exists() or path.stat().st_size == 0:
        return
    with path.open("rb+") as handle:
        handle.seek(-1, os.SEEK_END)
        if handle.read(1) == b"\n":
            return
        handle.seek(0)
        content = handle.read()
        last_newline = content.rfind(b"\n")
        handle.seek(0)
        handle.truncate(last_newline + 1)
        handle.flush()
        os.fsync(handle.fileno())


class MemoryErrorBase(RuntimeError):
    """Base class for failures at the workspace-memory boundary."""


class MemoryScopeError(MemoryErrorBase):
    """Raised when persisted memory belongs to another workspace."""


class MemoryCorruptionError(MemoryErrorBase):
    """Raised for malformed durable records that cannot be ignored safely."""


class ConflictResolutionError(MemoryErrorBase):
    """Raised when a requested adjudication is invalid or contradictory."""


class StaleConflictResolutionError(ConflictResolutionError):
    """Raised when evidence changed after a reviewer observed a conflict."""


class FactKind(str, Enum):
    """Small vocabulary that makes retention policy explicit.

    Decisions, conventions, and pitfalls are usually useful in later sessions.
    Outcomes are useful in the recent log but normally age out instead of being
    promoted to long-term memory.
    """

    DECISION = "decision"
    CONVENTION = "convention"
    PITFALL = "pitfall"
    OUTCOME = "outcome"


class CuratedStatus(str, Enum):
    """Lifecycle state for one immutable curated revision."""

    ACTIVE = "active"
    SUPERSEDED = "superseded"


class ConflictStatus(str, Enum):
    """Lifecycle of one immutable conflict snapshot."""

    OPEN = "open"
    RESOLVED = "resolved"
    SUPERSEDED = "superseded"


class ResolutionPhase(str, Enum):
    """Durable milestones for one multi-file human adjudication."""

    PREPARED = "prepared"
    CURATED_APPLIED = "curated_applied"
    CONFLICT_CLOSED = "conflict_closed"
    AUDIT_APPENDED = "audit_appended"
    COMMITTED = "committed"


@dataclass(frozen=True)
class MemoryFact:
    """One immutable fact in a workspace's append-only daily log."""

    fact_id: str
    workspace_id: str
    recorded_at: str
    kind: str
    content: str
    source: str = "agent"
    importance: int = 3
    evidence: Mapping[str, str] = field(default_factory=dict)
    schema_version: int = SCHEMA_VERSION
    memory_key: str | None = None

    @classmethod
    def from_dict(cls, payload: Mapping[str, object]) -> "MemoryFact":
        try:
            return cls(
                fact_id=str(payload["fact_id"]),
                workspace_id=str(payload["workspace_id"]),
                recorded_at=str(payload["recorded_at"]),
                kind=str(payload["kind"]),
                content=str(payload["content"]),
                memory_key=(
                    None
                    if payload.get("memory_key") in (None, "")
                    else _clean_memory_key(str(payload["memory_key"]))
                ),
                source=str(payload.get("source", "agent")),
                importance=int(payload.get("importance", 3)),
                evidence=dict(payload.get("evidence") or {}),
                schema_version=int(payload.get("schema_version", 1)),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise MemoryCorruptionError(f"invalid memory fact: {exc}") from exc


@dataclass(frozen=True)
class DistillPolicy:
    """Explainable gate from raw facts to curated project memory."""

    minimum_age_days: int = DEFAULT_RETENTION_DAYS
    minimum_importance: int = 4
    repeat_threshold: int = 2
    supersession_repeat_threshold: int = 2
    stable_kinds: frozenset[str] = frozenset(
        {FactKind.DECISION.value, FactKind.CONVENTION.value, FactKind.PITFALL.value}
    )

    def __post_init__(self) -> None:
        if self.minimum_age_days < 0:
            raise ValueError("minimum_age_days must be >= 0")
        if not 1 <= self.minimum_importance <= 5:
            raise ValueError("minimum_importance must be between 1 and 5")
        if self.repeat_threshold < 1:
            raise ValueError("repeat_threshold must be >= 1")
        if self.supersession_repeat_threshold < 2:
            raise ValueError("supersession_repeat_threshold must be >= 2")


@dataclass
class CuratedMemoryEntry:
    """Compact long-term statement with links back to source facts."""

    key: str
    kind: str
    content: str
    first_seen: str
    last_seen: str
    evidence_ids: list[str]
    occurrences: int
    memory_key: str | None = None
    revision: int = 1
    status: str = CuratedStatus.ACTIVE.value
    supersedes: str | None = None
    superseded_by: str | None = None

    @classmethod
    def from_dict(cls, payload: Mapping[str, object]) -> "CuratedMemoryEntry":
        try:
            evidence_ids = [str(item) for item in payload.get("evidence_ids", [])]
            memory_key = payload.get("memory_key")
            if memory_key not in (None, ""):
                memory_key = _clean_memory_key(str(memory_key))
            else:
                memory_key = None
            revision = int(payload.get("revision", 1))
            status = str(payload.get("status", CuratedStatus.ACTIVE.value))
            if revision < 1:
                raise ValueError("revision must be >= 1")
            if status not in {item.value for item in CuratedStatus}:
                raise ValueError(f"unsupported curated status: {status}")
            return cls(
                key=str(payload["key"]),
                kind=str(payload["kind"]),
                content=str(payload["content"]),
                first_seen=str(payload["first_seen"]),
                last_seen=str(payload["last_seen"]),
                evidence_ids=evidence_ids,
                occurrences=int(payload.get("occurrences", len(evidence_ids))),
                memory_key=memory_key,
                revision=revision,
                status=status,
                supersedes=(
                    None
                    if payload.get("supersedes") in (None, "")
                    else str(payload["supersedes"])
                ),
                superseded_by=(
                    None
                    if payload.get("superseded_by") in (None, "")
                    else str(payload["superseded_by"])
                ),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise MemoryCorruptionError(f"invalid curated entry: {exc}") from exc


@dataclass(frozen=True)
class DistillReport:
    """Observable result returned to the scheduler, CLI, or audit layer."""

    scanned: int
    eligible: int
    created: int
    updated: int
    skipped: int
    superseded: int = 0
    conflicts: int = 0
    stale: int = 0
    queued_conflicts: int = 0
    conflict_case_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class ConflictCandidate:
    """One human-reviewable value backed by immutable fact IDs."""

    candidate_id: str
    kind: str
    content: str
    evidence_ids: tuple[str, ...]
    occurrences: int
    maximum_importance: int
    first_seen: str
    last_seen: str
    incumbent: bool = False

    @classmethod
    def from_dict(cls, payload: Mapping[str, object]) -> "ConflictCandidate":
        try:
            evidence_ids = tuple(sorted(str(item) for item in payload["evidence_ids"]))
            incumbent = payload.get("incumbent", False)
            if not isinstance(incumbent, bool):
                raise ValueError("incumbent must be boolean")
            candidate = cls(
                candidate_id=_clean_event_id(
                    payload["candidate_id"], field_name="conflict candidate_id"
                ),
                kind=str(payload["kind"]),
                content=str(payload["content"]),
                evidence_ids=evidence_ids,
                occurrences=int(payload["occurrences"]),
                maximum_importance=int(payload["maximum_importance"]),
                first_seen=str(payload["first_seen"]),
                last_seen=str(payload["last_seen"]),
                incumbent=incumbent,
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise MemoryCorruptionError(f"invalid conflict candidate: {exc}") from exc
        _validate_conflict_candidate(candidate)
        return candidate


@dataclass
class MemoryConflictCase:
    """A versioned evidence snapshot that requires an explicit human choice."""

    conflict_id: str
    workspace_id: str
    memory_key: str
    revision: int
    fingerprint: str
    status: str
    candidates: tuple[ConflictCandidate, ...]
    observed_fact_ids: tuple[str, ...]
    active_entry_key: str | None
    detected_at: str
    resolved_at: str | None = None
    selected_candidate_id: str | None = None
    resolution_event_id: str | None = None
    resolution_actor: str | None = None
    resolution_rationale: str | None = None
    resulting_active_entry_key: str | None = None
    superseded_at: str | None = None

    @classmethod
    def from_dict(cls, payload: Mapping[str, object]) -> "MemoryConflictCase":
        try:
            case = cls(
                conflict_id=_clean_event_id(
                    payload["conflict_id"], field_name="conflict_id"
                ),
                workspace_id=str(payload["workspace_id"]),
                memory_key=_clean_memory_key(str(payload["memory_key"])),
                revision=int(payload["revision"]),
                fingerprint=str(payload["fingerprint"]),
                status=str(payload["status"]),
                candidates=tuple(
                    ConflictCandidate.from_dict(dict(item))
                    for item in payload["candidates"]
                ),
                observed_fact_ids=tuple(
                    sorted(str(item) for item in payload["observed_fact_ids"])
                ),
                active_entry_key=_optional_text(payload.get("active_entry_key")),
                detected_at=str(payload["detected_at"]),
                resolved_at=_optional_text(payload.get("resolved_at")),
                selected_candidate_id=_optional_text(
                    payload.get("selected_candidate_id")
                ),
                resolution_event_id=_optional_text(
                    payload.get("resolution_event_id")
                ),
                resolution_actor=_optional_text(payload.get("resolution_actor")),
                resolution_rationale=_optional_text(
                    payload.get("resolution_rationale")
                ),
                resulting_active_entry_key=_optional_text(
                    payload.get("resulting_active_entry_key")
                ),
                superseded_at=_optional_text(payload.get("superseded_at")),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise MemoryCorruptionError(f"invalid conflict case: {exc}") from exc
        _validate_conflict_case(case)
        return case


@dataclass(frozen=True)
class ConflictAdjudication:
    """Append-only record proving who selected which evidence snapshot."""

    event_id: str
    workspace_id: str
    conflict_id: str
    case_revision: int
    selected_candidate_id: str
    actor: str
    rationale: str
    resolved_at: str
    prior_active_entry_key: str | None
    resulting_active_entry_key: str | None
    evidence_ids: tuple[str, ...]
    schema_version: int = ADJUDICATION_SCHEMA_VERSION

    @classmethod
    def from_dict(cls, payload: Mapping[str, object]) -> "ConflictAdjudication":
        try:
            event = cls(
                event_id=_clean_event_id(payload["event_id"], field_name="event_id"),
                workspace_id=str(payload["workspace_id"]),
                conflict_id=_clean_event_id(
                    payload["conflict_id"], field_name="conflict_id"
                ),
                case_revision=int(payload["case_revision"]),
                selected_candidate_id=_clean_event_id(
                    payload["selected_candidate_id"],
                    field_name="selected_candidate_id",
                ),
                actor=_clean_adjudication_text(payload["actor"], field_name="actor"),
                rationale=_clean_adjudication_text(
                    payload["rationale"], field_name="rationale"
                ),
                resolved_at=str(payload["resolved_at"]),
                prior_active_entry_key=_optional_text(
                    payload.get("prior_active_entry_key")
                ),
                resulting_active_entry_key=_optional_text(
                    payload.get("resulting_active_entry_key")
                ),
                evidence_ids=tuple(sorted(str(item) for item in payload["evidence_ids"])),
                schema_version=int(payload.get("schema_version", 0)),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise MemoryCorruptionError(f"invalid conflict adjudication: {exc}") from exc
        _validate_adjudication(event)
        return event


@dataclass(frozen=True)
class ConflictResolutionTransaction:
    """Prepared before any adjudication side effect reaches canonical state.

    Both before and after snapshots are intentional.  Recovery can therefore
    distinguish "the write did not happen", "the write happened but its phase
    marker did not", and "some unrelated state replaced the expected data".
    The last case fails closed instead of overwriting newer or corrupt state.
    """

    transaction_id: str
    workspace_id: str
    conflict_id: str
    event_id: str
    prepared_at: str
    curated_before: tuple[CuratedMemoryEntry, ...]
    curated_after: tuple[CuratedMemoryEntry, ...]
    conflicts_before: tuple[MemoryConflictCase, ...]
    conflicts_after: tuple[MemoryConflictCase, ...]
    adjudication: ConflictAdjudication
    schema_version: int = RESOLUTION_TRANSACTION_SCHEMA_VERSION

    @classmethod
    def from_dict(
        cls, payload: Mapping[str, object]
    ) -> "ConflictResolutionTransaction":
        try:
            transaction = cls(
                transaction_id=_clean_event_id(
                    payload["transaction_id"], field_name="transaction_id"
                ),
                workspace_id=str(payload["workspace_id"]),
                conflict_id=_clean_event_id(
                    payload["conflict_id"], field_name="conflict_id"
                ),
                event_id=_clean_event_id(payload["event_id"], field_name="event_id"),
                prepared_at=str(payload["prepared_at"]),
                curated_before=tuple(
                    CuratedMemoryEntry.from_dict(item)
                    for item in payload["curated_before"]
                ),
                curated_after=tuple(
                    CuratedMemoryEntry.from_dict(item)
                    for item in payload["curated_after"]
                ),
                conflicts_before=tuple(
                    MemoryConflictCase.from_dict(dict(item))
                    for item in payload["conflicts_before"]
                ),
                conflicts_after=tuple(
                    MemoryConflictCase.from_dict(dict(item))
                    for item in payload["conflicts_after"]
                ),
                adjudication=ConflictAdjudication.from_dict(
                    dict(payload["adjudication"])
                ),
                schema_version=int(payload.get("schema_version", 0)),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise MemoryCorruptionError(
                f"invalid conflict resolution transaction: {exc}"
            ) from exc
        _validate_resolution_transaction(transaction)
        return transaction


def _as_utc(value: datetime | None) -> datetime:
    current = value or datetime.now(timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    return current.astimezone(timezone.utc)


def _iso(value: datetime | None = None) -> str:
    return _as_utc(value).isoformat().replace("+00:00", "Z")


def _parse_timestamp(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise MemoryCorruptionError(f"invalid recorded_at timestamp: {value!r}") from exc
    return _as_utc(parsed)


def _normal_form(content: str) -> str:
    """Collapse cosmetic differences before grouping repeated facts."""

    return re.sub(r"\s+", " ", content).strip().casefold()


def _clean_memory_key(value: str) -> str:
    """Normalize one explicit conflict domain before it reaches durable state."""

    key = value.strip().casefold()
    if not key:
        raise ValueError("memory_key must not be empty")
    if len(key) > MAX_MEMORY_KEY_CHARS:
        raise ValueError(f"memory_key exceeds {MAX_MEMORY_KEY_CHARS} characters")
    if not MEMORY_KEY_PATTERN.fullmatch(key):
        raise ValueError(
            "memory_key must use lowercase words separated by '.', '_' or '-'"
        )
    return key


def _optional_text(value: object) -> str | None:
    if value in (None, ""):
        return None
    return str(value)


def _clean_event_id(value: object, *, field_name: str) -> str:
    identifier = str(value).strip()
    if not identifier:
        raise ValueError(f"{field_name} must not be empty")
    if len(identifier) > MAX_EVENT_ID_CHARS or not EVENT_ID_PATTERN.fullmatch(identifier):
        raise ValueError(
            f"{field_name} must start with an alphanumeric character and use only "
            "letters, digits, '.', '_', ':', '/', or '-'"
        )
    return identifier


def _clean_adjudication_text(value: object, *, field_name: str) -> str:
    text = re.sub(r"\s+", " ", str(value)).strip()
    if not text:
        raise ValueError(f"{field_name} must not be empty")
    if len(text) > MAX_ADJUDICATION_TEXT_CHARS:
        raise ValueError(
            f"{field_name} exceeds {MAX_ADJUDICATION_TEXT_CHARS} characters"
        )
    return text


def _validate_conflict_candidate(candidate: ConflictCandidate) -> None:
    if candidate.kind not in {item.value for item in FactKind}:
        raise MemoryCorruptionError(
            f"conflict candidate {candidate.candidate_id} has unknown kind"
        )
    if not _normal_form(candidate.content):
        raise MemoryCorruptionError(
            f"conflict candidate {candidate.candidate_id} has empty content"
        )
    if len(candidate.content) > MAX_FACT_CHARS:
        raise MemoryCorruptionError(
            f"conflict candidate {candidate.candidate_id} content is too long"
        )
    if not candidate.evidence_ids or len(set(candidate.evidence_ids)) != len(
        candidate.evidence_ids
    ):
        raise MemoryCorruptionError(
            f"conflict candidate {candidate.candidate_id} needs unique evidence"
        )
    if candidate.occurrences != len(candidate.evidence_ids):
        raise MemoryCorruptionError(
            f"conflict candidate {candidate.candidate_id} has inconsistent occurrences"
        )
    if not 1 <= candidate.maximum_importance <= 5:
        raise MemoryCorruptionError(
            f"conflict candidate {candidate.candidate_id} has invalid importance"
        )
    first = _parse_timestamp(candidate.first_seen)
    last = _parse_timestamp(candidate.last_seen)
    if last < first:
        raise MemoryCorruptionError(
            f"conflict candidate {candidate.candidate_id} has reversed timestamps"
        )


def _validate_conflict_case(case: MemoryConflictCase) -> None:
    if case.revision < 1:
        raise MemoryCorruptionError("conflict revision must be >= 1")
    if not re.fullmatch(r"[0-9a-f]{64}", case.fingerprint):
        raise MemoryCorruptionError("conflict fingerprint must be a SHA-256 digest")
    if case.status not in {item.value for item in ConflictStatus}:
        raise MemoryCorruptionError(f"unsupported conflict status: {case.status}")
    if len(case.candidates) < 2:
        raise MemoryCorruptionError("conflict case needs at least two candidates")
    candidate_ids = [candidate.candidate_id for candidate in case.candidates]
    if candidate_ids != sorted(candidate_ids) or len(set(candidate_ids)) != len(
        candidate_ids
    ):
        raise MemoryCorruptionError("conflict candidate IDs must be unique and sorted")
    for candidate in case.candidates:
        expected_candidate_id = _conflict_candidate_id(
            case.memory_key, candidate.kind, candidate.content
        )
        if candidate.candidate_id != expected_candidate_id:
            raise MemoryCorruptionError(
                f"conflict candidate {candidate.candidate_id} has inconsistent identity"
            )
    incumbents = [candidate for candidate in case.candidates if candidate.incumbent]
    if len(incumbents) > 1:
        raise MemoryCorruptionError("conflict case cannot have multiple incumbents")
    if bool(incumbents) != bool(case.active_entry_key):
        raise MemoryCorruptionError(
            "conflict incumbent must match the active curated entry snapshot"
        )
    if not case.observed_fact_ids or len(set(case.observed_fact_ids)) != len(
        case.observed_fact_ids
    ):
        raise MemoryCorruptionError("conflict observed fact IDs must be unique")
    observed = set(case.observed_fact_ids)
    if any(not set(candidate.evidence_ids) <= observed for candidate in case.candidates):
        raise MemoryCorruptionError("conflict candidate evidence was not observed")
    _parse_timestamp(case.detected_at)

    resolution_fields = (
        case.resolved_at,
        case.selected_candidate_id,
        case.resolution_event_id,
        case.resolution_actor,
        case.resolution_rationale,
        case.resulting_active_entry_key,
    )
    if case.status == ConflictStatus.OPEN.value:
        if any(value is not None for value in resolution_fields) or case.superseded_at:
            raise MemoryCorruptionError("open conflict cannot contain closure fields")
    elif case.status == ConflictStatus.RESOLVED.value:
        if any(value is None for value in resolution_fields) or case.superseded_at:
            raise MemoryCorruptionError("resolved conflict needs complete resolution fields")
        if case.selected_candidate_id not in candidate_ids:
            raise MemoryCorruptionError("resolved conflict selected an unknown candidate")
        _clean_event_id(case.resolution_event_id, field_name="resolution_event_id")
        _clean_adjudication_text(case.resolution_actor, field_name="resolution_actor")
        _clean_adjudication_text(
            case.resolution_rationale, field_name="resolution_rationale"
        )
        _parse_timestamp(str(case.resolved_at))
    else:
        if not case.superseded_at or any(value is not None for value in resolution_fields):
            raise MemoryCorruptionError(
                "superseded conflict needs superseded_at and no resolution fields"
            )
        _parse_timestamp(case.superseded_at)

    expected_fingerprint = _conflict_fingerprint(
        memory_key=case.memory_key,
        active_entry_key=case.active_entry_key,
        candidates=case.candidates,
        observed_fact_ids=case.observed_fact_ids,
    )
    if case.fingerprint != expected_fingerprint:
        raise MemoryCorruptionError(
            "conflict fingerprint does not match its evidence snapshot"
        )
    expected_id = _conflict_id(case.workspace_id, case.memory_key, case.fingerprint)
    if case.conflict_id != expected_id:
        raise MemoryCorruptionError("conflict ID does not match its evidence fingerprint")


def _validate_adjudication(event: ConflictAdjudication) -> None:
    if event.schema_version != ADJUDICATION_SCHEMA_VERSION:
        raise MemoryCorruptionError("unsupported conflict adjudication schema")
    if event.case_revision < 1:
        raise MemoryCorruptionError("adjudication case_revision must be >= 1")
    if not event.evidence_ids or len(set(event.evidence_ids)) != len(
        event.evidence_ids
    ):
        raise MemoryCorruptionError("adjudication evidence IDs must be unique")
    _parse_timestamp(event.resolved_at)


def _resolution_transaction_id(workspace_id: str, event_id: str) -> str:
    material = f"{workspace_id}\0{event_id}"
    digest = hashlib.sha256(material.encode("utf-8")).hexdigest()[:24]
    return f"resolution-{digest}"


def _transaction_intent_hash(transaction: ConflictResolutionTransaction) -> str:
    canonical = json.dumps(
        asdict(transaction),
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _validate_resolution_transaction(
    transaction: ConflictResolutionTransaction,
) -> None:
    if transaction.schema_version != RESOLUTION_TRANSACTION_SCHEMA_VERSION:
        raise MemoryCorruptionError("unsupported resolution transaction schema")
    expected_id = _resolution_transaction_id(
        transaction.workspace_id, transaction.event_id
    )
    if transaction.transaction_id != expected_id:
        raise MemoryCorruptionError(
            "resolution transaction ID does not match workspace and event"
        )
    if transaction.conflict_id != transaction.adjudication.conflict_id:
        raise MemoryCorruptionError(
            "resolution transaction and adjudication conflict IDs differ"
        )
    if transaction.event_id != transaction.adjudication.event_id:
        raise MemoryCorruptionError(
            "resolution transaction and adjudication event IDs differ"
        )
    if transaction.workspace_id != transaction.adjudication.workspace_id:
        raise MemoryScopeError(
            "resolution transaction and adjudication workspaces differ"
        )
    _parse_timestamp(transaction.prepared_at)
    for case in (*transaction.conflicts_before, *transaction.conflicts_after):
        if case.workspace_id != transaction.workspace_id:
            raise MemoryScopeError(
                f"transaction conflict {case.conflict_id} belongs to another workspace"
            )


_RESOLUTION_PHASE_ORDER = tuple(phase.value for phase in ResolutionPhase)


def _conflict_candidate_id(memory_key: str, kind: str, content: str) -> str:
    material = f"{memory_key}\0{kind}\0{_normal_form(content)}"
    digest = hashlib.sha256(material.encode("utf-8")).hexdigest()[:16]
    return f"candidate-{digest}"


def _conflict_id(workspace_id: str, memory_key: str, fingerprint: str) -> str:
    material = f"{workspace_id}\0{memory_key}\0{fingerprint}"
    digest = hashlib.sha256(material.encode("utf-8")).hexdigest()[:16]
    return f"conflict-{digest}"


def _entry_key(
    kind: str,
    content: str,
    *,
    memory_key: str | None = None,
    revision: int = 1,
) -> str:
    if memory_key is None:
        material = f"{kind}\0{_normal_form(content)}"
    else:
        material = (
            f"{memory_key}\0revision:{revision}\0{kind}\0{_normal_form(content)}"
        )
    return hashlib.sha256(material.encode("utf-8")).hexdigest()[:16]


def _proposal_signature(fact: MemoryFact) -> tuple[str, str]:
    return fact.kind, _normal_form(fact.content)


def _proposal_score(facts: list[MemoryFact]) -> tuple[int, int, datetime]:
    """Prefer stronger evidence; use recency only after importance and count."""

    return (
        max(fact.importance for fact in facts),
        len({fact.fact_id for fact in facts}),
        max(_parse_timestamp(fact.recorded_at) for fact in facts),
    )


def _candidate_from_facts(memory_key: str, facts: list[MemoryFact]) -> ConflictCandidate:
    representative = max(
        facts,
        key=lambda fact: (
            fact.importance,
            _parse_timestamp(fact.recorded_at),
            fact.fact_id,
        ),
    )
    timestamps = sorted(fact.recorded_at for fact in facts)
    evidence_ids = tuple(sorted({fact.fact_id for fact in facts}))
    return ConflictCandidate(
        candidate_id=_conflict_candidate_id(
            memory_key, representative.kind, representative.content
        ),
        kind=representative.kind,
        content=representative.content,
        evidence_ids=evidence_ids,
        occurrences=len(evidence_ids),
        maximum_importance=max(fact.importance for fact in facts),
        first_seen=timestamps[0],
        last_seen=timestamps[-1],
    )


def _candidate_from_entry(
    memory_key: str,
    entry: CuratedMemoryEntry,
    facts_by_id: Mapping[str, MemoryFact],
) -> ConflictCandidate:
    importance = max(
        (facts_by_id[fact_id].importance for fact_id in entry.evidence_ids if fact_id in facts_by_id),
        default=1,
    )
    return ConflictCandidate(
        candidate_id=_conflict_candidate_id(memory_key, entry.kind, entry.content),
        kind=entry.kind,
        content=entry.content,
        evidence_ids=tuple(sorted(entry.evidence_ids)),
        occurrences=entry.occurrences,
        maximum_importance=importance,
        first_seen=entry.first_seen,
        last_seen=entry.last_seen,
        incumbent=True,
    )


def _conflict_fingerprint(
    *,
    memory_key: str,
    active_entry_key: str | None,
    candidates: tuple[ConflictCandidate, ...],
    observed_fact_ids: tuple[str, ...],
) -> str:
    material = json.dumps(
        {
            "memory_key": memory_key,
            "active_entry_key": active_entry_key,
            "candidates": [asdict(candidate) for candidate in candidates],
            "observed_fact_ids": observed_fact_ids,
        },
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


class WorkspaceMemory:
    """Durable project memory with an append log and a derived compact view.

    Layout under each project root::

        .learn_workbuddy/memory/
        ├── daily/YYYY-MM-DD.jsonl   # immutable source facts
        ├── curated.json             # canonical compact state
        ├── conflicts.json           # reviewable conflict snapshots
        ├── conflict-adjudications.jsonl  # append-only human decisions
        ├── conflict-resolution-transactions.jsonl  # crash recovery journal
        └── MEMORY.md                # human/prompt-facing derived view

    The teaching namespace deliberately avoids writing into a real product's
    state directory.  Resolving ``project_dir`` before deriving ``workspace_id``
    also prevents two relative paths to the same project from creating
    different logical scopes.
    """

    def __init__(self, project_dir: Path):
        self.project_dir = Path(project_dir).expanduser().resolve()
        self.workspace_id = hashlib.sha256(
            str(self.project_dir).encode("utf-8")
        ).hexdigest()[:16]
        self.memory_dir = self.project_dir / ".learn_workbuddy" / "memory"
        self.daily_dir = self.memory_dir / "daily"
        self.memory_file = self.memory_dir / "MEMORY.md"
        self.curated_file = self.memory_dir / "curated.json"
        self.conflict_file = self.memory_dir / "conflicts.json"
        self.adjudication_file = self.memory_dir / "conflict-adjudications.jsonl"
        self.resolution_transaction_file = (
            self.memory_dir / "conflict-resolution-transactions.jsonl"
        )
        self.daily_dir.mkdir(parents=True, exist_ok=True)
        self._recover_resolution_transactions()

    def daily_log_path(self, day: date) -> Path:
        """Return the scoped path for one UTC day's append-only fact log."""

        return self.daily_dir / f"{day.isoformat()}.jsonl"

    def today_log_path(self) -> Path:
        return self.daily_log_path(datetime.now(timezone.utc).date())

    def append_daily_log(
        self,
        content: str,
        *,
        kind: str | FactKind = FactKind.OUTCOME,
        importance: int = 3,
        source: str = "agent",
        evidence: Mapping[str, str] | None = None,
        memory_key: str | None = None,
        recorded_at: datetime | None = None,
        fact_id: str | None = None,
    ) -> MemoryFact:
        """Append one validated fact as exactly one JSONL record.

        ``O_APPEND`` plus one ``os.write`` keeps concurrent writers from
        seeking to and overwriting the same offset.  The subsequent ``fsync``
        makes successful return mean the record reached the filesystem.  A
        crash may still leave a partial final line; readers ignore only that
        unterminated tail and reject corruption in the middle of a log.
        """

        text = re.sub(r"\s+", " ", content).strip()
        if not text:
            raise ValueError("memory fact content must not be empty")
        if len(text) > MAX_FACT_CHARS:
            raise ValueError(f"memory fact exceeds {MAX_FACT_CHARS} characters")
        if not 1 <= importance <= 5:
            raise ValueError("importance must be between 1 and 5")

        kind_value = kind.value if isinstance(kind, FactKind) else str(kind)
        if kind_value not in {item.value for item in FactKind}:
            raise ValueError(f"unknown fact kind: {kind_value}")

        timestamp = _as_utc(recorded_at)
        normalized_memory_key = (
            None if memory_key is None else _clean_memory_key(memory_key)
        )
        fact = MemoryFact(
            fact_id=fact_id or uuid.uuid4().hex,
            workspace_id=self.workspace_id,
            recorded_at=timestamp.isoformat().replace("+00:00", "Z"),
            kind=kind_value,
            content=text,
            memory_key=normalized_memory_key,
            source=source,
            importance=importance,
            evidence=dict(evidence or {}),
        )
        encoded = (json.dumps(asdict(fact), ensure_ascii=False, sort_keys=True) + "\n").encode(
            "utf-8"
        )
        path = self.daily_log_path(timestamp.date())
        descriptor = os.open(path, os.O_APPEND | os.O_CREAT | os.O_WRONLY, 0o600)
        try:
            written = os.write(descriptor, encoded)
            if written != len(encoded):
                raise OSError(f"short memory write: {written}/{len(encoded)} bytes")
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
        return fact

    def list_logs(self) -> list[Path]:
        return sorted(self.daily_dir.glob("????-??-??.jsonl"))

    def _read_log(self, path: Path) -> list[MemoryFact]:
        if not path.exists():
            return []

        lines = path.read_text(encoding="utf-8").splitlines(keepends=True)
        facts: list[MemoryFact] = []
        for index, line in enumerate(lines, start=1):
            if not line.strip():
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError as exc:
                is_partial_tail = index == len(lines) and not line.endswith("\n")
                if is_partial_tail:
                    break
                raise MemoryCorruptionError(f"{path.name}:{index}: invalid JSON") from exc
            fact = MemoryFact.from_dict(payload)
            if fact.schema_version not in SUPPORTED_FACT_SCHEMAS:
                raise MemoryCorruptionError(
                    f"{path.name}:{index}: unsupported schema {fact.schema_version}"
                )
            if fact.workspace_id != self.workspace_id:
                raise MemoryScopeError(
                    f"{path.name}:{index} belongs to workspace {fact.workspace_id}"
                )
            facts.append(fact)
        return facts

    def read_daily_facts(self, day: date | None = None) -> list[MemoryFact]:
        target = day or datetime.now(timezone.utc).date()
        return self._read_log(self.daily_log_path(target))

    def read_all_facts(self) -> list[MemoryFact]:
        facts = [fact for path in self.list_logs() for fact in self._read_log(path)]
        return sorted(facts, key=lambda item: (item.recorded_at, item.fact_id))

    def _atomic_write_text(self, path: Path, content: str) -> None:
        """Replace a complete file or leave the previous version untouched."""

        path.parent.mkdir(parents=True, exist_ok=True)
        descriptor, temporary_name = tempfile.mkstemp(
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
        )
        temporary = Path(temporary_name)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                handle.write(content)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, path)
            # fsync the directory entry as well as the file contents.  Without
            # this step, a power loss may preserve the temporary file data but
            # lose the rename that made it canonical.  Windows cannot open a
            # directory through os.open, so its safe fallback stops after the
            # synced temporary file and same-directory atomic replace.
            _fsync_directory(path.parent)
        finally:
            temporary.unlink(missing_ok=True)

    def _load_conflicts(self) -> list[MemoryConflictCase]:
        if not self.conflict_file.exists():
            return []
        try:
            payload = json.loads(self.conflict_file.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise MemoryCorruptionError("conflicts.json is not valid JSON") from exc
        if payload.get("workspace_id") != self.workspace_id:
            raise MemoryScopeError("conflict queue belongs to another workspace")
        if payload.get("schema_version") != CONFLICT_SCHEMA_VERSION:
            raise MemoryCorruptionError("unsupported conflict queue schema")
        cases = [
            MemoryConflictCase.from_dict(dict(item))
            for item in payload.get("cases", [])
        ]
        by_id = {case.conflict_id: case for case in cases}
        if len(by_id) != len(cases):
            raise MemoryCorruptionError("conflict IDs must be unique")
        revisions: set[tuple[str, int]] = set()
        open_keys: set[str] = set()
        for case in cases:
            if case.workspace_id != self.workspace_id:
                raise MemoryScopeError(
                    f"conflict {case.conflict_id} belongs to another workspace"
                )
            revision_key = (case.memory_key, case.revision)
            if revision_key in revisions:
                raise MemoryCorruptionError(
                    f"duplicate conflict revision for {case.memory_key}"
                )
            revisions.add(revision_key)
            if case.status == ConflictStatus.OPEN.value:
                if case.memory_key in open_keys:
                    raise MemoryCorruptionError(
                        f"multiple open conflicts for {case.memory_key}"
                    )
                open_keys.add(case.memory_key)
        return sorted(cases, key=lambda item: (item.memory_key, item.revision))

    def _save_conflicts(self, cases: list[MemoryConflictCase]) -> None:
        # Reuse the loader's invariants before replacing the canonical snapshot.
        ids = {case.conflict_id for case in cases}
        if len(ids) != len(cases):
            raise MemoryCorruptionError("conflict IDs must be unique")
        for case in cases:
            if case.workspace_id != self.workspace_id:
                raise MemoryScopeError("cannot save a conflict from another workspace")
            _validate_conflict_case(case)
        revisions = [(case.memory_key, case.revision) for case in cases]
        if len(revisions) != len(set(revisions)):
            raise MemoryCorruptionError("conflict revisions must be unique per memory_key")
        open_keys = [
            case.memory_key
            for case in cases
            if case.status == ConflictStatus.OPEN.value
        ]
        if len(open_keys) != len(set(open_keys)):
            raise MemoryCorruptionError("only one open conflict is allowed per memory_key")
        payload = {
            "schema_version": CONFLICT_SCHEMA_VERSION,
            "workspace_id": self.workspace_id,
            "cases": [
                asdict(case)
                for case in sorted(
                    cases, key=lambda item: (item.memory_key, item.revision)
                )
            ],
        }
        self._atomic_write_text(
            self.conflict_file,
            json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        )

    def list_conflicts(
        self,
        *,
        status: str | ConflictStatus | None = ConflictStatus.OPEN,
    ) -> list[MemoryConflictCase]:
        """Return deterministic review snapshots without exposing them to Prompt."""

        if status is None:
            expected = None
        else:
            try:
                expected = (
                    status if isinstance(status, ConflictStatus) else ConflictStatus(status)
                ).value
            except ValueError as exc:
                raise ValueError(f"unsupported conflict status: {status}") from exc
        return [
            case
            for case in self._load_conflicts()
            if expected is None or case.status == expected
        ]

    def _read_adjudications(self) -> list[ConflictAdjudication]:
        if not self.adjudication_file.exists():
            return []
        lines = self.adjudication_file.read_text(encoding="utf-8").splitlines(
            keepends=True
        )
        events: list[ConflictAdjudication] = []
        for index, line in enumerate(lines, start=1):
            if not line.endswith("\n") and index == len(lines):
                break
            try:
                payload = json.loads(line)
            except json.JSONDecodeError as exc:
                raise MemoryCorruptionError(
                    f"invalid adjudication JSON at line {index}"
                ) from exc
            event = ConflictAdjudication.from_dict(payload)
            if event.workspace_id != self.workspace_id:
                raise MemoryScopeError(
                    f"adjudication {event.event_id} belongs to another workspace"
                )
            events.append(event)
        if len({event.event_id for event in events}) != len(events):
            raise MemoryCorruptionError("adjudication event IDs must be unique")
        return events

    def list_adjudications(self) -> list[ConflictAdjudication]:
        return self._read_adjudications()

    def _append_adjudication(self, event: ConflictAdjudication) -> None:
        _validate_adjudication(event)
        if event.workspace_id != self.workspace_id:
            raise MemoryScopeError("cannot append an adjudication for another workspace")
        encoded = (
            json.dumps(asdict(event), ensure_ascii=False, sort_keys=True) + "\n"
        ).encode("utf-8")
        _discard_incomplete_jsonl_tail(self.adjudication_file)
        descriptor = os.open(
            self.adjudication_file,
            os.O_APPEND | os.O_CREAT | os.O_WRONLY,
            0o600,
        )
        try:
            written = os.write(descriptor, encoded)
            if written != len(encoded):
                raise OSError(
                    f"short adjudication write: {written}/{len(encoded)} bytes"
                )
            os.fsync(descriptor)
        finally:
            os.close(descriptor)

    def _resolution_checkpoint(self, _name: str) -> None:
        """Fault-injection seam used to prove recovery at durable boundaries."""

    @staticmethod
    def _curated_snapshot(entries: Iterable[CuratedMemoryEntry]) -> str:
        ordered = sorted(
            entries,
            key=lambda item: (
                item.kind,
                item.memory_key or "",
                item.revision,
                item.key,
            ),
        )
        return json.dumps(
            [asdict(item) for item in ordered],
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )

    @staticmethod
    def _conflict_snapshot(cases: Iterable[MemoryConflictCase]) -> str:
        ordered = sorted(cases, key=lambda item: (item.memory_key, item.revision))
        return json.dumps(
            [asdict(item) for item in ordered],
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )

    def _append_resolution_phase(
        self,
        transaction: ConflictResolutionTransaction,
        phase: ResolutionPhase,
    ) -> None:
        _validate_resolution_transaction(transaction)
        if transaction.workspace_id != self.workspace_id:
            raise MemoryScopeError(
                "cannot append a resolution transaction for another workspace"
            )
        intent_hash = _transaction_intent_hash(transaction)
        payload: dict[str, object] = {
            "schema_version": RESOLUTION_TRANSACTION_SCHEMA_VERSION,
            "workspace_id": self.workspace_id,
            "transaction_id": transaction.transaction_id,
            "phase": phase.value,
            "recorded_at": _iso(),
            "intent_sha256": intent_hash,
        }
        if phase is ResolutionPhase.PREPARED:
            payload["intent"] = asdict(transaction)
        encoded = (
            json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n"
        ).encode("utf-8")
        _discard_incomplete_jsonl_tail(self.resolution_transaction_file)
        descriptor = os.open(
            self.resolution_transaction_file,
            os.O_APPEND | os.O_CREAT | os.O_WRONLY,
            0o600,
        )
        try:
            written = os.write(descriptor, encoded)
            if written != len(encoded):
                raise OSError(
                    f"short resolution journal write: {written}/{len(encoded)} bytes"
                )
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
        self._resolution_checkpoint(f"after_{phase.value}")

    def _read_resolution_transactions(
        self,
    ) -> list[tuple[ConflictResolutionTransaction, tuple[str, ...]]]:
        if not self.resolution_transaction_file.exists():
            return []
        lines = self.resolution_transaction_file.read_text(
            encoding="utf-8"
        ).splitlines(keepends=True)
        states: dict[str, dict[str, object]] = {}
        for index, line in enumerate(lines, start=1):
            if not line.endswith("\n") and index == len(lines):
                break
            try:
                payload = json.loads(line)
            except json.JSONDecodeError as exc:
                raise MemoryCorruptionError(
                    f"invalid resolution journal JSON at line {index}"
                ) from exc
            if payload.get("schema_version") != RESOLUTION_TRANSACTION_SCHEMA_VERSION:
                raise MemoryCorruptionError(
                    f"unsupported resolution journal schema at line {index}"
                )
            if payload.get("workspace_id") != self.workspace_id:
                raise MemoryScopeError(
                    f"resolution journal line {index} belongs to another workspace"
                )
            if not isinstance(payload.get("transaction_id"), str):
                raise MemoryCorruptionError(
                    f"invalid resolution transaction ID at line {index}"
                )
            transaction_id = _clean_event_id(
                payload["transaction_id"], field_name="transaction_id"
            )
            try:
                phase = ResolutionPhase(payload.get("phase"))
            except (TypeError, ValueError) as exc:
                raise MemoryCorruptionError(
                    f"unsupported resolution phase at line {index}"
                ) from exc
            try:
                _parse_timestamp(str(payload["recorded_at"]))
            except KeyError as exc:
                raise MemoryCorruptionError(
                    f"resolution journal line {index} has no timestamp"
                ) from exc
            intent_hash = str(payload.get("intent_sha256", ""))
            if not re.fullmatch(r"[0-9a-f]{64}", intent_hash):
                raise MemoryCorruptionError(
                    f"invalid resolution intent hash at line {index}"
                )

            state = states.get(transaction_id)
            if phase is ResolutionPhase.PREPARED:
                if state is not None:
                    raise MemoryCorruptionError(
                        f"resolution transaction {transaction_id} was prepared twice"
                    )
                intent = payload.get("intent")
                if not isinstance(intent, dict):
                    raise MemoryCorruptionError(
                        f"prepared transaction {transaction_id} has no intent"
                    )
                transaction = ConflictResolutionTransaction.from_dict(intent)
                if transaction.transaction_id != transaction_id:
                    raise MemoryCorruptionError(
                        "resolution journal transaction ID differs from its intent"
                    )
                if _transaction_intent_hash(transaction) != intent_hash:
                    raise MemoryCorruptionError(
                        f"resolution transaction {transaction_id} intent was modified"
                    )
                state = {
                    "transaction": transaction,
                    "intent_hash": intent_hash,
                    "phases": [],
                }
                states[transaction_id] = state
            elif state is None:
                raise MemoryCorruptionError(
                    f"resolution transaction {transaction_id} has no prepared intent"
                )
            elif state["intent_hash"] != intent_hash:
                raise MemoryCorruptionError(
                    f"resolution transaction {transaction_id} changed intent"
                )

            phases = state["phases"]
            assert isinstance(phases, list)
            phases.append(phase.value)

        result: list[tuple[ConflictResolutionTransaction, tuple[str, ...]]] = []
        for transaction_id, state in states.items():
            phases = tuple(state["phases"])
            expected = _RESOLUTION_PHASE_ORDER[: len(phases)]
            if phases != expected:
                raise MemoryCorruptionError(
                    f"resolution transaction {transaction_id} has invalid phase order"
                )
            transaction = state["transaction"]
            assert isinstance(transaction, ConflictResolutionTransaction)
            result.append((transaction, phases))
        return result

    def _ensure_curated_transaction_state(
        self, transaction: ConflictResolutionTransaction
    ) -> None:
        before = list(transaction.curated_before)
        target = list(transaction.curated_after)
        current = self._load_curated()
        current_snapshot = self._curated_snapshot(current)
        before_snapshot = self._curated_snapshot(before)
        target_snapshot = self._curated_snapshot(target)
        if current_snapshot == target_snapshot:
            if self.curated_file.exists():
                rendered = self._render_memory(target)
                existing = (
                    self.memory_file.read_text(encoding="utf-8")
                    if self.memory_file.exists()
                    else None
                )
                if existing != rendered:
                    self._atomic_write_text(self.memory_file, rendered)
                    self._resolution_checkpoint("after_memory_projection_write")
            return
        if current_snapshot != before_snapshot:
            raise MemoryCorruptionError(
                f"resolution transaction {transaction.transaction_id} found "
                "unexpected curated state"
            )
        self._save_curated(target)
        self._resolution_checkpoint("after_curated_write")

    def _ensure_conflict_transaction_state(
        self, transaction: ConflictResolutionTransaction
    ) -> None:
        before = list(transaction.conflicts_before)
        target = list(transaction.conflicts_after)
        current = self._load_conflicts()
        current_snapshot = self._conflict_snapshot(current)
        if current_snapshot == self._conflict_snapshot(target):
            return
        if current_snapshot != self._conflict_snapshot(before):
            raise MemoryCorruptionError(
                f"resolution transaction {transaction.transaction_id} found "
                "unexpected conflict state"
            )
        self._save_conflicts(target)
        self._resolution_checkpoint("after_conflict_write")

    def _ensure_adjudication_transaction_state(
        self, transaction: ConflictResolutionTransaction
    ) -> None:
        existing = next(
            (
                event
                for event in self._read_adjudications()
                if event.event_id == transaction.event_id
            ),
            None,
        )
        if existing is not None:
            if existing != transaction.adjudication:
                raise MemoryCorruptionError(
                    f"resolution transaction {transaction.transaction_id} found "
                    "a different adjudication for its event ID"
                )
            return
        self._append_adjudication(transaction.adjudication)
        self._resolution_checkpoint("after_audit_write")

    def _complete_resolution_transaction(
        self,
        transaction: ConflictResolutionTransaction,
        completed_phases: Iterable[str],
    ) -> None:
        completed = set(completed_phases)
        self._ensure_curated_transaction_state(transaction)
        if ResolutionPhase.CURATED_APPLIED.value not in completed:
            self._append_resolution_phase(
                transaction, ResolutionPhase.CURATED_APPLIED
            )
        self._ensure_conflict_transaction_state(transaction)
        if ResolutionPhase.CONFLICT_CLOSED.value not in completed:
            self._append_resolution_phase(transaction, ResolutionPhase.CONFLICT_CLOSED)
        self._ensure_adjudication_transaction_state(transaction)
        if ResolutionPhase.AUDIT_APPENDED.value not in completed:
            self._append_resolution_phase(transaction, ResolutionPhase.AUDIT_APPENDED)
        if ResolutionPhase.COMMITTED.value not in completed:
            self._append_resolution_phase(transaction, ResolutionPhase.COMMITTED)

    def _recover_resolution_transactions(self) -> None:
        for transaction, phases in self._read_resolution_transactions():
            if phases[-1] == ResolutionPhase.COMMITTED.value:
                continue
            self._complete_resolution_transaction(transaction, phases)

    def _queue_conflict(
        self,
        *,
        memory_key: str,
        current: CuratedMemoryEntry | None,
        winner_facts: list[list[MemoryFact]],
        all_keyed_facts: list[MemoryFact],
        facts_by_id: Mapping[str, MemoryFact],
        cases: list[MemoryConflictCase],
        detected_at: datetime,
    ) -> tuple[MemoryConflictCase, bool]:
        candidates = [
            _candidate_from_facts(memory_key, facts) for facts in winner_facts
        ]
        if current is not None:
            candidates.append(
                _candidate_from_entry(memory_key, current, facts_by_id)
            )
        ordered = tuple(sorted(candidates, key=lambda item: item.candidate_id))
        observed_fact_ids = tuple(
            sorted(
                {fact.fact_id for fact in all_keyed_facts}
                | {
                    evidence_id
                    for candidate in ordered
                    for evidence_id in candidate.evidence_ids
                }
            )
        )
        fingerprint = _conflict_fingerprint(
            memory_key=memory_key,
            active_entry_key=None if current is None else current.key,
            candidates=ordered,
            observed_fact_ids=observed_fact_ids,
        )
        conflict_id = _conflict_id(self.workspace_id, memory_key, fingerprint)
        existing = next(
            (case for case in cases if case.conflict_id == conflict_id), None
        )
        if existing is not None:
            return existing, False

        timestamp = _iso(detected_at)
        for case in cases:
            if (
                case.memory_key == memory_key
                and case.status == ConflictStatus.OPEN.value
            ):
                case.status = ConflictStatus.SUPERSEDED.value
                case.superseded_at = timestamp
        revision = 1 + max(
            (case.revision for case in cases if case.memory_key == memory_key),
            default=0,
        )
        case = MemoryConflictCase(
            conflict_id=conflict_id,
            workspace_id=self.workspace_id,
            memory_key=memory_key,
            revision=revision,
            fingerprint=fingerprint,
            status=ConflictStatus.OPEN.value,
            candidates=ordered,
            observed_fact_ids=observed_fact_ids,
            active_entry_key=None if current is None else current.key,
            detected_at=timestamp,
        )
        _validate_conflict_case(case)
        cases.append(case)
        return case, True

    @staticmethod
    def _resolved_case_for(
        cases: list[MemoryConflictCase],
        memory_key: str,
        active_entry_key: str | None,
    ) -> MemoryConflictCase | None:
        matching = [
            case
            for case in cases
            if case.memory_key == memory_key
            and case.status == ConflictStatus.RESOLVED.value
            and case.resulting_active_entry_key == active_entry_key
        ]
        return max(matching, key=lambda item: item.revision, default=None)

    def resolve_conflict(
        self,
        conflict_id: str,
        selected_candidate_id: str,
        *,
        expected_revision: int,
        actor: str,
        rationale: str,
        event_id: str,
        resolved_at: datetime | None = None,
    ) -> ConflictAdjudication:
        """Apply one explicit choice while retaining all losing evidence."""

        clean_conflict_id = _clean_event_id(conflict_id, field_name="conflict_id")
        clean_candidate_id = _clean_event_id(
            selected_candidate_id, field_name="selected_candidate_id"
        )
        clean_event_id = _clean_event_id(event_id, field_name="event_id")
        clean_actor = _clean_adjudication_text(actor, field_name="actor")
        clean_rationale = _clean_adjudication_text(
            rationale, field_name="rationale"
        )
        if isinstance(expected_revision, bool) or not isinstance(expected_revision, int):
            raise TypeError("expected_revision must be an integer")
        if expected_revision < 1:
            raise ValueError("expected_revision must be >= 1")

        self._recover_resolution_transactions()
        existing_events = self._read_adjudications()
        duplicate = next(
            (event for event in existing_events if event.event_id == clean_event_id),
            None,
        )
        if duplicate is not None:
            if (
                duplicate.conflict_id == clean_conflict_id
                and duplicate.case_revision == expected_revision
                and duplicate.selected_candidate_id == clean_candidate_id
                and duplicate.actor == clean_actor
                and duplicate.rationale == clean_rationale
            ):
                return duplicate
            raise ConflictResolutionError(
                f"adjudication event {clean_event_id} was already used differently"
            )

        cases = self._load_conflicts()
        case = next(
            (item for item in cases if item.conflict_id == clean_conflict_id),
            None,
        )
        if case is None:
            raise ConflictResolutionError(f"unknown conflict: {clean_conflict_id}")
        if case.revision != expected_revision:
            raise StaleConflictResolutionError(
                f"conflict revision changed from {expected_revision} to {case.revision}"
            )
        if case.status != ConflictStatus.OPEN.value:
            raise StaleConflictResolutionError(
                f"conflict {clean_conflict_id} is {case.status}, not open"
            )
        selected = next(
            (
                candidate
                for candidate in case.candidates
                if candidate.candidate_id == clean_candidate_id
            ),
            None,
        )
        if selected is None:
            raise ConflictResolutionError(
                f"candidate {clean_candidate_id} is not part of {clean_conflict_id}"
            )

        facts = self.read_all_facts()
        entries = self._load_curated()
        current = next(
            (
                entry
                for entry in entries
                if entry.memory_key == case.memory_key
                and entry.status == CuratedStatus.ACTIVE.value
            ),
            None,
        )
        current_key = None if current is None else current.key
        if current_key != case.active_entry_key:
            raise StaleConflictResolutionError(
                "active curated memory changed after this conflict was detected"
            )
        current_observed = tuple(
            sorted(
                {
                    fact.fact_id
                    for fact in facts
                    if fact.memory_key == case.memory_key
                }
                | (set() if current is None else set(current.evidence_ids))
            )
        )
        if current_observed != case.observed_fact_ids:
            raise StaleConflictResolutionError(
                "workspace evidence changed after this conflict was detected"
            )

        curated_before = tuple(deepcopy(entries))
        conflicts_before = tuple(deepcopy(cases))
        if selected.incumbent:
            if current is None:
                raise MemoryCorruptionError("conflict incumbent is no longer active")
            resulting_key = current.key
        else:
            revision = 1 if current is None else current.revision + 1
            resulting_key = _entry_key(
                selected.kind,
                selected.content,
                memory_key=case.memory_key,
                revision=revision,
            )
            if any(entry.key == resulting_key for entry in entries):
                raise MemoryCorruptionError(
                    f"curated revision key collision for {case.memory_key}"
                )
            new_entry = CuratedMemoryEntry(
                key=resulting_key,
                kind=selected.kind,
                content=selected.content,
                first_seen=selected.first_seen,
                last_seen=selected.last_seen,
                evidence_ids=list(selected.evidence_ids),
                occurrences=selected.occurrences,
                memory_key=case.memory_key,
                revision=revision,
                status=CuratedStatus.ACTIVE.value,
                supersedes=None if current is None else current.key,
            )
            if current is not None:
                current.status = CuratedStatus.SUPERSEDED.value
                current.superseded_by = new_entry.key
            entries.append(new_entry)

        timestamp = _iso(resolved_at)
        case.status = ConflictStatus.RESOLVED.value
        case.resolved_at = timestamp
        case.selected_candidate_id = selected.candidate_id
        case.resolution_event_id = clean_event_id
        case.resolution_actor = clean_actor
        case.resolution_rationale = clean_rationale
        case.resulting_active_entry_key = resulting_key

        event = ConflictAdjudication(
            event_id=clean_event_id,
            workspace_id=self.workspace_id,
            conflict_id=case.conflict_id,
            case_revision=case.revision,
            selected_candidate_id=selected.candidate_id,
            actor=clean_actor,
            rationale=clean_rationale,
            resolved_at=timestamp,
            prior_active_entry_key=current_key,
            resulting_active_entry_key=resulting_key,
            evidence_ids=selected.evidence_ids,
        )
        transaction = ConflictResolutionTransaction(
            transaction_id=_resolution_transaction_id(
                self.workspace_id, clean_event_id
            ),
            workspace_id=self.workspace_id,
            conflict_id=case.conflict_id,
            event_id=clean_event_id,
            prepared_at=timestamp,
            curated_before=curated_before,
            curated_after=tuple(deepcopy(entries)),
            conflicts_before=conflicts_before,
            conflicts_after=tuple(deepcopy(cases)),
            adjudication=event,
        )
        _validate_resolution_transaction(transaction)
        self._append_resolution_phase(transaction, ResolutionPhase.PREPARED)
        self._complete_resolution_transaction(
            transaction, (ResolutionPhase.PREPARED.value,)
        )
        return event

    def _load_curated(self) -> list[CuratedMemoryEntry]:
        if not self.curated_file.exists():
            return []
        try:
            payload = json.loads(self.curated_file.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise MemoryCorruptionError("curated.json is not valid JSON") from exc
        if payload.get("workspace_id") != self.workspace_id:
            raise MemoryScopeError("curated memory belongs to another workspace")
        if payload.get("schema_version") not in SUPPORTED_CURATED_SCHEMAS:
            raise MemoryCorruptionError("unsupported curated memory schema")
        entries = [
            CuratedMemoryEntry.from_dict(item)
            for item in payload.get("entries", [])
        ]
        self._validate_curated(entries)
        return entries

    @staticmethod
    def _validate_curated(entries: list[CuratedMemoryEntry]) -> None:
        """Reject ambiguous or broken lifecycle graphs before prompt projection."""

        by_key = {entry.key: entry for entry in entries}
        if len(by_key) != len(entries):
            raise MemoryCorruptionError("curated entry keys must be unique")
        active_by_memory_key: dict[str, CuratedMemoryEntry] = {}
        for entry in entries:
            if entry.occurrences != len(set(entry.evidence_ids)):
                raise MemoryCorruptionError(
                    f"curated entry {entry.key} has inconsistent evidence count"
                )
            if entry.memory_key is None:
                if (
                    entry.revision != 1
                    or entry.status != CuratedStatus.ACTIVE.value
                    or entry.supersedes
                    or entry.superseded_by
                ):
                    raise MemoryCorruptionError(
                        f"legacy entry {entry.key} cannot have revision lifecycle"
                    )
                continue
            if entry.memory_key is not None and entry.status == CuratedStatus.ACTIVE.value:
                previous = active_by_memory_key.get(entry.memory_key)
                if previous is not None:
                    raise MemoryCorruptionError(
                        f"multiple active revisions for memory_key {entry.memory_key}"
                    )
                active_by_memory_key[entry.memory_key] = entry
            if entry.status == CuratedStatus.ACTIVE.value and entry.superseded_by:
                raise MemoryCorruptionError(
                    f"active entry {entry.key} cannot have superseded_by"
                )
            if entry.status == CuratedStatus.SUPERSEDED.value and not entry.superseded_by:
                raise MemoryCorruptionError(
                    f"superseded entry {entry.key} needs superseded_by"
                )
            if entry.revision == 1 and entry.supersedes:
                raise MemoryCorruptionError(
                    f"first revision {entry.key} cannot supersede another entry"
                )
            if entry.revision > 1 and not entry.supersedes:
                raise MemoryCorruptionError(
                    f"revision {entry.key} needs a supersedes link"
                )
        keyed_domains = {
            entry.memory_key for entry in entries if entry.memory_key is not None
        }
        missing_active = sorted(keyed_domains - set(active_by_memory_key))
        if missing_active:
            raise MemoryCorruptionError(
                "curated lifecycle has no active revision for: "
                + ", ".join(missing_active)
            )
        for entry in entries:
            if entry.superseded_by:
                successor = by_key.get(entry.superseded_by)
                if successor is None or successor.supersedes != entry.key:
                    raise MemoryCorruptionError(
                        f"entry {entry.key} has a broken superseded_by link"
                    )
            if entry.supersedes:
                previous = by_key.get(entry.supersedes)
                if previous is None or previous.superseded_by != entry.key:
                    raise MemoryCorruptionError(
                        f"entry {entry.key} has a broken supersedes link"
                    )
                if previous.memory_key != entry.memory_key:
                    raise MemoryCorruptionError(
                        f"entry {entry.key} supersedes another conflict domain"
                    )
                if entry.revision != previous.revision + 1:
                    raise MemoryCorruptionError(
                        f"entry {entry.key} has a non-contiguous revision"
                    )

    def _render_memory(self, entries: Iterable[CuratedMemoryEntry]) -> str:
        groups: dict[str, list[CuratedMemoryEntry]] = {
            kind.value: [] for kind in FactKind if kind is not FactKind.OUTCOME
        }
        for entry in entries:
            if entry.status != CuratedStatus.ACTIVE.value:
                continue
            groups.setdefault(entry.kind, []).append(entry)

        labels = {
            FactKind.DECISION.value: "Decisions",
            FactKind.CONVENTION.value: "Conventions",
            FactKind.PITFALL.value: "Pitfalls",
        }
        lines = [
            "# Workspace Memory",
            "",
            "Derived from append-only project facts. Edit the source log or policy, not this view.",
        ]
        for kind in (
            FactKind.DECISION.value,
            FactKind.CONVENTION.value,
            FactKind.PITFALL.value,
        ):
            items = sorted(groups.get(kind, []), key=lambda item: (item.content, item.key))
            if not items:
                continue
            lines.extend(["", f"## {labels[kind]}", ""])
            for item in items:
                lines.append(
                    f"- {item.content} "
                    f"(seen {item.occurrences}x; evidence: {len(item.evidence_ids)})"
                )
        lines.append("")
        return "\n".join(lines)

    def _save_curated(self, entries: list[CuratedMemoryEntry]) -> None:
        self._validate_curated(entries)
        ordered = sorted(
            entries,
            key=lambda item: (
                item.kind,
                item.memory_key or "",
                item.revision,
                item.key,
            ),
        )
        payload = {
            "schema_version": SCHEMA_VERSION,
            "workspace_id": self.workspace_id,
            "entries": [asdict(item) for item in ordered],
        }
        # curated.json is canonical.  MEMORY.md is a replaceable projection for
        # humans and prompt assembly; both are written through atomic rename.
        self._atomic_write_text(
            self.curated_file,
            json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        )
        self._atomic_write_text(self.memory_file, self._render_memory(ordered))

    def read_memory_md(self) -> str:
        if not self.curated_file.exists():
            # A pre-migration teaching workspace may only have MEMORY.md.
            return self.memory_file.read_text(encoding="utf-8") if self.memory_file.exists() else ""

        # curated.json is canonical.  If a process stopped after committing it
        # but before refreshing MEMORY.md, the next read repairs the projection
        # instead of injecting stale memory into a new session.
        rendered = self._render_memory(self._load_curated())
        current = self.memory_file.read_text(encoding="utf-8") if self.memory_file.exists() else None
        if current != rendered:
            self._atomic_write_text(self.memory_file, rendered)
        return rendered

    def distill(
        self,
        *,
        policy: DistillPolicy | None = None,
        as_of: datetime | None = None,
    ) -> DistillReport:
        """Promote eligible facts without deleting their source evidence.

        Unkeyed facts preserve the original content-based behavior.  Facts
        with ``memory_key`` share one conflict domain: repeated, newer evidence
        may create a new active revision while the old revision and all source
        facts remain available for audit.  Equal-strength proposals fail
        closed instead of depending on filesystem or dictionary order.
        """

        active_policy = policy or DistillPolicy()
        observed_at = _as_utc(as_of)
        cutoff = observed_at - timedelta(days=active_policy.minimum_age_days)
        existing = self._load_curated()
        conflict_cases = self._load_conflicts()
        by_key = {entry.key: entry for entry in existing}
        processed_ids = {
            evidence_id for entry in existing for evidence_id in entry.evidence_ids
        }

        all_facts = self.read_all_facts()
        facts_by_id = {fact.fact_id: fact for fact in all_facts}
        aged = [
            fact
            for fact in all_facts
            if _parse_timestamp(fact.recorded_at) < cutoff
        ]
        candidates = [
            fact
            for fact in aged
            if fact.kind in active_policy.stable_kinds and fact.fact_id not in processed_ids
        ]

        created = 0
        updated = 0
        eligible = 0
        skipped = len(aged) - len(candidates)
        superseded = 0
        conflicts = 0
        stale = 0
        queued_conflicts = 0
        conflict_case_ids: list[str] = []
        conflicted_memory_keys: set[str] = set()
        changed = False
        conflicts_changed = False

        def distinct(facts: list[MemoryFact]) -> list[MemoryFact]:
            return list({fact.fact_id: fact for fact in facts}.values())

        def qualifies(facts: list[MemoryFact]) -> bool:
            return (
                max(fact.importance for fact in facts)
                >= active_policy.minimum_importance
                or len(facts) >= active_policy.repeat_threshold
            )

        def representative(facts: list[MemoryFact]) -> MemoryFact:
            return max(
                facts,
                key=lambda fact: (
                    fact.importance,
                    _parse_timestamp(fact.recorded_at),
                    fact.fact_id,
                ),
            )

        # Legacy facts intentionally keep their original content-derived key.
        # An upgrade must not infer conflict domains for existing workspaces.
        legacy_groups: dict[str, list[MemoryFact]] = {}
        for fact in candidates:
            if fact.memory_key is None:
                legacy_groups.setdefault(
                    _entry_key(fact.kind, fact.content), []
                ).append(fact)
        for key in sorted(legacy_groups):
            facts = distinct(legacy_groups[key])
            current = by_key.get(key)
            if current is None and not qualifies(facts):
                skipped += len(facts)
                continue

            eligible += len(facts)
            timestamps = sorted(fact.recorded_at for fact in facts)
            new_ids = {fact.fact_id for fact in facts}
            if current is None:
                # Preserve the original legacy projection: importance first,
                # then the earliest stable wording for deterministic display.
                chosen = min(
                    facts,
                    key=lambda fact: (
                        -fact.importance,
                        _parse_timestamp(fact.recorded_at),
                        fact.fact_id,
                    ),
                )
                by_key[key] = CuratedMemoryEntry(
                    key=key,
                    kind=chosen.kind,
                    content=chosen.content,
                    first_seen=timestamps[0],
                    last_seen=timestamps[-1],
                    evidence_ids=sorted(new_ids),
                    occurrences=len(new_ids),
                )
                created += 1
            else:
                merged_ids = sorted(set(current.evidence_ids) | new_ids)
                current.first_seen = min(current.first_seen, timestamps[0])
                current.last_seen = max(current.last_seen, timestamps[-1])
                current.evidence_ids = merged_ids
                current.occurrences = len(merged_ids)
                updated += 1
            changed = True

        active_by_memory_key = {
            entry.memory_key: entry
            for entry in existing
            if entry.memory_key is not None
            and entry.status == CuratedStatus.ACTIVE.value
        }
        keyed_groups: dict[
            str, dict[tuple[str, str], list[MemoryFact]]
        ] = {}
        for fact in candidates:
            if fact.memory_key is None:
                continue
            proposals = keyed_groups.setdefault(fact.memory_key, {})
            proposals.setdefault(_proposal_signature(fact), []).append(fact)

        for memory_key in sorted(keyed_groups):
            proposals = {
                signature: distinct(facts)
                for signature, facts in keyed_groups[memory_key].items()
            }
            current = active_by_memory_key.get(memory_key)

            # More evidence for the current value is an idempotent update, not
            # a new revision.  It also advances last_seen before challengers
            # are checked, preventing older evidence from rolling it back.
            if current is not None:
                current_signature = (current.kind, _normal_form(current.content))
                reinforcing = proposals.pop(current_signature, None)
                if reinforcing:
                    timestamps = sorted(fact.recorded_at for fact in reinforcing)
                    new_ids = {fact.fact_id for fact in reinforcing}
                    current.first_seen = min(current.first_seen, timestamps[0])
                    current.last_seen = max(current.last_seen, timestamps[-1])
                    current.evidence_ids = sorted(
                        set(current.evidence_ids) | new_ids
                    )
                    current.occurrences = len(current.evidence_ids)
                    eligible += len(reinforcing)
                    updated += 1
                    changed = True

            resolved_case = self._resolved_case_for(
                conflict_cases,
                memory_key,
                None if current is None else current.key,
            )

            qualified: list[tuple[tuple[str, str], list[MemoryFact]]] = []
            for signature, facts in proposals.items():
                if resolved_case is not None:
                    candidate_id = _conflict_candidate_id(
                        memory_key, signature[0], facts[0].content
                    )
                    reviewed = next(
                        (
                            candidate
                            for candidate in resolved_case.candidates
                            if candidate.candidate_id == candidate_id
                        ),
                        None,
                    )
                    if (
                        reviewed is not None
                        and candidate_id != resolved_case.selected_candidate_id
                        and tuple(sorted(fact.fact_id for fact in facts))
                        == reviewed.evidence_ids
                    ):
                        skipped += len(facts)
                        continue
                if not qualifies(facts):
                    skipped += len(facts)
                    continue
                if current is not None:
                    if len(facts) < active_policy.supersession_repeat_threshold:
                        skipped += len(facts)
                        continue
                    latest = max(
                        _parse_timestamp(fact.recorded_at) for fact in facts
                    )
                    if latest <= _parse_timestamp(current.last_seen):
                        skipped += len(facts)
                        stale += len(facts)
                        continue
                qualified.append((signature, facts))

            if not qualified:
                continue

            best_score = max(_proposal_score(facts) for _signature, facts in qualified)
            winners = [
                (signature, facts)
                for signature, facts in qualified
                if _proposal_score(facts) == best_score
            ]
            if len(winners) != 1:
                conflicts += 1
                skipped += sum(len(facts) for _signature, facts in qualified)
                conflicted_memory_keys.add(memory_key)
                case, created_case = self._queue_conflict(
                    memory_key=memory_key,
                    current=current,
                    winner_facts=[facts for _signature, facts in winners],
                    all_keyed_facts=[
                        fact for fact in all_facts if fact.memory_key == memory_key
                    ],
                    facts_by_id=facts_by_id,
                    cases=conflict_cases,
                    detected_at=observed_at,
                )
                conflict_case_ids.append(case.conflict_id)
                if created_case:
                    queued_conflicts += 1
                    conflicts_changed = True
                continue

            winning_signature, winning_facts = winners[0]
            skipped += sum(
                len(facts)
                for signature, facts in qualified
                if signature != winning_signature
            )
            chosen = representative(winning_facts)
            timestamps = sorted(fact.recorded_at for fact in winning_facts)
            new_ids = sorted({fact.fact_id for fact in winning_facts})
            revision = 1 if current is None else current.revision + 1
            key = _entry_key(
                chosen.kind,
                chosen.content,
                memory_key=memory_key,
                revision=revision,
            )
            if key in by_key:
                raise MemoryCorruptionError(
                    f"curated revision key collision for {memory_key}"
                )
            entry = CuratedMemoryEntry(
                key=key,
                kind=chosen.kind,
                content=chosen.content,
                first_seen=timestamps[0],
                last_seen=timestamps[-1],
                evidence_ids=new_ids,
                occurrences=len(new_ids),
                memory_key=memory_key,
                revision=revision,
                status=CuratedStatus.ACTIVE.value,
                supersedes=None if current is None else current.key,
            )
            if current is not None:
                current.status = CuratedStatus.SUPERSEDED.value
                current.superseded_by = entry.key
                superseded += 1
            by_key[entry.key] = entry
            active_by_memory_key[memory_key] = entry
            eligible += len(winning_facts)
            created += 1
            changed = True

        closed_at = _iso(observed_at)
        for case in conflict_cases:
            if (
                case.status == ConflictStatus.OPEN.value
                and case.memory_key in keyed_groups
                and case.memory_key not in conflicted_memory_keys
            ):
                case.status = ConflictStatus.SUPERSEDED.value
                case.superseded_at = closed_at
                conflicts_changed = True

        if changed:
            self._save_curated(list(by_key.values()))
        if conflicts_changed:
            self._save_conflicts(conflict_cases)

        return DistillReport(
            scanned=len(aged),
            eligible=eligible,
            created=created,
            updated=updated,
            skipped=skipped,
            superseded=superseded,
            conflicts=conflicts,
            stale=stale,
            queued_conflicts=queued_conflicts,
            conflict_case_ids=tuple(conflict_case_ids),
        )

    def get_context_for_agent(self, *, recent_limit: int = MAX_CONTEXT_FACTS) -> str:
        """Build a bounded prompt block from curated and recent memory."""

        parts: list[str] = []
        curated = self.read_memory_md().strip()
        if curated:
            parts.append(curated)

        # Explicitly keyed facts belong to the curated lifecycle.  Projecting
        # raw challengers here would bypass the evidence threshold and expose
        # conflicting values before distillation resolves them.
        recent_candidates = [
            fact for fact in self.read_all_facts() if fact.memory_key is None
        ]
        recent = recent_candidates[-recent_limit:] if recent_limit > 0 else []
        if recent:
            lines = ["# Recent Workspace Facts", ""]
            lines.extend(
                f"- [{fact.kind}] {fact.content} ({fact.recorded_at[:10]})"
                for fact in recent
            )
            parts.append("\n".join(lines))
        return "\n\n".join(parts) if parts else "(no workspace memory yet)"


class MemoryAwareAgent:
    """Minimal provider loop showing where workspace memory enters a harness.

    The memory store is independent of the provider.  The loop loads a bounded
    view before each turn and exposes one structured ``write_memory`` tool.
    Tool-use blocks, rather than a provider stop string, determine whether
    another tool-result round is required.
    """

    def __init__(self, cwd: Path, memory: WorkspaceMemory):
        self.cwd = Path(cwd).resolve()
        self.memory = memory
        self.client = Anthropic(base_url=os.getenv("ANTHROPIC_BASE_URL"))
        self.model = os.getenv("MODEL_ID", "")
        if not self.model:
            raise SystemExit(
                "MODEL_ID is not set. Copy .env.example to .env and fill in "
                "ANTHROPIC_API_KEY and MODEL_ID (see README quick start)."
            )
        self.messages: list[dict] = []

    def _build_system(self) -> str:
        return f"""You are a coding agent working in {self.cwd}.

## Workspace memory
{self.memory.get_context_for_agent()}

Use write_memory only for durable project decisions, conventions, pitfalls,
or completed outcomes. Do not store greetings, guesses, secrets, or raw tool
output. Set memory_key for a replaceable project decision so later evidence
can supersede it safely. Memory supplements the user-facing reply; it never
replaces it."""

    @staticmethod
    def _build_tools() -> list[dict]:
        return [
            {
                "name": "bash",
                "description": "Run a shell command inside the workspace.",
                "input_schema": {
                    "type": "object",
                    "properties": {"command": {"type": "string"}},
                    "required": ["command"],
                },
            },
            {
                "name": "write_memory",
                "description": "Append one durable, project-scoped memory fact.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "content": {"type": "string"},
                        "kind": {
                            "type": "string",
                            "enum": [item.value for item in FactKind],
                        },
                        "importance": {
                            "type": "integer",
                            "minimum": 1,
                            "maximum": 5,
                        },
                        "memory_key": {
                            "type": "string",
                            "description": (
                                "Optional stable conflict domain such as "
                                "runtime.python-version"
                            ),
                            "pattern": MEMORY_KEY_PATTERN.pattern,
                            "maxLength": MAX_MEMORY_KEY_CHARS,
                        },
                    },
                    "required": ["content", "kind", "importance"],
                },
            },
        ]

    def chat(self, user_message: str) -> str:
        self.messages.append({"role": "user", "content": user_message})
        final_text = ""

        while True:
            response = self.client.messages.create(
                model=self.model,
                system=self._build_system(),
                messages=self.messages,
                tools=self._build_tools(),
                max_tokens=8_000,
            )
            self.messages.append({"role": "assistant", "content": response.content})
            final_text = "".join(
                block.text
                for block in response.content
                if getattr(block, "type", None) == "text"
            )
            tool_blocks = [
                block
                for block in response.content
                if getattr(block, "type", None) == "tool_use"
            ]
            if not tool_blocks:
                return final_text

            results = []
            for block in tool_blocks:
                if block.name == "write_memory":
                    fact = self.memory.append_daily_log(
                        str(block.input.get("content", "")),
                        kind=str(block.input.get("kind", FactKind.OUTCOME.value)),
                        importance=int(block.input.get("importance", 3)),
                        source="model_tool",
                        memory_key=(
                            None
                            if block.input.get("memory_key") in (None, "")
                            else str(block.input["memory_key"])
                        ),
                    )
                    output = f"memory fact appended: {fact.fact_id}"
                elif block.name == "bash":
                    output = self._run_bash(str(block.input.get("command", "")))
                else:
                    output = f"Error: unknown tool {block.name}"
                results.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": output,
                    }
                )
            self.messages.append({"role": "user", "content": results})

    def _run_bash(self, command: str) -> str:
        """Keep the inherited demo tool narrow; s04 owns permission policy."""

        dangerous = ("rm -rf /", "sudo", "shutdown", "reboot")
        if any(fragment in command for fragment in dangerous):
            return "Error: command blocked by the teaching safety guard"
        try:
            result = subprocess.run(
                command,
                shell=True,
                cwd=self.cwd,
                capture_output=True,
                text=True,
                timeout=120,
            )
        except subprocess.TimeoutExpired:
            return "Error: timeout after 120 seconds"
        output = (result.stdout + result.stderr).strip()
        return output[:50_000] if output else "(no output)"


def _print_report(report: DistillReport) -> None:
    print(
        "distill: "
        f"scanned={report.scanned}, eligible={report.eligible}, "
        f"created={report.created}, updated={report.updated}, skipped={report.skipped}, "
        f"superseded={report.superseded}, conflicts={report.conflicts}, "
        f"queued={report.queued_conflicts}, stale={report.stale}"
    )
    if report.conflict_case_ids:
        print("review:  " + ", ".join(report.conflict_case_ids))


def main() -> None:
    print("s10: Workspace Memory — append facts, distill durable knowledge")
    memory = WorkspaceMemory(WORKDIR)
    agent = MemoryAwareAgent(WORKDIR, memory)
    print(f"workspace: {memory.project_dir}")
    print(f"memory:    {memory.memory_dir}")
    print("commands: /memory /today /logs /distill /conflicts /resolve /reset q")

    while True:
        try:
            query = input("s10 >> ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if query.lower() in {"q", "quit", "exit"}:
            break
        if not query:
            continue
        if query == "/memory":
            print(memory.read_memory_md() or "(no curated workspace memory)")
            continue
        if query == "/today":
            facts = memory.read_daily_facts()
            for fact in facts:
                print(f"[{fact.kind}] {fact.content} ({fact.importance}/5)")
            if not facts:
                print("(no facts today)")
            continue
        if query == "/logs":
            for path in memory.list_logs():
                print(f"{path.name}: {len(memory._read_log(path))} facts")
            if not memory.list_logs():
                print("(no daily logs)")
            continue
        if query == "/distill":
            _print_report(memory.distill())
            continue
        if query == "/conflicts":
            cases = memory.list_conflicts()
            for case in cases:
                print(
                    f"{case.conflict_id} revision={case.revision} "
                    f"memory_key={case.memory_key}"
                )
                for candidate in case.candidates:
                    marker = " (current)" if candidate.incumbent else ""
                    print(
                        f"  {candidate.candidate_id}{marker}: {candidate.content} "
                        f"[{len(candidate.evidence_ids)} evidence]"
                    )
            if not cases:
                print("(no open memory conflicts)")
            continue
        if query.startswith("/resolve "):
            parts = query.split(maxsplit=5)
            if len(parts) != 6:
                print(
                    "usage: /resolve <conflict_id> <revision> "
                    "<candidate_id> <event_id> <rationale>"
                )
                continue
            _, conflict_id, revision, candidate_id, event_id, rationale = parts
            try:
                event = memory.resolve_conflict(
                    conflict_id,
                    candidate_id,
                    expected_revision=int(revision),
                    actor="local-cli-user",
                    rationale=rationale,
                    event_id=event_id,
                )
            except (ValueError, MemoryErrorBase) as exc:
                print(f"resolution rejected: {exc}")
            else:
                print(
                    f"resolved {event.conflict_id} -> "
                    f"{event.selected_candidate_id} ({event.event_id})"
                )
            continue
        if query == "/reset":
            agent.messages.clear()
            print("conversation reset; workspace memory retained")
            continue
        print(agent.chat(query))


if __name__ == "__main__":
    main()
