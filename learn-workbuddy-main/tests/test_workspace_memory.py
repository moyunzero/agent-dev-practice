"""Offline contract tests for s10's workspace log-and-distill memory."""

from __future__ import annotations

import importlib.util
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def s10():
    stub_dir = ROOT / "tests" / "stubs"
    sys.path.insert(0, str(stub_dir))
    saved_anthropic = sys.modules.pop("anthropic", None)
    old_model = os.environ.get("MODEL_ID")
    os.environ["MODEL_ID"] = "offline-test-model"
    module_name = "s10_workspace_memory_test_module"
    try:
        spec = importlib.util.spec_from_file_location(
            module_name, ROOT / "s10_workspace_memory" / "code.py"
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


def _old(day: int) -> datetime:
    return datetime(2026, 1, day, 12, tzinfo=timezone.utc)


def _append_pair(
    memory,
    content: str,
    *,
    memory_key: str,
    first_day: int,
    prefix: str,
    importance: int = 4,
) -> None:
    for offset in range(2):
        memory.append_daily_log(
            content,
            kind="decision",
            importance=importance,
            memory_key=memory_key,
            recorded_at=_old(first_day + offset),
            fact_id=f"{prefix}{offset + 1}",
        )


def _database_conflict(s10, root: Path):
    memory = s10.WorkspaceMemory(root)
    memory.append_daily_log(
        "Use SQLite.",
        kind="decision",
        importance=5,
        memory_key="storage.database",
        recorded_at=_old(1),
        fact_id="database-current",
    )
    as_of = datetime(2026, 3, 1, tzinfo=timezone.utc)
    memory.distill(as_of=as_of)
    for content, prefix in (("Use Postgres.", "pg"), ("Use MySQL.", "mysql")):
        _append_pair(
            memory,
            content,
            memory_key="storage.database",
            first_day=10,
            prefix=prefix,
        )
    report = memory.distill(as_of=as_of)
    case = memory.list_conflicts()[0]
    return memory, as_of, report, case


def test_workspace_scope_isolated_and_log_is_append_only(s10, tmp_path: Path) -> None:
    first = s10.WorkspaceMemory(tmp_path / "project-a")
    second = s10.WorkspaceMemory(tmp_path / "project-b")

    first.append_daily_log("Use SQLite WAL.", kind="decision", fact_id="a1")
    first.append_daily_log("Keep paths relative.", kind="convention", fact_id="a2")
    second.append_daily_log("Use Postgres.", kind="decision", fact_id="b1")

    assert first.workspace_id != second.workspace_id
    assert [fact.fact_id for fact in first.read_daily_facts()] == ["a1", "a2"]
    assert [fact.fact_id for fact in second.read_daily_facts()] == ["b1"]
    assert first.today_log_path().read_text(encoding="utf-8").count("\n") == 2
    assert ".learn_workbuddy/memory/daily" in first.today_log_path().as_posix()


def test_distill_gate_is_explainable_idempotent_and_keeps_evidence(
    s10, tmp_path: Path
) -> None:
    memory = s10.WorkspaceMemory(tmp_path / "project")
    memory.append_daily_log(
        "Use SQLite WAL.", kind="decision", importance=5, recorded_at=_old(1), fact_id="d1"
    )
    memory.append_daily_log(
        "Keep paths relative.", kind="convention", importance=2, recorded_at=_old(2), fact_id="c1"
    )
    memory.append_daily_log(
        " keep   paths relative. ", kind="convention", importance=2, recorded_at=_old(3), fact_id="c2"
    )
    memory.append_daily_log(
        "One-off build passed.", kind="outcome", importance=5, recorded_at=_old(4), fact_id="o1"
    )
    memory.append_daily_log(
        "Possible rare pitfall.", kind="pitfall", importance=2, recorded_at=_old(5), fact_id="p1"
    )
    report = memory.distill(
        policy=s10.DistillPolicy(minimum_age_days=30),
        as_of=datetime(2026, 3, 1, tzinfo=timezone.utc),
    )

    assert report == s10.DistillReport(
        scanned=5, eligible=3, created=2, updated=0, skipped=2
    )
    assert len(memory.list_logs()) == 5  # distillation never deletes evidence
    rendered = memory.read_memory_md()
    assert "Use SQLite WAL." in rendered
    assert "Keep paths relative." in rendered
    assert "One-off build passed." not in rendered
    assert memory.distill(
        policy=s10.DistillPolicy(minimum_age_days=30),
        as_of=datetime(2026, 3, 1, tzinfo=timezone.utc),
    ).created == 0
    entries = json.loads(memory.curated_file.read_text(encoding="utf-8"))["entries"]
    assert sorted(entry["occurrences"] for entry in entries) == [1, 2]


def test_atomic_replace_preserves_previous_curated_file_on_failure(
    s10, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    memory = s10.WorkspaceMemory(tmp_path / "project")
    memory.append_daily_log(
        "First decision.", kind="decision", importance=5, recorded_at=_old(1), fact_id="d1"
    )
    as_of = datetime(2026, 3, 1, tzinfo=timezone.utc)
    memory.distill(as_of=as_of)
    previous = memory.curated_file.read_text(encoding="utf-8")
    memory.append_daily_log(
        "Second decision.", kind="decision", importance=5, recorded_at=_old(2), fact_id="d2"
    )
    real_replace = s10.os.replace

    def fail_curated_replace(source, destination) -> None:
        if Path(destination) == memory.curated_file:
            raise OSError("simulated crash before rename")
        real_replace(source, destination)

    monkeypatch.setattr(s10.os, "replace", fail_curated_replace)
    with pytest.raises(OSError, match="simulated crash"):
        memory.distill(as_of=as_of)
    assert memory.curated_file.read_text(encoding="utf-8") == previous
    assert list(memory.memory_dir.glob(".*.tmp")) == []


def test_directory_fsync_falls_back_without_opening_directory(
    s10, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def fail_if_opened(*_args, **_kwargs) -> None:
        raise AssertionError("directory fsync fallback must not call os.open")

    monkeypatch.setattr(s10, "_DIRECTORY_FSYNC_SUPPORTED", False)
    monkeypatch.setattr(s10.os, "open", fail_if_opened)

    s10._fsync_directory(tmp_path)


def test_new_process_view_recovers_facts_and_curated_context(s10, tmp_path: Path) -> None:
    root = tmp_path / "project"
    writer = s10.WorkspaceMemory(root)
    writer.append_daily_log(
        "Never store secrets in memory.",
        kind="convention",
        importance=5,
        recorded_at=_old(1),
        fact_id="safe1",
    )
    writer.distill(as_of=datetime(2026, 3, 1, tzinfo=timezone.utc))

    recovered = s10.WorkspaceMemory(root)
    assert recovered.read_all_facts()[0].fact_id == "safe1"
    assert "Never store secrets in memory." in recovered.get_context_for_agent()

    # curated.json is canonical: a stale human-facing projection is repaired
    # before it can be injected into a replacement runtime.
    recovered.memory_file.write_text("stale projection", encoding="utf-8")
    assert "Never store secrets in memory." in recovered.read_memory_md()
    assert "stale projection" not in recovered.memory_file.read_text(encoding="utf-8")
    assert "# Recent Workspace Facts" not in recovered.get_context_for_agent(recent_limit=0)


def test_reader_ignores_only_an_unterminated_corrupt_tail(s10, tmp_path: Path) -> None:
    memory = s10.WorkspaceMemory(tmp_path / "project")
    memory.append_daily_log("Valid fact.", fact_id="valid")
    with memory.today_log_path().open("ab") as handle:
        handle.write(b'{"fact_id":')
    assert [fact.fact_id for fact in memory.read_daily_facts()] == ["valid"]


def test_keyed_fact_validates_conflict_domain_and_writes_current_schema(
    s10, tmp_path: Path
) -> None:
    memory = s10.WorkspaceMemory(tmp_path / "project")

    fact = memory.append_daily_log(
        "Use Python 3.12.",
        kind="decision",
        importance=5,
        memory_key=" Runtime.Python-Version ",
        recorded_at=_old(1),
        fact_id="runtime1",
    )

    assert fact.memory_key == "runtime.python-version"
    assert fact.schema_version == 2
    stored = json.loads(
        memory.daily_log_path(_old(1).date()).read_text(encoding="utf-8")
    )
    assert stored["memory_key"] == "runtime.python-version"
    with pytest.raises(ValueError, match="memory_key"):
        memory.append_daily_log(
            "Invalid key.",
            kind="decision",
            memory_key="Runtime Python Version",
        )

    write_memory = next(
        tool
        for tool in s10.MemoryAwareAgent._build_tools()
        if tool["name"] == "write_memory"
    )
    key_schema = write_memory["input_schema"]["properties"]["memory_key"]
    assert key_schema["pattern"] == s10.MEMORY_KEY_PATTERN.pattern
    assert "memory_key" not in write_memory["input_schema"]["required"]


def test_confirmed_new_value_supersedes_without_deleting_old_evidence(
    s10, tmp_path: Path
) -> None:
    memory = s10.WorkspaceMemory(tmp_path / "project")
    memory.append_daily_log(
        "Use Python 3.11.",
        kind="decision",
        importance=5,
        memory_key="runtime.python-version",
        recorded_at=_old(1),
        fact_id="python-old",
    )
    as_of = datetime(2026, 3, 1, tzinfo=timezone.utc)
    first = memory.distill(as_of=as_of)
    assert first.created == 1

    memory.append_daily_log(
        "Use Python 3.12.",
        kind="decision",
        importance=5,
        memory_key="runtime.python-version",
        recorded_at=_old(10),
        fact_id="python-new-1",
    )
    unconfirmed = memory.distill(as_of=as_of)
    assert unconfirmed.superseded == 0
    assert "Use Python 3.11." in memory.read_memory_md()
    assert "Use Python 3.12." not in memory.get_context_for_agent()

    memory.append_daily_log(
        "Use Python 3.12.",
        kind="decision",
        importance=4,
        memory_key="runtime.python-version",
        recorded_at=_old(11),
        fact_id="python-new-2",
    )
    confirmed = memory.distill(as_of=as_of)
    assert confirmed.created == 1
    assert confirmed.superseded == 1
    assert confirmed.conflicts == 0

    payload = json.loads(memory.curated_file.read_text(encoding="utf-8"))
    entries = sorted(payload["entries"], key=lambda entry: entry["revision"])
    old, active = entries
    assert payload["schema_version"] == 2
    assert old["status"] == "superseded"
    assert old["superseded_by"] == active["key"]
    assert active["status"] == "active"
    assert active["revision"] == 2
    assert active["supersedes"] == old["key"]
    assert active["evidence_ids"] == ["python-new-1", "python-new-2"]
    assert len(memory.read_all_facts()) == 3

    rendered = memory.read_memory_md()
    assert "Use Python 3.12." in rendered
    assert "Use Python 3.11." not in rendered
    assert "Use Python 3.11." not in memory.get_context_for_agent()


def test_stale_evidence_cannot_roll_back_active_revision(s10, tmp_path: Path) -> None:
    memory = s10.WorkspaceMemory(tmp_path / "project")
    memory.append_daily_log(
        "Use Python 3.11.",
        kind="decision",
        importance=5,
        memory_key="runtime.python-version",
        recorded_at=_old(1),
        fact_id="old-original",
    )
    as_of = datetime(2026, 3, 1, tzinfo=timezone.utc)
    memory.distill(as_of=as_of)
    _append_pair(
        memory,
        "Use Python 3.12.",
        memory_key="runtime.python-version",
        first_day=10,
        prefix="new",
    )
    memory.distill(as_of=as_of)

    _append_pair(
        memory,
        "Use Python 3.11.",
        memory_key="runtime.python-version",
        first_day=5,
        prefix="late-old",
        importance=5,
    )
    report = memory.distill(as_of=as_of)

    assert report.superseded == 0
    assert report.stale == 2
    entries = memory._load_curated()
    assert len(entries) == 2
    assert next(entry for entry in entries if entry.status == "active").content == (
        "Use Python 3.12."
    )


def test_equal_strength_conflict_fails_closed_and_is_observable(
    s10, tmp_path: Path
) -> None:
    memory, as_of, report, case = _database_conflict(
        s10, tmp_path / "project"
    )

    assert report.conflicts == 1
    assert report.queued_conflicts == 1
    assert report.conflict_case_ids == (case.conflict_id,)
    assert report.superseded == 0
    assert report.created == 0
    assert "Use SQLite." in memory.read_memory_md()
    assert "Use Postgres." not in memory.get_context_for_agent()
    assert "Use MySQL." not in memory.get_context_for_agent()
    assert len(memory._load_curated()) == 1
    assert case.status == "open"
    assert case.revision == 1
    assert case.active_entry_key == memory._load_curated()[0].key
    assert [candidate.candidate_id for candidate in case.candidates] == sorted(
        candidate.candidate_id for candidate in case.candidates
    )
    assert {candidate.content for candidate in case.candidates} == {
        "Use SQLite.",
        "Use Postgres.",
        "Use MySQL.",
    }
    assert sum(candidate.incumbent for candidate in case.candidates) == 1
    assert set(case.observed_fact_ids) == {
        "database-current",
        "pg1",
        "pg2",
        "mysql1",
        "mysql2",
    }

    before = memory.conflict_file.read_text(encoding="utf-8")
    rerun = memory.distill(as_of=as_of)
    assert rerun.conflicts == 1
    assert rerun.queued_conflicts == 0
    assert rerun.conflict_case_ids == (case.conflict_id,)
    assert memory.conflict_file.read_text(encoding="utf-8") == before


def test_human_resolution_creates_revision_and_append_only_audit(
    s10, tmp_path: Path
) -> None:
    root = tmp_path / "project"
    memory, as_of, _, case = _database_conflict(s10, root)
    selected = next(
        candidate for candidate in case.candidates if candidate.content == "Use Postgres."
    )

    event = memory.resolve_conflict(
        case.conflict_id,
        selected.candidate_id,
        expected_revision=case.revision,
        actor="KEDADA",
        rationale="The deployment target requires PostgreSQL features.",
        event_id="review:storage-database:1",
        resolved_at=as_of,
    )

    assert event.actor == "KEDADA"
    assert event.evidence_ids == ("pg1", "pg2")
    assert len(memory.list_adjudications()) == 1
    assert memory.adjudication_file.read_text(encoding="utf-8").count("\n") == 1
    resolved = memory.list_conflicts(status=s10.ConflictStatus.RESOLVED)[0]
    assert resolved.selected_candidate_id == selected.candidate_id
    assert resolved.resulting_active_entry_key == event.resulting_active_entry_key

    entries = sorted(memory._load_curated(), key=lambda item: item.revision)
    assert len(entries) == 2
    assert entries[0].status == "superseded"
    assert entries[1].status == "active"
    assert entries[1].content == "Use Postgres."
    assert entries[1].supersedes == entries[0].key
    assert entries[0].superseded_by == entries[1].key
    assert "Use Postgres." in memory.get_context_for_agent()
    assert "Use MySQL." not in memory.get_context_for_agent()
    assert len(memory.read_all_facts()) == 5

    # Replaying distillation cannot promote a rejected candidate from the same
    # reviewed evidence snapshot.
    rerun = memory.distill(as_of=as_of)
    assert rerun.created == 0
    assert rerun.superseded == 0
    assert next(
        entry for entry in memory._load_curated() if entry.status == "active"
    ).content == "Use Postgres."

    recovered = s10.WorkspaceMemory(root)
    assert recovered.list_conflicts() == []
    assert recovered.list_conflicts(status=None)[0].status == "resolved"
    assert recovered.list_adjudications() == [event]


@pytest.mark.parametrize(
    "fault_point",
    [
        "after_prepared",
        "after_curated_write",
        "after_curated_applied",
        "after_conflict_write",
        "after_conflict_closed",
        "after_audit_write",
        "after_audit_appended",
        "after_committed",
    ],
)
def test_resolution_transaction_recovers_every_durable_write_boundary(
    s10,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    fault_point: str,
) -> None:
    root = tmp_path / fault_point
    memory, as_of, _, case = _database_conflict(s10, root)
    selected = next(
        candidate for candidate in case.candidates if candidate.content == "Use Postgres."
    )

    def crash_at(name: str) -> None:
        if name == fault_point:
            raise OSError(f"simulated process exit at {name}")

    monkeypatch.setattr(memory, "_resolution_checkpoint", crash_at)
    with pytest.raises(OSError, match=fault_point):
        memory.resolve_conflict(
            case.conflict_id,
            selected.candidate_id,
            expected_revision=case.revision,
            actor="KEDADA",
            rationale="PostgreSQL is required by the reviewed deployment target.",
            event_id=f"recovery-{fault_point}",
            resolved_at=as_of,
        )

    recovered = s10.WorkspaceMemory(root)
    events = recovered.list_adjudications()
    assert len(events) == 1
    assert events[0].event_id == f"recovery-{fault_point}"
    assert events[0].actor == "KEDADA"
    assert recovered.list_conflicts() == []
    assert recovered.list_conflicts(status=None)[0].status == "resolved"
    entries = sorted(recovered._load_curated(), key=lambda item: item.revision)
    assert [entry.status for entry in entries] == ["superseded", "active"]
    assert entries[-1].content == "Use Postgres."
    assert "Use Postgres." in recovered.read_memory_md()

    journal_before = recovered.resolution_transaction_file.read_text(
        encoding="utf-8"
    )
    records = [json.loads(line) for line in journal_before.splitlines()]
    assert [record["phase"] for record in records] == [
        "prepared",
        "curated_applied",
        "conflict_closed",
        "audit_appended",
        "committed",
    ]
    assert len({record["transaction_id"] for record in records}) == 1
    assert len({record["intent_sha256"] for record in records}) == 1

    restarted_again = s10.WorkspaceMemory(root)
    assert restarted_again.list_adjudications() == events
    assert (
        restarted_again.resolution_transaction_file.read_text(encoding="utf-8")
        == journal_before
    )


def test_resolution_recovery_repairs_projection_after_curated_replace(
    s10, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "project"
    memory, as_of, _, case = _database_conflict(s10, root)
    selected = next(
        candidate for candidate in case.candidates if candidate.content == "Use Postgres."
    )
    old_projection = memory.memory_file.read_text(encoding="utf-8")
    real_atomic_write = memory._atomic_write_text

    def crash_after_curated_replace(path: Path, content: str) -> None:
        real_atomic_write(path, content)
        if path == memory.curated_file:
            raise OSError("simulated exit after curated replace")

    monkeypatch.setattr(memory, "_atomic_write_text", crash_after_curated_replace)
    with pytest.raises(OSError, match="after curated replace"):
        memory.resolve_conflict(
            case.conflict_id,
            selected.candidate_id,
            expected_revision=case.revision,
            actor="KEDADA",
            rationale="Recover the human-facing projection from canonical state.",
            event_id="recovery-projection-1",
            resolved_at=as_of,
        )

    assert memory.memory_file.read_text(encoding="utf-8") == old_projection
    recovered = s10.WorkspaceMemory(root)
    assert "Use Postgres." in recovered.memory_file.read_text(encoding="utf-8")
    assert len(recovered.list_adjudications()) == 1
    assert recovered.list_conflicts(status=None)[0].status == "resolved"


def test_resolution_recovery_keeps_incumbent_without_duplicate_revision(
    s10, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "project"
    memory, as_of, _, case = _database_conflict(s10, root)
    incumbent = next(candidate for candidate in case.candidates if candidate.incumbent)

    def crash_after_conflict_write(name: str) -> None:
        if name == "after_conflict_write":
            raise OSError("simulated incumbent resolution exit")

    monkeypatch.setattr(memory, "_resolution_checkpoint", crash_after_conflict_write)
    with pytest.raises(OSError, match="incumbent resolution exit"):
        memory.resolve_conflict(
            case.conflict_id,
            incumbent.candidate_id,
            expected_revision=case.revision,
            actor="KEDADA",
            rationale="Keep the reviewed incumbent.",
            event_id="recovery-incumbent-1",
            resolved_at=as_of,
        )

    recovered = s10.WorkspaceMemory(root)
    entries = recovered._load_curated()
    assert len(entries) == 1
    assert entries[0].content == "Use SQLite."
    assert entries[0].revision == 1
    assert len(recovered.list_adjudications()) == 1


def test_resolution_recovery_discards_partial_journal_and_audit_tails(
    s10, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "project"
    memory, as_of, _, case = _database_conflict(s10, root)
    selected = next(candidate for candidate in case.candidates if not candidate.incumbent)

    def crash_after_conflict_phase(name: str) -> None:
        if name == "after_conflict_closed":
            raise OSError("simulated exit before audit")

    monkeypatch.setattr(memory, "_resolution_checkpoint", crash_after_conflict_phase)
    with pytest.raises(OSError, match="before audit"):
        memory.resolve_conflict(
            case.conflict_id,
            selected.candidate_id,
            expected_revision=case.revision,
            actor="KEDADA",
            rationale="Recover after partial append-only records.",
            event_id="recovery-partial-tail-1",
            resolved_at=as_of,
        )

    with memory.resolution_transaction_file.open("ab") as handle:
        handle.write(b'{"phase":')
    with memory.adjudication_file.open("ab") as handle:
        handle.write(b'{"event_id":')

    recovered = s10.WorkspaceMemory(root)
    transaction_records = [
        json.loads(line)
        for line in recovered.resolution_transaction_file.read_text(
            encoding="utf-8"
        ).splitlines()
    ]
    assert [record["phase"] for record in transaction_records] == [
        "prepared",
        "curated_applied",
        "conflict_closed",
        "audit_appended",
        "committed",
    ]
    assert [event.event_id for event in recovered.list_adjudications()] == [
        "recovery-partial-tail-1"
    ]


def test_modified_resolution_intent_fails_closed_before_recovery(
    s10, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "project"
    memory, as_of, _, case = _database_conflict(s10, root)
    selected = next(candidate for candidate in case.candidates if not candidate.incumbent)

    def crash_after_prepare(name: str) -> None:
        if name == "after_prepared":
            raise OSError("simulated exit after prepare")

    monkeypatch.setattr(memory, "_resolution_checkpoint", crash_after_prepare)
    with pytest.raises(OSError, match="after prepare"):
        memory.resolve_conflict(
            case.conflict_id,
            selected.candidate_id,
            expected_revision=case.revision,
            actor="KEDADA",
            rationale="Original reviewed intent.",
            event_id="recovery-tamper-1",
            resolved_at=as_of,
        )

    record = json.loads(
        memory.resolution_transaction_file.read_text(encoding="utf-8")
    )
    record["intent"]["adjudication"]["rationale"] = "Tampered intent."
    memory.resolution_transaction_file.write_text(
        json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    with pytest.raises(s10.MemoryCorruptionError, match="intent was modified"):
        s10.WorkspaceMemory(root)
    assert memory._load_conflicts()[0].status == "open"
    assert memory._load_curated()[0].content == "Use SQLite."
    assert memory._read_adjudications() == []


def test_resolution_recovery_refuses_unexpected_third_state(
    s10, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "project"
    memory, as_of, _, case = _database_conflict(s10, root)
    selected = next(candidate for candidate in case.candidates if not candidate.incumbent)

    def crash_after_prepare(name: str) -> None:
        if name == "after_prepared":
            raise OSError("simulated exit before canonical writes")

    monkeypatch.setattr(memory, "_resolution_checkpoint", crash_after_prepare)
    with pytest.raises(OSError, match="before canonical writes"):
        memory.resolve_conflict(
            case.conflict_id,
            selected.candidate_id,
            expected_revision=case.revision,
            actor="KEDADA",
            rationale="Do not overwrite unrelated post-prepare state.",
            event_id="recovery-third-state-1",
            resolved_at=as_of,
        )

    payload = json.loads(memory.curated_file.read_text(encoding="utf-8"))
    payload["entries"].append(
        {
            "key": "unrelated-valid-entry",
            "kind": "convention",
            "content": "An unrelated writer changed curated state.",
            "first_seen": "2026-01-01T12:00:00Z",
            "last_seen": "2026-01-01T12:00:00Z",
            "evidence_ids": ["unrelated-fact"],
            "occurrences": 1,
            "memory_key": None,
            "revision": 1,
            "status": "active",
            "supersedes": None,
            "superseded_by": None,
        }
    )
    memory.curated_file.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    with pytest.raises(s10.MemoryCorruptionError, match="unexpected curated state"):
        s10.WorkspaceMemory(root)
    assert memory._load_conflicts()[0].status == "open"
    assert memory._read_adjudications() == []


def test_resolution_retry_is_idempotent_and_event_reuse_is_rejected(
    s10, tmp_path: Path
) -> None:
    memory, as_of, _, case = _database_conflict(s10, tmp_path / "project")
    postgres = next(
        candidate for candidate in case.candidates if candidate.content == "Use Postgres."
    )
    mysql = next(
        candidate for candidate in case.candidates if candidate.content == "Use MySQL."
    )
    kwargs = {
        "expected_revision": case.revision,
        "actor": "KEDADA",
        "rationale": "Use the reviewed deployment standard.",
        "event_id": "review-retry-1",
        "resolved_at": as_of,
    }

    first = memory.resolve_conflict(
        case.conflict_id, postgres.candidate_id, **kwargs
    )
    second = memory.resolve_conflict(
        case.conflict_id, postgres.candidate_id, **kwargs
    )

    assert second == first
    assert len(memory.list_adjudications()) == 1
    assert len(memory._load_curated()) == 2
    with pytest.raises(s10.ConflictResolutionError, match="already used differently"):
        memory.resolve_conflict(case.conflict_id, mysql.candidate_id, **kwargs)


def test_reviewer_can_keep_incumbent_without_creating_fake_revision(
    s10, tmp_path: Path
) -> None:
    memory, as_of, _, case = _database_conflict(s10, tmp_path / "project")
    incumbent = next(candidate for candidate in case.candidates if candidate.incumbent)

    event = memory.resolve_conflict(
        case.conflict_id,
        incumbent.candidate_id,
        expected_revision=case.revision,
        actor="KEDADA",
        rationale="The alternatives do not justify changing the current database.",
        event_id="review-keep-current-1",
        resolved_at=as_of,
    )

    assert event.prior_active_entry_key == event.resulting_active_entry_key
    assert len(memory._load_curated()) == 1
    memory.distill(as_of=as_of)
    active = memory._load_curated()[0]
    assert active.content == "Use SQLite."
    assert active.revision == 1
    assert "Use Postgres." not in memory.get_context_for_agent()


def test_new_evidence_invalidates_observed_conflict_snapshot(
    s10, tmp_path: Path
) -> None:
    memory, as_of, _, case = _database_conflict(s10, tmp_path / "project")
    postgres = next(
        candidate for candidate in case.candidates if candidate.content == "Use Postgres."
    )
    memory.append_daily_log(
        "Use Postgres.",
        kind="decision",
        importance=4,
        memory_key="storage.database",
        recorded_at=_old(20),
        fact_id="pg3",
    )

    with pytest.raises(
        s10.StaleConflictResolutionError, match="evidence changed"
    ):
        memory.resolve_conflict(
            case.conflict_id,
            postgres.candidate_id,
            expected_revision=case.revision,
            actor="KEDADA",
            rationale="This review is now stale.",
            event_id="stale-review-1",
            resolved_at=as_of,
        )

    assert memory.list_adjudications() == []
    assert memory.list_conflicts()[0].conflict_id == case.conflict_id
    assert memory._load_curated()[0].content == "Use SQLite."


def test_refreshed_equal_conflict_supersedes_old_revision(
    s10, tmp_path: Path
) -> None:
    memory, as_of, _, original = _database_conflict(s10, tmp_path / "project")
    for content, fact_id in (("Use Postgres.", "pg3"), ("Use MySQL.", "mysql3")):
        memory.append_daily_log(
            content,
            kind="decision",
            importance=4,
            memory_key="storage.database",
            recorded_at=_old(20),
            fact_id=fact_id,
        )

    report = memory.distill(as_of=as_of)
    refreshed = memory.list_conflicts()[0]

    assert report.queued_conflicts == 1
    assert refreshed.revision == 2
    assert refreshed.conflict_id != original.conflict_id
    old = next(
        case
        for case in memory.list_conflicts(status=None)
        if case.conflict_id == original.conflict_id
    )
    assert old.status == "superseded"
    with pytest.raises(s10.StaleConflictResolutionError, match="not open"):
        memory.resolve_conflict(
            original.conflict_id,
            original.candidates[0].candidate_id,
            expected_revision=original.revision,
            actor="KEDADA",
            rationale="Old browser tab.",
            event_id="stale-revision-1",
            resolved_at=as_of,
        )


def test_conflict_queue_scope_validation_and_partial_audit_tail(
    s10, tmp_path: Path
) -> None:
    first, as_of, _, case = _database_conflict(s10, tmp_path / "project-a")
    selected = next(candidate for candidate in case.candidates if not candidate.incumbent)
    first.resolve_conflict(
        case.conflict_id,
        selected.candidate_id,
        expected_revision=case.revision,
        actor="KEDADA",
        rationale="Reviewed candidate.",
        event_id="audit-tail-1",
        resolved_at=as_of,
    )
    with first.adjudication_file.open("ab") as handle:
        handle.write(b'{"event_id":')
    assert [event.event_id for event in first.list_adjudications()] == ["audit-tail-1"]

    second = s10.WorkspaceMemory(tmp_path / "project-b")
    second.conflict_file.write_text(
        first.conflict_file.read_text(encoding="utf-8"), encoding="utf-8"
    )
    with pytest.raises(s10.MemoryScopeError, match="another workspace"):
        second.list_conflicts()


def test_unknown_candidate_and_invalid_boundary_values_fail_closed(
    s10, tmp_path: Path
) -> None:
    memory, as_of, _, case = _database_conflict(s10, tmp_path / "project")
    with pytest.raises(s10.ConflictResolutionError, match="is not part"):
        memory.resolve_conflict(
            case.conflict_id,
            "candidate-0000000000000000",
            expected_revision=case.revision,
            actor="KEDADA",
            rationale="Unknown candidate must fail.",
            event_id="unknown-candidate-1",
            resolved_at=as_of,
        )
    with pytest.raises(ValueError, match="event_id"):
        memory.resolve_conflict(
            case.conflict_id,
            case.candidates[0].candidate_id,
            expected_revision=case.revision,
            actor="KEDADA",
            rationale="Invalid event identifier.",
            event_id="bad event id",
            resolved_at=as_of,
        )
    with pytest.raises(TypeError, match="expected_revision must be an integer"):
        memory.resolve_conflict(
            case.conflict_id,
            case.candidates[0].candidate_id,
            expected_revision=True,
            actor="KEDADA",
            rationale="Boolean revisions must not pass as integers.",
            event_id="boolean-revision-1",
            resolved_at=as_of,
        )
    with pytest.raises(ValueError, match="unsupported conflict status"):
        memory.list_conflicts(status="pending")


def test_supersession_is_idempotent_and_recovers_in_a_new_instance(
    s10, tmp_path: Path
) -> None:
    root = tmp_path / "project"
    writer = s10.WorkspaceMemory(root)
    writer.append_daily_log(
        "Use npm.",
        kind="decision",
        importance=5,
        memory_key="frontend.package-manager",
        recorded_at=_old(1),
        fact_id="npm",
    )
    as_of = datetime(2026, 3, 1, tzinfo=timezone.utc)
    writer.distill(as_of=as_of)
    _append_pair(
        writer,
        "Use pnpm.",
        memory_key="frontend.package-manager",
        first_day=10,
        prefix="pnpm",
    )
    writer.distill(as_of=as_of)
    before = writer.curated_file.read_text(encoding="utf-8")

    rerun = writer.distill(as_of=as_of)
    recovered = s10.WorkspaceMemory(root)
    entries = recovered._load_curated()

    assert rerun.created == 0
    assert rerun.updated == 0
    assert rerun.superseded == 0
    assert writer.curated_file.read_text(encoding="utf-8") == before
    assert len(entries) == 2
    assert next(entry for entry in entries if entry.status == "active").revision == 2
    assert "Use pnpm." in recovered.get_context_for_agent()
    assert "Use npm." not in recovered.get_context_for_agent()


def test_schema_one_curated_state_migrates_on_next_successful_distill(
    s10, tmp_path: Path
) -> None:
    memory = s10.WorkspaceMemory(tmp_path / "project")
    memory.curated_file.parent.mkdir(parents=True, exist_ok=True)
    memory.curated_file.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "workspace_id": memory.workspace_id,
                "entries": [
                    {
                        "key": "legacy-entry",
                        "kind": "decision",
                        "content": "Keep the legacy decision.",
                        "first_seen": "2025-12-01T12:00:00Z",
                        "last_seen": "2025-12-01T12:00:00Z",
                        "evidence_ids": ["legacy-evidence"],
                        "occurrences": 1,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    assert "Keep the legacy decision." in memory.read_memory_md()
    legacy = memory._load_curated()[0]
    assert legacy.revision == 1
    assert legacy.status == "active"
    assert legacy.memory_key is None

    memory.append_daily_log(
        "Add a new convention.",
        kind="convention",
        importance=5,
        recorded_at=_old(2),
        fact_id="new-evidence",
    )
    memory.distill(as_of=datetime(2026, 3, 1, tzinfo=timezone.utc))
    migrated = json.loads(memory.curated_file.read_text(encoding="utf-8"))

    assert migrated["schema_version"] == 2
    migrated_legacy = next(
        entry for entry in migrated["entries"] if entry["key"] == "legacy-entry"
    )
    assert migrated_legacy["revision"] == 1
    assert migrated_legacy["status"] == "active"
    assert migrated_legacy["supersedes"] is None


def test_corrupt_lifecycle_with_two_active_revisions_is_rejected(
    s10, tmp_path: Path
) -> None:
    memory = s10.WorkspaceMemory(tmp_path / "project")
    base = {
        "kind": "decision",
        "first_seen": "2026-01-01T12:00:00Z",
        "last_seen": "2026-01-01T12:00:00Z",
        "occurrences": 1,
        "memory_key": "runtime.python-version",
        "status": "active",
        "supersedes": None,
        "superseded_by": None,
    }
    memory.curated_file.parent.mkdir(parents=True, exist_ok=True)
    memory.curated_file.write_text(
        json.dumps(
            {
                "schema_version": 2,
                "workspace_id": memory.workspace_id,
                "entries": [
                    {
                        **base,
                        "key": "revision-one",
                        "content": "Use Python 3.11.",
                        "revision": 1,
                        "evidence_ids": ["one"],
                    },
                    {
                        **base,
                        "key": "revision-two",
                        "content": "Use Python 3.12.",
                        "revision": 2,
                        "evidence_ids": ["two"],
                    },
                ],
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(s10.MemoryCorruptionError, match="multiple active revisions"):
        memory.read_memory_md()
