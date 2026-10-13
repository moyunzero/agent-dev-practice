"""S13 artifact evidence and context-pointer contracts."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path
from threading import Barrier, RLock

import pytest


ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def s13():
    name = "s13_output_externalization_test_module"
    spec = importlib.util.spec_from_file_location(
        name, ROOT / "s13_output_externalization" / "code.py"
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[name] = module
    spec.loader.exec_module(module)
    yield module
    sys.modules.pop(name, None)


class _OwnerFence:
    def __init__(self, owner, transaction, observation):
        self.owner = owner
        self.transaction = transaction
        self._observation = observation

    @property
    def observation(self):
        return self._observation

    def seal_absent(self):
        record = self.owner.records[self.transaction.transaction_id]
        if self.owner.change_generation_before_seal:
            record["generation"] += 1
            self.owner.change_generation_before_seal = False
            raise self.owner.s13.ArtifactOwnerGenerationChanged("owner changed")
        if record["generation"] != self._observation.generation:
            raise self.owner.s13.ArtifactOwnerGenerationChanged("owner changed")
        if record["presence"] is not self.owner.s13.ArtifactReferencePresence.ABSENT:
            raise self.owner.s13.ArtifactOwnerGenerationChanged("reference appeared")
        record["generation"] += 1
        record["absence_sealed"] = True
        self._observation = self.owner._observation(self.transaction.transaction_id)
        return self._observation


class _OwnerFenceContext:
    def __init__(self, owner, transaction):
        self.owner = owner
        self.transaction = transaction

    def __enter__(self):
        self.owner.lock.acquire()
        self.owner.inspections += 1
        self.owner.records.setdefault(
            self.transaction.transaction_id,
            {
                "generation": 0,
                "presence": self.owner.s13.ArtifactReferencePresence.ABSENT,
                "source_id": None,
                "content_sha256": None,
                "absence_sealed": False,
            },
        )
        return _OwnerFence(
            self.owner,
            self.transaction,
            self.owner._observation(self.transaction.transaction_id),
        )

    def __exit__(self, exc_type, exc, traceback):
        self.owner.lock.release()
        return False


class _FakeReferenceOwner:
    """用排他锁模拟远端 Memory 的 generation fence 与缺失 tombstone。"""

    def __init__(self, s13):
        self.s13 = s13
        self.lock = RLock()
        self.records = {}
        self.inspections = 0
        self.change_generation_before_seal = False

    def _observation(self, transaction_id):
        record = self.records[transaction_id]
        return self.s13.ArtifactReferenceObservation(
            transaction_id=transaction_id,
            generation=record["generation"],
            presence=record["presence"],
            source_id=record["source_id"],
            content_sha256=record["content_sha256"],
            absence_sealed=record["absence_sealed"],
        )

    def inspect_fenced(self, transaction):
        return _OwnerFenceContext(self, transaction)

    def set_unknown(self, transaction_id):
        with self.lock:
            self.records[transaction_id] = {
                "generation": 1,
                "presence": self.s13.ArtifactReferencePresence.UNKNOWN,
                "source_id": None,
                "content_sha256": None,
                "absence_sealed": False,
            }

    def publish(self, transaction_id, claim):
        with self.lock:
            current = self.records.get(transaction_id)
            if current is not None and current["absence_sealed"]:
                raise self.s13.ArtifactPublicationRejected(
                    "owner tombstone rejects late publication"
                )
            generation = 1 if current is None else current["generation"] + 1
            self.records[transaction_id] = {
                "generation": generation,
                "presence": self.s13.ArtifactReferencePresence.PUBLISHED,
                "source_id": claim.source_id,
                "content_sha256": claim.content_sha256,
                "absence_sealed": False,
            }


def test_externalized_result_separates_body_pointer_and_reference(s13, tmp_path: Path) -> None:
    raw_output = "first line\n" + "private-body\n" * 4_000
    externalizer = s13.ToolResultExternalizer(tmp_path / "session-7")

    result = externalizer.externalize(
        raw_output,
        "bash",
        summary="Search output with repeated private rows.",
    )
    artifact = result.artifact

    assert artifact.path.read_text(encoding="utf-8") == raw_output
    assert artifact.content_sha256 == hashlib.sha256(raw_output.encode()).hexdigest()
    assert artifact.source.source_id.startswith("artifact:session-7:tool_result_001.txt:")
    assert artifact.source.source_type == "artifact"
    assert artifact.source_tool == "bash"
    assert artifact.summary == "Search output with repeated private rows."
    assert artifact.source.source_id in result.context_text
    assert str(artifact.path) in result.context_text
    assert artifact.content_sha256 in result.context_text


def test_memory_reference_never_copies_artifact_body(s13, tmp_path: Path) -> None:
    secret_body = "credential-like-output-that-must-stay-in-the-artifact" * 2_000
    externalizer = s13.ToolResultExternalizer(tmp_path / "session")
    artifact = externalizer.externalize(
        secret_body,
        "search",
        summary="Credential scan output; inspect the referenced artifact if authorized.",
    ).artifact

    memory_reference = artifact.for_memory()
    payload = memory_reference.to_dict()

    assert not hasattr(memory_reference, "content")
    assert "content" not in payload
    assert secret_body not in str(payload)
    assert payload["summary"] == artifact.summary
    assert payload["artifact_path"] == str(artifact.path)
    assert payload["source"] == artifact.source.to_dict()


def test_recreated_externalizer_does_not_overwrite_referenced_evidence(
    s13, tmp_path: Path
) -> None:
    session_dir = tmp_path / "stable-session"
    first = s13.ToolResultExternalizer(session_dir).externalize(
        "first evidence",
        "search",
        summary="First result.",
    ).artifact
    replacement = s13.ToolResultExternalizer(session_dir)
    second = replacement.externalize(
        "second evidence",
        "search",
        summary="Second result.",
    ).artifact

    assert first.path.name == "tool_result_001.txt"
    assert second.path.name == "tool_result_002.txt"
    assert first.path.read_text(encoding="utf-8") == "first evidence"
    assert second.path.read_text(encoding="utf-8") == "second evidence"
    assert first.source.source_id != second.source.source_id


def test_artifact_reads_are_bounded_to_owned_directory(s13, tmp_path: Path) -> None:
    externalizer = s13.ToolResultExternalizer(tmp_path / "session")
    outside = tmp_path / "outside.txt"
    outside.write_text("not owned by this externalizer", encoding="utf-8")

    with pytest.raises(s13.ArtifactAccessError, match="outside"):
        externalizer.read_from_disk(outside)
    with pytest.raises(ValueError, match="offset"):
        externalizer.read_from_disk(
            externalizer.tool_results_dir / "missing.txt", offset=-1
        )


def test_reference_read_fails_closed_after_artifact_tampering(s13, tmp_path: Path) -> None:
    externalizer = s13.ToolResultExternalizer(tmp_path / "session")
    artifact = externalizer.externalize(
        "trusted evidence",
        "search",
        summary="Trusted search evidence.",
    ).artifact
    artifact.path.write_text("replaced evidence", encoding="utf-8")

    with pytest.raises(s13.ArtifactIntegrityError, match="digest mismatch"):
        externalizer.read_artifact(artifact)


def test_invalid_summary_fails_before_creating_artifact(s13, tmp_path: Path) -> None:
    externalizer = s13.ToolResultExternalizer(tmp_path / "session")

    with pytest.raises(ValueError, match="summary"):
        externalizer.externalize("large output", "search", summary="  ")

    assert list(externalizer.tool_results_dir.iterdir()) == []


def _set_artifact_age(path: Path, *, now: datetime, age_seconds: int) -> None:
    observed = now.timestamp() - age_seconds
    os.utime(path, (observed, observed))


def _prepare_pending_lease(
    s13,
    tmp_path: Path,
    transaction_id: str,
    *,
    expired: bool = True,
):
    now = datetime(2026, 9, 1, 9, tzinfo=timezone.utc)
    session_dir = tmp_path / f"{transaction_id}-session"
    externalizer = s13.ToolResultExternalizer(session_dir)
    artifact = externalizer.externalize(
        f"reconciliation evidence for {transaction_id}",
        "search",
        summary="A pending Memory publication needs owner reconciliation.",
    ).artifact
    _set_artifact_age(artifact.path, now=now, age_seconds=7_200)
    claim = s13.ArtifactRetentionClaim.from_memory_reference(
        artifact.for_memory(),
        retain_until=(now - timedelta(hours=1)).isoformat() if expired else None,
    )
    journal = s13.ArtifactRetentionJournal(session_dir)
    journal.prepare(
        claim,
        transaction_id=transaction_id,
        prepared_at=now - timedelta(hours=2),
    )
    return now, session_dir, externalizer, artifact, claim, journal


def test_cleanup_retains_memory_reference_and_deletes_expired_orphan(
    s13, tmp_path: Path
) -> None:
    now = datetime(2026, 8, 27, 12, tzinfo=timezone.utc)
    externalizer = s13.ToolResultExternalizer(tmp_path / "retention-session")
    referenced = externalizer.externalize(
        "durable build evidence",
        "search",
        summary="Referenced build evidence.",
    ).artifact
    orphan = externalizer.externalize(
        "temporary diagnostic output",
        "search",
        summary="Temporary diagnostic output.",
    ).artifact
    _set_artifact_age(referenced.path, now=now, age_seconds=7_200)
    _set_artifact_age(orphan.path, now=now, age_seconds=7_200)
    claim = s13.ArtifactRetentionClaim.from_memory_reference(
        referenced.for_memory(),
        reference_count=2,
    )
    policy = s13.ArtifactCleanupPolicy(
        orphan_ttl_seconds=3_600,
        dry_run=False,
    )

    plan = externalizer.plan_cleanup((claim,), policy=policy, now=now)
    planned = {decision.filename: decision for decision in plan.decisions}
    assert planned[referenced.path.name].status is (
        s13.ArtifactCleanupStatus.RETAINED_REFERENCED
    )
    assert planned[referenced.path.name].reference_count == 2
    assert planned[orphan.path.name].status is (
        s13.ArtifactCleanupStatus.PLANNED_DELETE
    )
    assert str(tmp_path) not in json.dumps(plan.to_dict(), sort_keys=True)

    report = externalizer.apply_cleanup(plan, claims=(claim,), now=now)
    assert report.counts == {
        "retained_referenced": 1,
        "deleted": 1,
    }
    assert referenced.path.read_text(encoding="utf-8") == "durable build evidence"
    assert not orphan.path.exists()


def test_cleanup_dry_run_ttl_and_deletion_limit_are_deterministic(
    s13, tmp_path: Path
) -> None:
    now = datetime(2026, 8, 27, 12, tzinfo=timezone.utc)
    externalizer = s13.ToolResultExternalizer(tmp_path / "policy-session")
    old_first = externalizer.externalize(
        "old first",
        "search",
        summary="Old first artifact.",
    ).artifact
    old_second = externalizer.externalize(
        "old second",
        "search",
        summary="Old second artifact.",
    ).artifact
    recent = externalizer.externalize(
        "recent",
        "search",
        summary="Recent artifact.",
    ).artifact
    for artifact in (old_first, old_second):
        _set_artifact_age(artifact.path, now=now, age_seconds=7_200)
    _set_artifact_age(recent.path, now=now, age_seconds=30)

    policy = s13.ArtifactCleanupPolicy(
        orphan_ttl_seconds=60,
        max_deletions=1,
        dry_run=True,
    )
    report = externalizer.cleanup_artifacts(policy=policy, now=now)
    statuses = {
        decision.filename: decision.status
        for decision in report.decisions
    }

    assert statuses[old_first.path.name] is s13.ArtifactCleanupStatus.PLANNED_DELETE
    assert statuses[old_second.path.name] is s13.ArtifactCleanupStatus.RETAINED_LIMIT
    assert statuses[recent.path.name] is s13.ArtifactCleanupStatus.RETAINED_RECENT
    assert all(artifact.path.exists() for artifact in (old_first, old_second, recent))


def test_expired_claim_can_be_collected_but_missing_active_claim_is_reported(
    s13, tmp_path: Path
) -> None:
    now = datetime(2026, 8, 27, 12, tzinfo=timezone.utc)
    externalizer = s13.ToolResultExternalizer(tmp_path / "lease-session")
    artifact = externalizer.externalize(
        "expired lease body",
        "search",
        summary="Expired lease artifact.",
    ).artifact
    _set_artifact_age(artifact.path, now=now, age_seconds=7_200)
    expired = s13.ArtifactRetentionClaim.from_memory_reference(
        artifact.for_memory(),
        retain_until=(now - timedelta(seconds=1)).isoformat(),
    )
    missing_digest = hashlib.sha256(b"missing artifact").hexdigest()
    missing = s13.ArtifactRetentionClaim(
        source_id=(
            "artifact:lease-session:tool_result_999.txt:"
            f"{missing_digest[:12]}"
        ),
        content_sha256=missing_digest,
    )

    plan = externalizer.plan_cleanup(
        (expired, missing),
        policy=s13.ArtifactCleanupPolicy(
            orphan_ttl_seconds=60,
            dry_run=False,
        ),
        now=now,
    )
    statuses = {decision.filename: decision.status for decision in plan.decisions}
    assert statuses[artifact.path.name] is s13.ArtifactCleanupStatus.PLANNED_DELETE
    assert statuses["tool_result_999.txt"] is (
        s13.ArtifactCleanupStatus.MISSING_REFERENCED
    )

    report = externalizer.apply_cleanup(plan, claims=(expired, missing), now=now)
    assert report.counts == {"deleted": 1, "missing_referenced": 1}
    assert not artifact.path.exists()


def test_cleanup_retains_artifact_when_claim_digest_disagrees(
    s13, tmp_path: Path
) -> None:
    now = datetime(2026, 8, 27, 12, tzinfo=timezone.utc)
    externalizer = s13.ToolResultExternalizer(tmp_path / "corrupt-session")
    artifact = externalizer.externalize(
        "original evidence",
        "search",
        summary="Evidence protected by a retention claim.",
    ).artifact
    claim = s13.ArtifactRetentionClaim.from_memory_reference(artifact.for_memory())
    artifact.path.write_text("tampered evidence", encoding="utf-8")
    _set_artifact_age(artifact.path, now=now, age_seconds=7_200)

    report = externalizer.cleanup_artifacts(
        (claim,),
        policy=s13.ArtifactCleanupPolicy(
            orphan_ttl_seconds=60,
            dry_run=False,
        ),
        now=now,
    )

    assert report.counts == {"retained_corrupt": 1}
    assert artifact.path.read_text(encoding="utf-8") == "tampered evidence"


def test_cleanup_rechecks_claims_added_after_planning(s13, tmp_path: Path) -> None:
    now = datetime(2026, 8, 27, 12, tzinfo=timezone.utc)
    externalizer = s13.ToolResultExternalizer(tmp_path / "late-claim-session")
    artifact = externalizer.externalize(
        "evidence claimed after planning",
        "search",
        summary="Evidence that gains an owner before apply.",
    ).artifact
    _set_artifact_age(artifact.path, now=now, age_seconds=7_200)
    policy = s13.ArtifactCleanupPolicy(orphan_ttl_seconds=60, dry_run=False)
    plan = externalizer.plan_cleanup(policy=policy, now=now)
    claim = s13.ArtifactRetentionClaim.from_memory_reference(artifact.for_memory())

    with pytest.raises(s13.ArtifactRetentionError, match="current retention claims"):
        externalizer.apply_cleanup(plan, now=now)

    report = externalizer.apply_cleanup(plan, claims=(claim,), now=now)
    assert report.counts == {"retained_referenced": 1}
    assert artifact.path.exists()


def test_cleanup_rechecks_digest_and_is_idempotent(s13, tmp_path: Path) -> None:
    now = datetime(2026, 8, 27, 12, tzinfo=timezone.utc)
    externalizer = s13.ToolResultExternalizer(tmp_path / "race-session")
    raced = externalizer.externalize(
        "original-bytes",
        "search",
        summary="Race detection artifact.",
    ).artifact
    _set_artifact_age(raced.path, now=now, age_seconds=7_200)
    policy = s13.ArtifactCleanupPolicy(orphan_ttl_seconds=60, dry_run=False)
    plan = externalizer.plan_cleanup(policy=policy, now=now)
    deletion = next(
        decision
        for decision in plan.decisions
        if decision.status is s13.ArtifactCleanupStatus.PLANNED_DELETE
    )
    raced.path.write_text("replaced-bytes", encoding="utf-8")
    snapshot = raced.path.stat()
    os.utime(
        raced.path,
        ns=(snapshot.st_atime_ns, deletion.snapshot_mtime_ns),
    )

    raced_report = externalizer.apply_cleanup(plan, claims=(), now=now)
    assert raced_report.counts == {"race_detected": 1}
    assert raced.path.exists()

    idempotent_externalizer = s13.ToolResultExternalizer(
        tmp_path / "idempotent-session"
    )
    safe = idempotent_externalizer.externalize(
        "safe orphan",
        "search",
        summary="Safe orphan artifact.",
    ).artifact
    _set_artifact_age(safe.path, now=now, age_seconds=7_200)
    safe_plan = idempotent_externalizer.plan_cleanup(policy=policy, now=now)
    first = idempotent_externalizer.apply_cleanup(safe_plan, claims=(), now=now)
    second = idempotent_externalizer.apply_cleanup(safe_plan, claims=(), now=now)
    assert first.counts["deleted"] == 1
    assert second.counts["already_missing"] == 1


def test_cleanup_rejects_cross_session_claims_and_symlink_escape(
    s13, tmp_path: Path
) -> None:
    externalizer = s13.ToolResultExternalizer(tmp_path / "owned-session")
    digest = hashlib.sha256(b"other session").hexdigest()
    cross_session = s13.ArtifactRetentionClaim(
        source_id=f"artifact:other-session:tool_result_001.txt:{digest[:12]}",
        content_sha256=digest,
    )
    with pytest.raises(s13.ArtifactRetentionError, match="different artifact session"):
        externalizer.plan_cleanup((cross_session,))
    with pytest.raises(s13.ArtifactRetentionError, match="path-free"):
        s13.parse_artifact_source_id(
            f"artifact:../outside:tool_result_001.txt:{digest[:12]}"
        )

    outside = tmp_path / "outside.txt"
    outside.write_text("outside owner", encoding="utf-8")
    link = externalizer.tool_results_dir / "tool_result_001.txt"
    try:
        link.symlink_to(outside)
    except OSError:
        pytest.skip("file symlinks are unavailable on this platform")
    plan = externalizer.plan_cleanup(
        policy=s13.ArtifactCleanupPolicy(orphan_ttl_seconds=0, dry_run=False)
    )
    assert plan.decisions[0].status is s13.ArtifactCleanupStatus.DENIED
    externalizer.apply_cleanup(plan)
    assert outside.read_text(encoding="utf-8") == "outside owner"


def test_retention_journal_survives_restart_and_drives_cleanup(
    s13, tmp_path: Path
) -> None:
    now = datetime(2026, 8, 29, 12, tzinfo=timezone.utc)
    session_dir = tmp_path / "journal-session"
    externalizer = s13.ToolResultExternalizer(session_dir)
    referenced = externalizer.externalize(
        "durable referenced evidence",
        "search",
        summary="Referenced evidence persisted before cleanup.",
    ).artifact
    orphan = externalizer.externalize(
        "old orphan",
        "search",
        summary="Unreferenced diagnostic output.",
    ).artifact
    for artifact in (referenced, orphan):
        _set_artifact_age(artifact.path, now=now, age_seconds=7_200)

    journal = s13.ArtifactRetentionJournal(session_dir)
    claim = s13.ArtifactRetentionClaim.from_memory_reference(referenced.for_memory())
    published: list[str] = []
    transaction, result = journal.publish_reference(
        claim,
        lambda: published.append(referenced.source.source_id) or "published",
        transaction_id="publish-reference-1",
        prepared_at=now - timedelta(minutes=2),
        committed_at=now - timedelta(minutes=1),
    )

    assert result == "published"
    assert published == [referenced.source.source_id]
    assert transaction.transaction_id == "publish-reference-1"
    restarted_journal = s13.ArtifactRetentionJournal(session_dir)
    recovery = restarted_journal.recover(now=now)
    assert len(recovery.claims) == 1
    assert recovery.claims[0] == claim
    assert recovery.pending_transaction_ids == ()
    assert recovery.states[0].phases == (
        s13.ArtifactLeasePhase.PREPARED,
        s13.ArtifactLeasePhase.COMMITTED,
    )
    assert str(tmp_path) not in json.dumps(recovery.to_dict(), sort_keys=True)
    retried_publisher_called = False

    def retried_publisher() -> None:
        nonlocal retried_publisher_called
        retried_publisher_called = True

    with pytest.raises(s13.ArtifactLeaseJournalError, match="reconciliation"):
        restarted_journal.publish_reference(
            claim,
            retried_publisher,
            transaction_id=transaction.transaction_id,
            prepared_at=now,
        )
    assert retried_publisher_called is False

    restarted_externalizer = s13.ToolResultExternalizer(session_dir)
    with pytest.raises(s13.ArtifactRetentionError, match="journal-aware cleanup"):
        restarted_externalizer.cleanup_artifacts((claim,), now=now)
    report = restarted_externalizer.cleanup_artifacts_from_journal(
        restarted_journal,
        policy=s13.ArtifactCleanupPolicy(
            orphan_ttl_seconds=60,
            dry_run=False,
        ),
        now=now,
    )
    assert report.counts == {"retained_referenced": 1, "deleted": 1}
    assert referenced.path.exists()
    assert not orphan.path.exists()


def test_prepared_lease_protects_reference_when_commit_was_not_written(
    s13, tmp_path: Path
) -> None:
    now = datetime(2026, 8, 29, 12, tzinfo=timezone.utc)
    session_dir = tmp_path / "prepared-session"
    externalizer = s13.ToolResultExternalizer(session_dir)
    artifact = externalizer.externalize(
        "memory publication completed before process exit",
        "search",
        summary="Reference publication crossed the crash boundary.",
    ).artifact
    _set_artifact_age(artifact.path, now=now, age_seconds=7_200)
    expired_claim = s13.ArtifactRetentionClaim.from_memory_reference(
        artifact.for_memory(),
        retain_until=(now - timedelta(hours=1)).isoformat(),
    )
    journal = s13.ArtifactRetentionJournal(session_dir)
    journal.prepare(
        expired_claim,
        transaction_id="crash-before-commit",
        prepared_at=now - timedelta(hours=2),
    )

    # The external Memory write succeeded, but the process exited before the
    # committed phase. A fresh journal must keep the uncertain intent alive.
    memory_publication = tmp_path / "published-reference.json"
    memory_publication.write_text(
        json.dumps(artifact.for_memory().to_dict(), sort_keys=True),
        encoding="utf-8",
    )
    restarted = s13.ArtifactRetentionJournal(session_dir)
    recovery = restarted.recover(now=now)
    assert recovery.pending_transaction_ids == ("crash-before-commit",)
    assert recovery.claims[0].retain_until is None

    report = externalizer.cleanup_artifacts_from_journal(
        restarted,
        policy=s13.ArtifactCleanupPolicy(
            orphan_ttl_seconds=60,
            dry_run=False,
        ),
        now=now,
    )
    assert report.counts == {"retained_referenced": 1}
    assert artifact.path.exists()


def test_expired_committed_lease_allows_orphan_collection(s13, tmp_path: Path) -> None:
    now = datetime(2026, 8, 29, 12, tzinfo=timezone.utc)
    session_dir = tmp_path / "expired-journal-session"
    externalizer = s13.ToolResultExternalizer(session_dir)
    artifact = externalizer.externalize(
        "expired committed evidence",
        "search",
        summary="The committed lease has reached its explicit deadline.",
    ).artifact
    _set_artifact_age(artifact.path, now=now, age_seconds=7_200)
    claim = s13.ArtifactRetentionClaim.from_memory_reference(
        artifact.for_memory(),
        retain_until=(now - timedelta(seconds=1)).isoformat(),
    )
    journal = s13.ArtifactRetentionJournal(session_dir)
    journal.prepare(
        claim,
        transaction_id="expired-committed-reference",
        prepared_at=now - timedelta(hours=2),
    )
    journal.commit(
        "expired-committed-reference",
        committed_at=now - timedelta(hours=1),
    )

    assert journal.recover(now=now).claims == ()
    report = externalizer.cleanup_artifacts_from_journal(
        journal,
        policy=s13.ArtifactCleanupPolicy(orphan_ttl_seconds=60, dry_run=False),
        now=now,
    )
    assert report.counts == {"deleted": 1}
    assert not artifact.path.exists()


@pytest.mark.parametrize("error_type", [TimeoutError, ConnectionError, OSError, RuntimeError])
@pytest.mark.parametrize("write_before_error", [False, True], ids=["before-write", "after-write"])
def test_uncertain_publication_preserves_pending_lease_across_restart_and_gc(
    s13, tmp_path: Path, error_type, write_before_error: bool
) -> None:
    now = datetime(2026, 8, 29, 12, tzinfo=timezone.utc)
    session_dir = tmp_path / "uncertain-publication-session"
    externalizer = s13.ToolResultExternalizer(session_dir)
    artifact = externalizer.externalize(
        "evidence whose Memory publication result is uncertain",
        "search",
        summary="Publication acknowledgement may be lost after a durable write.",
    ).artifact
    _set_artifact_age(artifact.path, now=now, age_seconds=7_200)
    claim = s13.ArtifactRetentionClaim.from_memory_reference(
        artifact.for_memory(),
        retain_until=(now - timedelta(hours=1)).isoformat(),
    )
    journal = s13.ArtifactRetentionJournal(session_dir)
    memory_path = tmp_path / "published-reference.json"
    payload = artifact.for_memory().to_dict()
    failure = error_type("publication result is unknown")
    calls = []

    def uncertain_publication() -> None:
        calls.append("publish")
        if write_before_error:
            # 模拟 Memory 已持久化、但成功回执未到达 Harness 的边界。
            with memory_path.open("w", encoding="utf-8") as handle:
                json.dump(payload, handle, sort_keys=True)
                handle.flush()
                os.fsync(handle.fileno())
        raise failure

    with pytest.raises(error_type) as raised:
        journal.publish_reference(
            claim,
            uncertain_publication,
            transaction_id="uncertain-publication",
            prepared_at=now - timedelta(hours=2),
        )
    assert raised.value is failure

    restarted_journal = s13.ArtifactRetentionJournal(session_dir)
    restarted_externalizer = s13.ToolResultExternalizer(session_dir)
    recovery = restarted_journal.recover(now=now)
    assert recovery.pending_transaction_ids == ("uncertain-publication",)
    assert recovery.states[0].phases == (s13.ArtifactLeasePhase.PREPARED,)
    assert len(recovery.claims) == 1
    assert recovery.claims[0].source_id == artifact.source.source_id
    assert recovery.claims[0].retain_until is None
    if write_before_error:
        assert json.loads(memory_path.read_text(encoding="utf-8")) == payload
    else:
        assert not memory_path.exists()

    journal_before = restarted_journal.path.read_bytes()
    with pytest.raises(s13.ArtifactLeaseJournalError, match="reconciliation"):
        restarted_journal.publish_reference(
            claim,
            uncertain_publication,
            transaction_id="uncertain-publication",
        )
    assert calls == ["publish"]
    assert restarted_journal.path.read_bytes() == journal_before

    # 即使原租约和 orphan TTL 均已到期，不确定结果仍必须保护证据。
    report = restarted_externalizer.cleanup_artifacts_from_journal(
        restarted_journal,
        policy=s13.ArtifactCleanupPolicy(orphan_ttl_seconds=60, dry_run=False),
        now=now,
    )
    assert report.counts == {"retained_referenced": 1}
    assert artifact.path.exists()


def test_explicitly_rejected_publication_aborts_lease_and_allows_gc(
    s13, tmp_path: Path
) -> None:
    now = datetime(2026, 8, 29, 12, tzinfo=timezone.utc)
    session_dir = tmp_path / "aborted-session"
    externalizer = s13.ToolResultExternalizer(session_dir)
    artifact = externalizer.externalize(
        "publication failure evidence",
        "search",
        summary="Reference publisher raises before commit.",
    ).artifact
    _set_artifact_age(artifact.path, now=now, age_seconds=7_200)
    claim = s13.ArtifactRetentionClaim.from_memory_reference(artifact.for_memory())
    journal = s13.ArtifactRetentionJournal(session_dir)
    rejection = s13.ArtifactPublicationRejected("memory adapter rejected the write")

    def reject_publication() -> None:
        raise rejection

    with pytest.raises(s13.ArtifactPublicationRejected, match="rejected the write") as raised:
        journal.publish_reference(
            claim,
            reject_publication,
            transaction_id="aborted-publication",
            prepared_at=now,
        )
    assert raised.value is rejection

    restarted_journal = s13.ArtifactRetentionJournal(session_dir)
    recovery = restarted_journal.recover(now=now)
    assert recovery.claims == ()
    assert recovery.pending_transaction_ids == ()
    assert recovery.states[0].phases == (
        s13.ArtifactLeasePhase.PREPARED,
        s13.ArtifactLeasePhase.ABORTED,
    )
    report = s13.ToolResultExternalizer(session_dir).cleanup_artifacts_from_journal(
        restarted_journal,
        policy=s13.ArtifactCleanupPolicy(orphan_ttl_seconds=60, dry_run=False),
        now=now,
    )
    assert report.counts == {"deleted": 1}
    assert not artifact.path.exists()


def test_reconciliation_commits_exact_published_reference_after_restart_and_is_idempotent(
    s13, tmp_path: Path
) -> None:
    now, session_dir, externalizer, artifact, claim, _journal = _prepare_pending_lease(
        s13,
        tmp_path,
        "published-owner-reference",
        expired=False,
    )
    owner = _FakeReferenceOwner(s13)
    owner.publish("published-owner-reference", claim)

    restarted = s13.ArtifactRetentionJournal(session_dir)
    reports = restarted.reconcile_pending(
        owner,
        resolved_at=now,
    )
    assert len(reports) == 1
    report = reports[0]
    assert report.to_dict() == {
        "transaction_id": "published-owner-reference",
        "status": "committed",
        "reason": "owner_confirmed_reference",
        "observed_generation": 1,
    }
    recovery = s13.ArtifactRetentionJournal(session_dir).recover(now=now)
    assert recovery.pending_transaction_ids == ()
    assert recovery.states[0].current_phase is s13.ArtifactLeasePhase.COMMITTED

    journal_before = restarted.path.read_bytes()
    repeated = restarted.reconcile_reference("published-owner-reference", owner)
    assert repeated.status is s13.ArtifactReconciliationStatus.ALREADY_COMMITTED
    assert owner.inspections == 1
    assert restarted.path.read_bytes() == journal_before

    cleanup = externalizer.cleanup_artifacts_from_journal(
        restarted,
        policy=s13.ArtifactCleanupPolicy(orphan_ttl_seconds=60, dry_run=False),
        now=now,
    )
    assert cleanup.counts == {"retained_referenced": 1}
    assert artifact.path.exists()
    assert str(tmp_path) not in json.dumps(report.to_dict(), sort_keys=True)


def test_reconciliation_seals_absence_before_abort_and_rejects_late_publication(
    s13, tmp_path: Path
) -> None:
    now, session_dir, externalizer, artifact, claim, journal = _prepare_pending_lease(
        s13,
        tmp_path,
        "absent-owner-reference",
    )
    owner = _FakeReferenceOwner(s13)

    report = journal.reconcile_reference(
        "absent-owner-reference",
        owner,
        resolved_at=now,
    )
    assert report.status is s13.ArtifactReconciliationStatus.ABORTED
    assert report.observed_generation == 1
    assert owner.records["absent-owner-reference"]["absence_sealed"] is True
    recovery = s13.ArtifactRetentionJournal(session_dir).recover(now=now)
    assert recovery.pending_transaction_ids == ()
    assert recovery.claims == ()
    assert recovery.states[0].current_phase is s13.ArtifactLeasePhase.ABORTED

    with pytest.raises(s13.ArtifactPublicationRejected, match="late publication"):
        owner.publish("absent-owner-reference", claim)

    cleanup = externalizer.cleanup_artifacts_from_journal(
        journal,
        policy=s13.ArtifactCleanupPolicy(orphan_ttl_seconds=60, dry_run=False),
        now=now,
    )
    assert cleanup.counts == {"deleted": 1}
    assert not artifact.path.exists()


@pytest.mark.parametrize(
    ("owner_setup", "expected_status", "expected_reason"),
    [
        ("unknown", "pending_unknown", "owner_result_unknown"),
        ("mismatch", "pending_conflict", "owner_reference_mismatch"),
        ("stale", "pending_stale", "owner_generation_changed"),
    ],
)
def test_untrusted_or_stale_owner_result_remains_prepared_and_protects_gc(
    s13,
    tmp_path: Path,
    owner_setup: str,
    expected_status: str,
    expected_reason: str,
) -> None:
    now, session_dir, externalizer, artifact, claim, journal = _prepare_pending_lease(
        s13,
        tmp_path,
        f"{owner_setup}-owner-reference",
    )
    transaction_id = f"{owner_setup}-owner-reference"
    owner = _FakeReferenceOwner(s13)
    if owner_setup == "unknown":
        owner.set_unknown(transaction_id)
    elif owner_setup == "mismatch":
        owner.publish(transaction_id, claim)
        owner.records[transaction_id]["content_sha256"] = "f" * 64
    else:
        owner.change_generation_before_seal = True

    report = journal.reconcile_reference(transaction_id, owner, resolved_at=now)
    assert report.status.value == expected_status
    assert report.reason == expected_reason
    recovery = s13.ArtifactRetentionJournal(session_dir).recover(now=now)
    assert recovery.pending_transaction_ids == (transaction_id,)
    assert recovery.states[0].phases == (s13.ArtifactLeasePhase.PREPARED,)
    assert recovery.claims[0].retain_until is None

    cleanup = externalizer.cleanup_artifacts_from_journal(
        journal,
        policy=s13.ArtifactCleanupPolicy(orphan_ttl_seconds=60, dry_run=False),
        now=now,
    )
    assert cleanup.counts == {"retained_referenced": 1}
    assert artifact.path.exists()


def test_crash_after_owner_seal_recovers_without_reopening_publication_window(
    s13, tmp_path: Path, monkeypatch
) -> None:
    now, session_dir, _externalizer, _artifact, claim, journal = _prepare_pending_lease(
        s13,
        tmp_path,
        "seal-crash-reference",
    )
    owner = _FakeReferenceOwner(s13)

    def crash_after_seal(name: str) -> None:
        if name == "after_owner_absence_sealed":
            raise RuntimeError("simulated exit after owner tombstone fsync")

    monkeypatch.setattr(journal, "_checkpoint", crash_after_seal)
    with pytest.raises(RuntimeError, match="owner tombstone fsync"):
        journal.reconcile_reference("seal-crash-reference", owner, resolved_at=now)

    assert owner.records["seal-crash-reference"]["absence_sealed"] is True
    restarted = s13.ArtifactRetentionJournal(session_dir)
    assert restarted.recover(now=now).pending_transaction_ids == (
        "seal-crash-reference",
    )
    with pytest.raises(s13.ArtifactPublicationRejected):
        owner.publish("seal-crash-reference", claim)

    report = restarted.reconcile_reference(
        "seal-crash-reference",
        owner,
        resolved_at=now,
    )
    assert report.status is s13.ArtifactReconciliationStatus.ABORTED
    assert report.observed_generation == 1
    assert restarted.recover(now=now).pending_transaction_ids == ()


def test_concurrent_reconciliation_appends_one_terminal_transition(
    s13, tmp_path: Path
) -> None:
    now, session_dir, _externalizer, _artifact, claim, journal = _prepare_pending_lease(
        s13,
        tmp_path,
        "concurrent-owner-reference",
    )
    owner = _FakeReferenceOwner(s13)
    owner.publish("concurrent-owner-reference", claim)
    barrier = Barrier(2)

    def reconcile_once():
        barrier.wait()
        return journal.reconcile_reference(
            "concurrent-owner-reference",
            owner,
            resolved_at=now,
        )

    with ThreadPoolExecutor(max_workers=2) as executor:
        reports = list(executor.map(lambda _index: reconcile_once(), range(2)))

    assert {report.status for report in reports} == {
        s13.ArtifactReconciliationStatus.COMMITTED,
        s13.ArtifactReconciliationStatus.ALREADY_COMMITTED,
    }
    records = [
        json.loads(line)
        for line in journal.path.read_text(encoding="utf-8").splitlines()
    ]
    assert [record["phase"] for record in records] == ["prepared", "committed"]
    assert s13.ArtifactRetentionJournal(session_dir).recover(
        now=now
    ).pending_transaction_ids == ()


def test_post_fsync_commit_crash_recovers_and_retry_is_idempotent(
    s13, tmp_path: Path, monkeypatch
) -> None:
    now = datetime(2026, 8, 29, 12, tzinfo=timezone.utc)
    session_dir = tmp_path / "commit-crash-session"
    externalizer = s13.ToolResultExternalizer(session_dir)
    artifact = externalizer.externalize(
        "commit crash evidence",
        "search",
        summary="Committed phase reaches disk before process exit.",
    ).artifact
    claim = s13.ArtifactRetentionClaim.from_memory_reference(artifact.for_memory())
    journal = s13.ArtifactRetentionJournal(session_dir)
    transaction = journal.prepare(
        claim,
        transaction_id="commit-crash",
        prepared_at=now - timedelta(minutes=1),
    )

    def crash_after_fsync(name: str) -> None:
        if name == "after_committed":
            raise RuntimeError("simulated process exit after commit fsync")

    monkeypatch.setattr(journal, "_checkpoint", crash_after_fsync)
    with pytest.raises(RuntimeError, match="after commit fsync"):
        journal.commit(transaction.transaction_id, committed_at=now)

    restarted = s13.ArtifactRetentionJournal(session_dir)
    recovery = restarted.recover(now=now)
    assert recovery.states[0].current_phase is s13.ArtifactLeasePhase.COMMITTED
    journal_before = restarted.path.read_bytes()
    restarted.commit(transaction.transaction_id, committed_at=now)
    assert restarted.path.read_bytes() == journal_before


def test_journal_discards_only_partial_tail_and_detects_tampering(
    s13, tmp_path: Path
) -> None:
    now = datetime(2026, 8, 29, 12, tzinfo=timezone.utc)
    session_dir = tmp_path / "journal-integrity-session"
    externalizer = s13.ToolResultExternalizer(session_dir)
    artifact = externalizer.externalize(
        "journal integrity evidence",
        "search",
        summary="Journal integrity test artifact.",
    ).artifact
    claim = s13.ArtifactRetentionClaim.from_memory_reference(artifact.for_memory())
    journal = s13.ArtifactRetentionJournal(session_dir)
    transaction = journal.prepare(
        claim,
        transaction_id="integrity-transaction",
        prepared_at=now - timedelta(minutes=2),
    )
    journal.commit(transaction.transaction_id, committed_at=now - timedelta(minutes=1))
    with journal.path.open("ab") as handle:
        handle.write(b'{"partial_crash_record":"\xe2\x82')

    assert len(s13.ArtifactRetentionJournal(session_dir).recover(now=now).claims) == 1
    restarted = s13.ArtifactRetentionJournal(session_dir)
    restarted.release(transaction.transaction_id, released_at=now)
    records = [
        json.loads(line)
        for line in restarted.path.read_text(encoding="utf-8").splitlines()
    ]
    assert [record["sequence"] for record in records] == [1, 2, 3]

    valid_journal = restarted.path.read_text(encoding="utf-8")
    restarted.path.write_text(valid_journal + "{complete bad record}\n", encoding="utf-8")
    with pytest.raises(s13.ArtifactLeaseJournalError, match="invalid.*JSON"):
        s13.ArtifactRetentionJournal(session_dir).recover(now=now)
    restarted.path.write_text(valid_journal, encoding="utf-8")

    records[0]["intent"]["claim"]["reference_count"] = 99
    restarted.path.write_text(
        "\n".join(json.dumps(record, sort_keys=True) for record in records) + "\n",
        encoding="utf-8",
    )
    with pytest.raises(s13.ArtifactLeaseJournalError, match="hash mismatch"):
        s13.ArtifactRetentionJournal(session_dir).recover(now=now)


def test_journal_aggregates_and_releases_multiple_references(
    s13, tmp_path: Path
) -> None:
    now = datetime(2026, 8, 29, 12, tzinfo=timezone.utc)
    session_dir = tmp_path / "aggregate-session"
    externalizer = s13.ToolResultExternalizer(session_dir)
    artifact = externalizer.externalize(
        "shared evidence",
        "search",
        summary="Two Memory records reference one Artifact.",
    ).artifact
    claim = s13.ArtifactRetentionClaim.from_memory_reference(artifact.for_memory())
    journal = s13.ArtifactRetentionJournal(session_dir)
    for transaction_id in ("reference-a", "reference-b"):
        journal.prepare(claim, transaction_id=transaction_id, prepared_at=now)
        journal.commit(transaction_id, committed_at=now)

    assert journal.recover(now=now).claims[0].reference_count == 2

    def fail_removal() -> None:
        raise RuntimeError("reference removal failed")

    with pytest.raises(RuntimeError, match="reference removal failed"):
        journal.remove_reference(
            "reference-a",
            fail_removal,
            released_at=now,
        )
    assert journal.recover(now=now).claims[0].reference_count == 2
    assert journal.remove_reference(
        "reference-a",
        lambda: "removed",
        released_at=now,
    ) == "removed"
    assert journal.recover(now=now).claims[0].reference_count == 1
    journal.release("reference-b", released_at=now)
    assert journal.recover(now=now).claims == ()


def test_concurrent_journal_writers_preserve_sequence_and_hash_chain(
    s13, tmp_path: Path
) -> None:
    now = datetime(2026, 8, 29, 12, tzinfo=timezone.utc)
    session_dir = tmp_path / "concurrent-journal-session"
    artifact = s13.ToolResultExternalizer(session_dir).externalize(
        "shared concurrent evidence",
        "search",
        summary="Concurrent publishers share one immutable Artifact.",
    ).artifact
    claim = s13.ArtifactRetentionClaim.from_memory_reference(artifact.for_memory())
    writer_count = 6
    barrier = Barrier(writer_count)

    def prepare(index: int) -> None:
        writer = s13.ArtifactRetentionJournal(session_dir)
        barrier.wait()
        writer.prepare(
            claim,
            transaction_id=f"concurrent-reference-{index}",
            prepared_at=now,
        )

    with ThreadPoolExecutor(max_workers=writer_count) as executor:
        list(executor.map(prepare, range(writer_count)))

    journal = s13.ArtifactRetentionJournal(session_dir)
    recovery = journal.recover(now=now)
    assert recovery.claims[0].reference_count == writer_count
    assert len(recovery.pending_transaction_ids) == writer_count
    records = [
        json.loads(line)
        for line in journal.path.read_text(encoding="utf-8").splitlines()
    ]
    assert [record["sequence"] for record in records] == list(
        range(1, writer_count + 1)
    )


def test_journal_apply_rechecks_reference_added_after_plan(
    s13, tmp_path: Path
) -> None:
    now = datetime(2026, 8, 29, 12, tzinfo=timezone.utc)
    session_dir = tmp_path / "journal-late-claim-session"
    externalizer = s13.ToolResultExternalizer(session_dir)
    artifact = externalizer.externalize(
        "late durable reference",
        "search",
        summary="Reference is published after cleanup planning.",
    ).artifact
    _set_artifact_age(artifact.path, now=now, age_seconds=7_200)
    policy = s13.ArtifactCleanupPolicy(orphan_ttl_seconds=60, dry_run=False)
    journal = s13.ArtifactRetentionJournal(session_dir)
    plan = externalizer.plan_cleanup_from_journal(journal, policy=policy, now=now)

    claim = s13.ArtifactRetentionClaim.from_memory_reference(artifact.for_memory())
    journal.publish_reference(
        claim,
        lambda: None,
        transaction_id="late-reference",
        prepared_at=now,
        committed_at=now,
    )
    report = externalizer.apply_cleanup_from_journal(plan, journal, now=now)
    assert report.counts == {"retained_referenced": 1}
    assert artifact.path.exists()


def test_reference_publication_is_rejected_when_cleanup_wins_the_lock(
    s13, tmp_path: Path
) -> None:
    now = datetime(2026, 8, 29, 12, tzinfo=timezone.utc)
    session_dir = tmp_path / "cleanup-first-session"
    externalizer = s13.ToolResultExternalizer(session_dir)
    artifact = externalizer.externalize(
        "unowned evidence",
        "search",
        summary="Cleanup removes this artifact before publication begins.",
    ).artifact
    _set_artifact_age(artifact.path, now=now, age_seconds=7_200)
    claim = s13.ArtifactRetentionClaim.from_memory_reference(artifact.for_memory())
    journal = s13.ArtifactRetentionJournal(session_dir)
    report = externalizer.cleanup_artifacts_from_journal(
        journal,
        policy=s13.ArtifactCleanupPolicy(orphan_ttl_seconds=60, dry_run=False),
        now=now,
    )
    assert report.counts == {"deleted": 1}

    publisher_called = False

    def publisher() -> None:
        nonlocal publisher_called
        publisher_called = True

    with pytest.raises(s13.ArtifactRetentionError, match="missing artifact"):
        journal.publish_reference(
            claim,
            publisher,
            transaction_id="too-late-reference",
            prepared_at=now,
        )
    assert publisher_called is False
    assert journal.recover(now=now).states == ()


def test_cleanup_rejects_journal_owned_by_another_session(s13, tmp_path: Path) -> None:
    externalizer = s13.ToolResultExternalizer(tmp_path / "cleanup-owner")
    other_journal = s13.ArtifactRetentionJournal(tmp_path / "other-owner")
    with pytest.raises(s13.ArtifactRetentionError, match="different artifact session"):
        externalizer.plan_cleanup_from_journal(other_journal)


def test_retention_journal_rejects_symlink_escape(s13, tmp_path: Path) -> None:
    session_dir = tmp_path / "journal-symlink-session"
    artifact = s13.ToolResultExternalizer(session_dir).externalize(
        "owned artifact",
        "search",
        summary="The lease journal must remain in its session root.",
    ).artifact
    claim = s13.ArtifactRetentionClaim.from_memory_reference(artifact.for_memory())
    outside = tmp_path / "outside-journal.jsonl"
    outside.write_text("outside owner\n", encoding="utf-8")
    journal = s13.ArtifactRetentionJournal(session_dir)
    try:
        journal.path.symlink_to(outside)
    except OSError:
        pytest.skip("file symlinks are unavailable on this platform")

    with pytest.raises(s13.ArtifactLeaseJournalError, match="owned regular file"):
        journal.prepare(
            claim,
            transaction_id="symlink-escape",
        )
    assert outside.read_text(encoding="utf-8") == "outside owner\n"
