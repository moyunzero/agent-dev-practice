"""Offline contract tests for s11's user-scoped profile and preferences."""

from __future__ import annotations

import importlib.util
import json
import os
import sys
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def s11():
    stub_dir = ROOT / "tests" / "stubs"
    sys.path.insert(0, str(stub_dir))
    saved_anthropic = sys.modules.pop("anthropic", None)
    old_model = os.environ.get("MODEL_ID")
    os.environ["MODEL_ID"] = "offline-test-model"
    module_name = "s11_user_memory_test_module"
    try:
        spec = importlib.util.spec_from_file_location(
            module_name, ROOT / "s11_user_memory" / "code.py"
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


def _establish_identity(memory) -> None:
    memory.save_identity(
        soul="# Soul\n\nBe useful.",
        assistant_identity="# Identity\n\nName: WorkBuddy",
        profile={"name": "Alice", "call_them": "Alice"},
    )


@pytest.mark.parametrize("stage", ["write", "flush", "fsync", "replace"])
@pytest.mark.parametrize("existing", [True, False])
def test_atomic_write_cleans_up_after_failure(s11, tmp_path, monkeypatch, stage, existing):
    target = tmp_path / "profile.json"
    old = '{"city": "Shanghai"}'
    new = '{"city": "Beijing"}'
    if existing:
        target.write_text(old, encoding="utf-8")
    original_tempfile = s11.tempfile.NamedTemporaryFile

    def fail(*args, **kwargs):
        raise OSError(f"injected {stage} failure")

    @contextmanager
    def failing_tempfile(*args, **kwargs):
        # Use a real temporary file so cleanup is tested on disk, not on a mock.
        with original_tempfile(*args, **kwargs) as handle:
            monkeypatch.setattr(handle, stage, fail)
            yield handle

    with monkeypatch.context() as patch:
        if stage in {"write", "flush"}:
            patch.setattr(s11.tempfile, "NamedTemporaryFile", failing_tempfile)
        else:
            patch.setattr(s11.os, stage, fail)
        with pytest.raises(OSError, match=f"injected {stage} failure"):
            s11.UserMemory._atomic_write_text(target, new)
    assert target.exists() == existing
    if existing:
        assert target.read_text(encoding="utf-8") == old
    assert list(tmp_path.glob(".profile.json.*.tmp")) == []

    # Once the underlying failure is gone, the same write can be retried.
    s11.UserMemory._atomic_write_text(target, new)
    assert target.read_text(encoding="utf-8") == new
    assert list(tmp_path.glob(".profile.json.*.tmp")) == []


def test_profile_patch_is_explicit_partial_and_restart_safe(s11, tmp_path: Path) -> None:
    root = tmp_path / "user-memory"
    memory = s11.UserMemory(root, user_id="alice@example.com")

    first = memory.update_profile(
        {"name": "Alice", "call_them": "Alice", "timezone": "UTC+8"}
    )
    repeated = memory.update_profile({"name": "Alice"})
    changed = memory.update_profile({"call_them": "A", "timezone": None})

    assert first.changed == ("call_them", "name", "timezone")
    assert repeated.unchanged == ("name",)
    assert changed.changed == ("call_them", "timezone")
    recovered = s11.UserMemory(root, user_id="alice@example.com")
    assert recovered.read_profile() == {"name": "Alice", "call_them": "A"}
    assert "Call them: A" in recovered.user_path.read_text(encoding="utf-8")


@pytest.mark.parametrize("value", [{"unexpected": "Beijing"}, ["Beijing"], 42, True, "", "  ", "x" * 1001])
def test_profile_rejects_invalid_patch_without_writes(s11, tmp_path, value):
    memory = s11.UserMemory(tmp_path, user_id="alice")
    _establish_identity(memory)
    before = (memory.profile_path.read_bytes(), memory.user_path.read_bytes())
    # A valid earlier field must not be committed if a later field is invalid.
    with pytest.raises(s11.UserMemoryValidationError):
        memory.update_profile({"name": "Bob", "city": value})
    assert (memory.profile_path.read_bytes(), memory.user_path.read_bytes()) == before


@pytest.mark.parametrize("profile", [
    {"name": None}, {"city": {"unexpected": "Beijing"}}, {"city": ["Beijing"]},
    {"city": 42}, {"city": True}, {"name": ""}, {"name": "  "},
    {"notes": "x" * 1001}, {"unknown": "value"}, [],
])
def test_profile_rejects_invalid_disk_records_before_projection(s11, tmp_path, profile):
    memory = s11.UserMemory(tmp_path, user_id="alice")
    _establish_identity(memory)
    payload = json.loads(memory.profile_path.read_text())
    payload["profile"] = profile
    memory.profile_path.write_text(json.dumps(payload), encoding="utf-8")
    before = (memory.profile_path.read_bytes(), memory.user_path.read_bytes())
    restarted = s11.UserMemory(tmp_path, user_id="alice")
    for read in (restarted.read_profile, restarted.load_identity, restarted.get_context_for_agent):
        with pytest.raises(s11.UserMemoryValidationError):
            read()
    with pytest.raises(s11.UserMemoryValidationError):
        restarted.update_profile({"name": "Bob"})
    assert (memory.profile_path.read_bytes(), memory.user_path.read_bytes()) == before


@pytest.mark.parametrize("version", [1, 2])
def test_profile_valid_strings_remain_restart_safe(s11, tmp_path, version):
    memory = s11.UserMemory(tmp_path, user_id="alice")
    memory.update_profile({"name": "  Alice\n Smith ", "notes": "x" * 1000})
    payload = json.loads(memory.profile_path.read_text())
    payload["schema_version"] = version
    memory.profile_path.write_text(json.dumps(payload), encoding="utf-8")
    before = memory.profile_path.read_bytes()
    restarted = s11.UserMemory(tmp_path, user_id="alice")
    assert restarted.read_profile() == {"name": "Alice Smith", "notes": "x" * 1000}
    assert memory.profile_path.read_bytes() == before
    assert restarted.update_profile({"notes": None}).changed == ("notes",)
    assert restarted.read_profile() == {"name": "Alice Smith"}


@pytest.mark.parametrize("new_city", ["Beijing", None])
@pytest.mark.parametrize("recovery", ["retry", "restart"])
def test_profile_projection_recovers_after_partial_write(s11, tmp_path, monkeypatch, new_city, recovery):
    memory = s11.UserMemory(tmp_path, user_id="alice")
    _establish_identity(memory)
    memory.update_profile({"city": "Shanghai"})
    original_write = memory._atomic_write_text

    def fail_projection(path, content):
        if path == memory.user_path:
            raise OSError("injected projection failure")
        original_write(path, content)

    with monkeypatch.context() as patch:
        patch.setattr(memory, "_atomic_write_text", fail_projection)
        with pytest.raises(OSError, match="projection failure"):
            memory.update_profile({"city": new_city})
    canonical = memory.profile_path.read_bytes()
    assert "Shanghai" in memory.user_path.read_text()
    if recovery == "retry":
        assert memory.update_profile({"city": new_city}).unchanged == ("city",)
        assert "Shanghai" not in memory.user_path.read_text()
    else:
        memory = s11.UserMemory(tmp_path, user_id="alice")
    context = memory.get_context_for_agent()
    assert "Shanghai" not in context
    assert ("City: Beijing" in context) == (new_city is not None)
    assert memory.profile_path.read_bytes() == canonical


@pytest.mark.parametrize("damage", ["stale", "missing", "empty_profile"])
def test_profile_projection_is_repaired_without_rewriting_json(s11, tmp_path, monkeypatch, damage):
    memory = s11.UserMemory(tmp_path, user_id="alice")
    _establish_identity(memory)
    if damage == "empty_profile":
        memory.update_profile({key: None for key in memory.read_profile()})
    canonical = memory.profile_path.read_bytes()
    if damage == "missing":
        memory.user_path.unlink()
    else:
        memory.user_path.write_text("stale profile", encoding="utf-8")
    user = memory.load_identity()["user"]
    assert "stale profile" not in user
    assert ("Name: Alice" in user) == (damage != "empty_profile")
    assert memory.profile_path.read_bytes() == canonical
    assert memory.user_path.read_text() == user
    def unexpected_write(*args, **kwargs):
        raise AssertionError("current projections must not be rewritten")
    monkeypatch.setattr(memory, "_atomic_write_text", unexpected_write)
    assert memory.load_identity()["user"] == user


def test_failed_profile_repair_does_not_return_stale_prompt(s11, tmp_path, monkeypatch):
    memory = s11.UserMemory(tmp_path, user_id="alice")
    _establish_identity(memory)
    memory.user_path.write_text("stale profile", encoding="utf-8")
    def fail_write(*args, **kwargs):
        raise OSError("cannot repair projection")
    monkeypatch.setattr(memory, "_atomic_write_text", fail_write)
    with pytest.raises(OSError, match="cannot repair"):
        memory.get_context_for_agent()


def test_preference_key_deduplicates_retries_and_replaces_stale_value(
    s11, tmp_path: Path
) -> None:
    memory = s11.UserMemory(tmp_path / "user-memory", user_id="alice")

    created = memory.set_preference(
        "response.language", "Chinese", updated_at="2026-08-09T01:00:00Z"
    )
    unchanged = memory.set_preference(
        "response.language", "Chinese", updated_at="2026-08-09T01:00:00Z"
    )
    updated = memory.set_preference(
        "response.language", "English", updated_at="2026-08-09T03:00:00Z"
    )

    assert created.status is s11.WriteStatus.CREATED
    assert unchanged.status is s11.WriteStatus.UNCHANGED
    assert unchanged.revision == 1
    assert updated.status is s11.WriteStatus.UPDATED
    assert updated.previous_value == "Chinese"
    assert updated.revision == 2
    assert memory.read_memory().count("response.language") == 1
    assert "English" in memory.read_memory()
    assert "Chinese" not in memory.read_memory()


@pytest.mark.parametrize("restart", [False, True])
@pytest.mark.parametrize("use_event_ids", [False, True])
def test_new_confirmation_blocks_delayed_conflict(s11, tmp_path, restart, use_event_ids):
    memory = s11.UserMemory(tmp_path, user_id="alice")
    memory.set_preference(
        "response.language", "Chinese", updated_at="2026-09-14T09:00:00Z",
        source_event_id="event-1" if use_event_ids else None,
    )
    confirmed = memory.set_preference(
        "response.language", "Chinese", updated_at="2026-09-14T11:00:00Z",
        source_event_id="event-3" if use_event_ids else None,
    )
    assert confirmed.status is s11.WriteStatus.UPDATED
    assert confirmed.revision == 2
    if restart:
        memory = s11.UserMemory(tmp_path, user_id="alice")
    assert memory.list_preferences()[0].updated_at == "2026-09-14T11:00:00Z"
    before = memory.preferences_path.read_bytes()
    with pytest.raises(s11.StalePreferenceUpdateError):
        memory.set_preference(
            "response.language", "English", updated_at="2026-09-14T10:00:00Z",
            source_event_id="event-2" if use_event_ids else None,
        )
    assert memory.preferences_path.read_bytes() == before
    assert memory.list_preferences()[0].value == "Chinese"


@pytest.mark.parametrize("event_id", [None, "event-1"])
def test_same_evidence_retry_keeps_timestamp_and_bytes(s11, tmp_path, event_id):
    memory = s11.UserMemory(tmp_path, user_id="alice")
    memory.set_preference(
        "response.language", "Chinese", updated_at="2026-09-14T09:00:00Z",
        source_event_id=event_id,
    )
    before = memory.preferences_path.read_bytes()
    # With an ID, a later retry clock is irrelevant; without one, replay the
    # original evidence time (including equivalent timezone representations).
    retry_time = "2026-09-14T11:00:00Z" if event_id else "2026-09-14T17:00:00+08:00"
    retry = memory.set_preference(
        "response.language", "Chinese", updated_at=retry_time, source_event_id=event_id,
    )
    assert retry.status is s11.WriteStatus.UNCHANGED
    assert retry.revision == 1
    assert memory.preferences_path.read_bytes() == before


def test_implicit_clock_is_not_new_confirmation(s11, tmp_path, monkeypatch):
    memory = s11.UserMemory(tmp_path, user_id="alice")
    memory.set_preference("response.language", "Chinese", updated_at="2026-09-14T09:00:00Z")
    before = memory.preferences_path.read_bytes()
    monkeypatch.setattr(s11, "_now_iso", lambda: "2026-09-14T11:00:00Z")
    assert memory.set_preference("response.language", "Chinese").status is s11.WriteStatus.UNCHANGED
    assert memory.preferences_path.read_bytes() == before


def test_two_users_share_a_root_without_sharing_state(s11, tmp_path: Path) -> None:
    root = tmp_path / "user-memory"
    alice = s11.UserMemory(root, user_id="alice")
    bob = s11.UserMemory(root, user_id="bob")

    alice.update_profile({"name": "Alice"})
    alice.set_preference("editor.indent", "tabs")
    bob.update_profile({"name": "Bob"})
    bob.set_preference("editor.indent", "spaces")

    assert alice.base_dir != bob.base_dir
    assert alice.read_profile() == {"name": "Alice"}
    assert bob.read_profile() == {"name": "Bob"}
    assert alice.list_preferences()[0].value == "tabs"
    assert bob.list_preferences()[0].value == "spaces"
    assert "Bob" not in alice.get_context_for_agent()


def test_canonical_scope_marker_rejects_cross_user_file_copy(s11, tmp_path: Path) -> None:
    root = tmp_path / "user-memory"
    alice = s11.UserMemory(root, user_id="alice")
    bob = s11.UserMemory(root, user_id="bob")
    alice.set_preference("response.detail", "concise")
    bob.preferences_path.write_text(
        alice.preferences_path.read_text(encoding="utf-8"), encoding="utf-8"
    )

    with pytest.raises(s11.UserScopeError, match="another user scope"):
        bob.list_preferences()


def test_context_contains_user_state_but_not_workspace_state(s11, tmp_path: Path) -> None:
    memory = s11.UserMemory(tmp_path / "user-memory", user_id="alice")
    _establish_identity(memory)
    memory.set_preference("response.language", "Chinese")

    context = memory.get_context_for_agent()

    assert "## User profile" in context
    assert "response.language" in context
    assert "workspace" not in context.casefold()
    assert ".learn_workbuddy/memory" not in context


def test_projection_is_repaired_from_canonical_preferences(s11, tmp_path: Path) -> None:
    memory = s11.UserMemory(tmp_path / "user-memory", user_id="alice")
    memory.set_preference("response.language", "Chinese")
    memory.memory_path.write_text("stale projection", encoding="utf-8")

    assert "response.language" in memory.read_memory()
    assert "stale projection" not in memory.memory_path.read_text(encoding="utf-8")


def test_preference_json_is_stable_and_addressable(s11, tmp_path: Path) -> None:
    memory = s11.UserMemory(tmp_path / "user-memory", user_id="alice")
    memory.set_preference("response.detail", "concise")
    memory.set_preference("editor.indent", "tabs")

    payload = json.loads(memory.preferences_path.read_text(encoding="utf-8"))

    assert payload["user_scope"] == memory.scope_id
    assert [item["key"] for item in payload["preferences"]] == [
        "editor.indent",
        "response.detail",
    ]


def test_expired_preference_stays_canonical_but_never_reaches_prompt(
    s11, tmp_path: Path
) -> None:
    memory = s11.UserMemory(tmp_path / "user-memory", user_id="alice")
    _establish_identity(memory)
    memory.set_preference(
        "response.detail",
        "verbose during onboarding",
        source="transcript",
        source_event_id="session-7:event-42",
        updated_at="2026-08-01T09:00:00+08:00",
        expires_at="2026-08-02T09:00:00+08:00",
    )
    before_expiry = datetime(2026, 8, 2, 0, 59, 59, tzinfo=timezone.utc)
    at_expiry = datetime(2026, 8, 2, 1, 0, 0, tzinfo=timezone.utc)

    preference = memory.list_preferences()[0]
    assert preference.updated_at == "2026-08-01T01:00:00Z"
    assert preference.expires_at == "2026-08-02T01:00:00Z"
    assert preference.source_event_id == "session-7:event-42"
    assert preference.status(as_of=before_expiry) is s11.PreferenceStatus.ACTIVE
    assert preference.status(as_of=at_expiry) is s11.PreferenceStatus.EXPIRED
    assert "response.detail" in memory.get_context_for_agent(as_of=before_expiry)
    assert "response.detail" not in memory.get_context_for_agent(as_of=at_expiry)

    # Time-travel reads are pure and expired records remain auditable.
    current_projection = memory.memory_path.read_text(encoding="utf-8")
    assert "response.detail" in memory.read_memory(as_of=before_expiry)
    assert memory.memory_path.read_text(encoding="utf-8") == current_projection
    payload = json.loads(memory.preferences_path.read_text(encoding="utf-8"))
    assert len(payload["preferences"]) == 1


def test_lifecycle_and_provenance_changes_are_revisioned_but_retries_are_not(
    s11, tmp_path: Path
) -> None:
    memory = s11.UserMemory(tmp_path / "user-memory", user_id="alice")
    common = {
        "source": "transcript",
        "source_event_id": "event-1",
        "expires_at": "2099-01-01T00:00:00Z",
    }
    created = memory.set_preference(
        "response.language",
        "Chinese",
        updated_at="2026-08-01T00:00:00Z",
        **common,
    )
    retry = memory.set_preference(
        "response.language",
        "Chinese",
        updated_at="2026-08-02T00:00:00Z",
        **common,
    )
    extended = memory.set_preference(
        "response.language",
        "Chinese",
        source="transcript",
        source_event_id="event-1",
        updated_at="2026-08-03T00:00:00Z",
        expires_at="2099-02-01T00:00:00Z",
    )
    new_evidence = memory.set_preference(
        "response.language",
        "Chinese",
        source="transcript",
        source_event_id="event-2",
        updated_at="2026-08-04T00:00:00Z",
        expires_at="2099-02-01T00:00:00Z",
    )

    assert created.status is s11.WriteStatus.CREATED
    assert retry.status is s11.WriteStatus.UNCHANGED
    assert retry.revision == 1
    assert extended.status is s11.WriteStatus.UPDATED
    assert extended.revision == 2
    assert new_evidence.status is s11.WriteStatus.UPDATED
    assert new_evidence.revision == 3
    recovered = s11.UserMemory(tmp_path / "user-memory", user_id="alice")
    assert recovered.list_preferences()[0].source_event_id == "event-2"

    with pytest.raises(s11.StalePreferenceUpdateError, match="newer canonical"):
        recovered.set_preference(
            "response.language",
            "English",
            source="transcript",
            source_event_id="stale-event",
            updated_at="2026-08-03T12:00:00Z",
        )
    assert recovered.list_preferences()[0].value == "Chinese"


def test_timestamps_and_source_event_ids_fail_closed(s11, tmp_path: Path) -> None:
    memory = s11.UserMemory(tmp_path / "user-memory", user_id="alice")

    with pytest.raises(s11.UserMemoryValidationError, match="timezone"):
        memory.set_preference(
            "response.detail",
            "concise",
            updated_at="2026-08-01T00:00:00",
        )
    with pytest.raises(s11.UserMemoryValidationError, match="later than"):
        memory.set_preference(
            "response.detail",
            "concise",
            updated_at="2026-08-02T00:00:00Z",
            expires_at="2026-08-02T00:00:00Z",
        )
    with pytest.raises(s11.UserMemoryValidationError, match="source_event_id"):
        memory.set_preference(
            "response.detail",
            "concise",
            source_event_id="event id with spaces",
        )
    with pytest.raises(s11.UserMemoryValidationError, match="as_of"):
        memory.list_active_preferences(as_of=datetime(2026, 8, 1))


def test_schema_one_preferences_migrate_on_next_observable_update(
    s11, tmp_path: Path
) -> None:
    memory = s11.UserMemory(tmp_path / "user-memory", user_id="alice")
    memory.preferences_path.parent.mkdir(parents=True, exist_ok=True)
    memory.preferences_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "user_scope": memory.scope_id,
                "preferences": [
                    {
                        "key": "response.language",
                        "value": "Chinese",
                        "source": "explicit",
                        "updated_at": "2026-08-01T00:00:00Z",
                        "revision": 1,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    legacy = memory.list_preferences()[0]
    assert legacy.expires_at is None
    assert legacy.source_event_id is None
    memory.set_preference(
        "response.language",
        "Chinese",
        updated_at="2026-08-02T00:00:00Z",
        expires_at="2099-01-01T00:00:00Z",
        source_event_id="event-migration",
    )
    migrated = json.loads(memory.preferences_path.read_text(encoding="utf-8"))

    assert migrated["schema_version"] == 2
    record = migrated["preferences"][0]
    assert record["revision"] == 2
    assert record["expires_at"] == "2099-01-01T00:00:00Z"
    assert record["source_event_id"] == "event-migration"


def test_model_tool_can_set_expiry_but_cannot_forge_source_event_id(s11) -> None:
    tool = next(
        item
        for item in s11.IdentityAwareAgent._build_tools()
        if item["name"] == "save_user_preference"
    )
    properties = tool["input_schema"]["properties"]

    assert properties["expires_at"]["format"] == "date-time"
    assert "source_event_id" not in properties
