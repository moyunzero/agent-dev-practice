#!/usr/bin/env python3
"""s11_user_memory - explicit, user-scoped profile and preferences.

s10 keeps durable facts owned by one workspace.  This chapter adds the next
ownership boundary: facts about a person that should follow that person across
projects.  The canonical state is structured JSON; ``persona/user.md`` and
``MEMORY.md`` are readable projections used for inspection and prompt assembly.

The core is deliberately provider-neutral so profile updates, preference
deduplication, scope isolation, atomic writes, and restart recovery can all be
tested offline.  The two small agent adapters at the end only demonstrate how
an LLM can call those explicit state transitions.

Usage:
    python s11_user_memory/code.py --demo
    python s11_user_memory/code.py
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Mapping


# Machine-readable learning path metadata.  User memory preserves s10's
# durable/derived-state distinction, but changes the owner from a workspace to
# an explicit user scope.
PROGRESSION = {
    "chapter": "s11_user_memory",
    "builds_on": ["s10_workspace_memory"],
    "adds": [
        "user-scoped profile",
        "explicit preference updates",
        "idempotent preference dedupe",
        "expiring preference lifecycle",
        "source-event provenance",
    ],
    "preserves": ["workspace memory remains a separate ownership layer"],
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
from mini_workbuddy.paths import tutorial_workbuddy_home


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


WORKDIR = Path.cwd()
# The tutorial namespace cannot collide with a real product's ~/.workbuddy.
USER_MEMORY_ROOT = tutorial_workbuddy_home() / "user-memory"
SCHEMA_VERSION = 2
SUPPORTED_SCHEMA_VERSIONS = frozenset({1, SCHEMA_VERSION})
MAX_PREFERENCE_CHARS = 4_000
MAX_SOURCE_EVENT_ID_CHARS = 200
PROFILE_FIELDS = frozenset(
    {"name", "call_them", "pronouns", "city", "timezone", "notes"}
)
PREFERENCE_KEY = re.compile(r"^[a-z0-9]+(?:[._-][a-z0-9]+)*$")
SOURCE_EVENT_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,199}$")


BOOTSTRAP_TEMPLATE = """# Bootstrap

This is your first conversation. Learn only stable user-level information:
1. Ask the user's name and how they would like to be addressed
2. Ask their city or timezone when it is useful
3. Ask for one explicit cross-project communication preference
4. Ask what name and emoji they would like to give the assistant

After the conversation, call save_identity once. The harness writes the user
profile and preference explicitly, then removes this one-time file.
"""


DEFAULT_SOUL = """# Soul

Be genuinely helpful, not performatively helpful.

## Values
- Honesty over comfort. Don't sugarcoat problems.
- Action over explanation. Do the thing, don't just describe it.
- Concise by default. Long answers need justification.

## Boundaries
- Never guess at URLs or API endpoints.
- Never modify files without understanding them first.
- Ask before destructive operations.

## Vibe
- Direct, warm, slightly dry humor.
- Treat the user as a competent adult.
"""


class UserMemoryError(RuntimeError):
    """Base class for failures at the user-memory boundary."""


class UserScopeError(UserMemoryError):
    """Raised when persisted state belongs to a different user scope."""


class UserMemoryValidationError(UserMemoryError):
    """Raised before invalid profile or preference data reaches disk."""


class StalePreferenceUpdateError(UserMemoryError):
    """Raised when older evidence attempts to replace a newer preference."""


class WriteStatus(str, Enum):
    """Observable result of an explicit preference mutation."""

    CREATED = "created"
    UPDATED = "updated"
    UNCHANGED = "unchanged"
    DELETED = "deleted"


class PreferenceStatus(str, Enum):
    """Time-derived state; expiration never deletes canonical evidence."""

    ACTIVE = "active"
    EXPIRED = "expired"


@dataclass(frozen=True)
class Preference:
    """One addressable cross-project rule owned by a user."""

    key: str
    value: str
    source: str
    updated_at: str
    revision: int = 1
    expires_at: str | None = None
    source_event_id: str | None = None

    def status(self, *, as_of: datetime | None = None) -> PreferenceStatus:
        if self.expires_at is None:
            return PreferenceStatus.ACTIVE
        return (
            PreferenceStatus.ACTIVE
            if _as_utc(as_of)
            < _parse_timestamp(self.expires_at, field_name="expires_at")
            else PreferenceStatus.EXPIRED
        )

    def is_active(self, *, as_of: datetime | None = None) -> bool:
        return self.status(as_of=as_of) is PreferenceStatus.ACTIVE

    @classmethod
    def from_dict(cls, payload: Mapping[str, object]) -> "Preference":
        try:
            revision = int(payload.get("revision", 1))
            if revision < 1:
                raise ValueError("revision must be positive")
            updated_at = _normalize_timestamp(
                str(payload["updated_at"]), field_name="updated_at"
            )
            raw_expiry = payload.get("expires_at")
            expires_at = (
                None
                if raw_expiry in (None, "")
                else _normalize_timestamp(str(raw_expiry), field_name="expires_at")
            )
            if expires_at is not None and _parse_timestamp(
                expires_at, field_name="expires_at"
            ) <= _parse_timestamp(updated_at, field_name="updated_at"):
                raise ValueError("expires_at must be later than updated_at")
            return cls(
                key=_preference_key(str(payload["key"])),
                value=_clean_text(
                    payload["value"],
                    field_name="preference value",
                    max_chars=MAX_PREFERENCE_CHARS,
                ),
                source=_clean_text(
                    payload.get("source", "explicit"),
                    field_name="source",
                    max_chars=100,
                ),
                updated_at=updated_at,
                revision=revision,
                expires_at=expires_at,
                source_event_id=_optional_source_event_id(
                    payload.get("source_event_id")
                ),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise UserMemoryValidationError(f"invalid preference record: {exc}") from exc


@dataclass(frozen=True)
class PreferenceWrite:
    """Result returned to tools, tests, and audit code after a mutation."""

    status: WriteStatus
    key: str
    previous_value: str | None
    current_value: str | None
    revision: int


@dataclass(frozen=True)
class ProfileWrite:
    """Fields changed and fields already current in one explicit profile patch."""

    changed: tuple[str, ...] = field(default_factory=tuple)
    unchanged: tuple[str, ...] = field(default_factory=tuple)


def _as_utc(value: datetime | None = None) -> datetime:
    current = value or datetime.now(timezone.utc)
    if current.tzinfo is None or current.utcoffset() is None:
        raise UserMemoryValidationError("as_of must include a timezone")
    return current.astimezone(timezone.utc)


def _format_timestamp(value: datetime) -> str:
    return _as_utc(value).isoformat().replace("+00:00", "Z")


def _parse_timestamp(value: str, *, field_name: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise UserMemoryValidationError(
            f"{field_name} must be an ISO-8601 timestamp"
        ) from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise UserMemoryValidationError(f"{field_name} must include a timezone")
    return parsed.astimezone(timezone.utc)


def _normalize_timestamp(value: str, *, field_name: str) -> str:
    return _format_timestamp(_parse_timestamp(value, field_name=field_name))


def _now_iso() -> str:
    return _format_timestamp(datetime.now(timezone.utc))


def _scope_id(user_id: str) -> str:
    normalized = user_id.strip().casefold()
    if not normalized:
        raise UserMemoryValidationError("user_id must not be empty")
    # A stable digest makes arbitrary account identifiers safe as path names
    # while keeping the original identifier out of prompts and file listings.
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:16]


def _preference_key(value: str) -> str:
    key = value.strip().casefold()
    if not PREFERENCE_KEY.fullmatch(key):
        raise UserMemoryValidationError(
            "preference key must use lowercase words separated by '.', '_' or '-'"
        )
    return key


def _clean_text(value: object, *, field_name: str, max_chars: int) -> str:
    text = re.sub(r"\s+", " ", str(value)).strip()
    if not text:
        raise UserMemoryValidationError(f"{field_name} must not be empty")
    if len(text) > max_chars:
        raise UserMemoryValidationError(
            f"{field_name} exceeds the {max_chars}-character teaching limit"
        )
    return text


def _profile_text(key: str, value: object) -> str:
    """Validate profile fields at both the write and disk-read boundaries."""

    if key not in PROFILE_FIELDS:
        raise UserMemoryValidationError(f"unknown profile field: {key}")
    # Do not turn null, containers or numbers into apparent facts via str().
    # None is a deletion instruction only in update_profile, never stored data.
    if not isinstance(value, str):
        raise UserMemoryValidationError(f"{key} must be a string")
    return _clean_text(value, field_name=key, max_chars=1_000)


def _optional_source_event_id(value: object | None) -> str | None:
    if value is None:
        return None
    event_id = _clean_text(
        value,
        field_name="source_event_id",
        max_chars=MAX_SOURCE_EVENT_ID_CHARS,
    )
    if not SOURCE_EVENT_ID.fullmatch(event_id):
        raise UserMemoryValidationError(
            "source_event_id must be an opaque event identifier"
        )
    return event_id


class UserMemory:
    """Durable profile and preferences isolated by explicit user scope.

    Layout under the tutorial state root::

        user-memory/users/<scope-id>/
        ├── profile.json              # canonical user facts
        ├── preferences.json          # canonical keyed rules
        ├── MEMORY.md                 # derived prompt/readable preference view
        └── persona/
            ├── core.md               # assistant values and boundaries
            ├── identity.md           # assistant name/type/emoji
            ├── user.md               # derived readable profile view
            └── bootstrap.md          # one-time setup, deleted on completion

    ``user_id`` is mandatory in the storage model even when the interactive
    lesson defaults it to ``local-user``.  A workspace path is intentionally
    absent: project facts belong to s10 and must never leak into this layer.
    """

    def __init__(self, base_dir: Path | None = None, *, user_id: str = "local-user"):
        self.root_dir = Path(base_dir or USER_MEMORY_ROOT).expanduser().resolve()
        self.user_id = user_id.strip()
        self.scope_id = _scope_id(self.user_id)
        self.base_dir = self.root_dir / "users" / self.scope_id
        self.persona_dir = self.base_dir / "persona"
        self.profile_path = self.base_dir / "profile.json"
        self.preferences_path = self.base_dir / "preferences.json"
        self.memory_path = self.base_dir / "MEMORY.md"
        self.soul_path = self.persona_dir / "core.md"
        self.identity_path = self.persona_dir / "identity.md"
        self.user_path = self.persona_dir / "user.md"
        self.bootstrap_path = self.persona_dir / "bootstrap.md"
        self.persona_dir.mkdir(parents=True, exist_ok=True)

    # ── Bootstrap lifecycle ───────────────────────────────────

    def needs_bootstrap(self) -> bool:
        """Return whether the one-time setup instruction still exists."""

        return self.bootstrap_path.exists()

    def create_bootstrap(self) -> None:
        """Create the setup instruction without overwriting an interrupted run."""

        if not self.bootstrap_path.exists():
            self.bootstrap_path.write_text(BOOTSTRAP_TEMPLATE, encoding="utf-8")

    def read_bootstrap(self) -> str:
        return self._read_text(self.bootstrap_path)

    def delete_bootstrap(self) -> None:
        """Finish bootstrap only after both user and assistant identity exist."""

        if not self.is_identity_established():
            raise UserMemoryValidationError(
                "cannot complete bootstrap before profile and assistant identity are saved"
            )
        self.bootstrap_path.unlink(missing_ok=True)

    # ── Profile: stable facts about the person ────────────────

    def read_profile(self) -> dict[str, str]:
        payload = self._read_scoped_json(self.profile_path, default_key="profile")
        profile = payload.get("profile", {})
        if not isinstance(profile, dict):
            raise UserMemoryValidationError("profile must be a JSON object")
        # Scope/schema checks alone do not make on-disk facts safe to project.
        # Validate without rewriting the canonical file during a read.
        return {key: _profile_text(key, value) for key, value in profile.items()}

    def update_profile(self, changes: Mapping[str, object]) -> ProfileWrite:
        """Apply an explicit partial update; omitted fields remain untouched.

        A ``None`` value removes a field.  Unknown fields are rejected instead
        of silently becoming prompt data, which keeps the profile contract
        inspectable and prevents an LLM from inventing a new schema per turn.
        """

        unknown = sorted(set(changes) - PROFILE_FIELDS)
        if unknown:
            raise UserMemoryValidationError(
                f"unknown profile fields: {', '.join(unknown)}"
            )

        profile = self.read_profile()
        changed: list[str] = []
        unchanged: list[str] = []
        for key, raw_value in changes.items():
            if raw_value is None:
                if key in profile:
                    del profile[key]
                    changed.append(key)
                else:
                    unchanged.append(key)
                continue
            value = _profile_text(key, raw_value)
            if profile.get(key) == value:
                unchanged.append(key)
            else:
                profile[key] = value
                changed.append(key)

        if changed:
            self._write_scoped_json(self.profile_path, "profile", profile)
        # A previous attempt may have committed JSON but failed to refresh
        # Markdown. Even an unchanged retry must reconcile that derived view.
        self._write_profile_projection(profile)
        return ProfileWrite(tuple(sorted(changed)), tuple(sorted(unchanged)))

    # ── Preferences: addressable, explicit cross-project rules ─

    def list_preferences(self) -> list[Preference]:
        """Return every canonical record, including expired audit evidence."""

        payload = self._read_scoped_json(
            self.preferences_path, default_key="preferences"
        )
        records = payload.get("preferences", [])
        if not isinstance(records, list):
            raise UserMemoryValidationError("preferences must be a JSON array")
        preferences = [Preference.from_dict(item) for item in records]
        if len({item.key for item in preferences}) != len(preferences):
            raise UserMemoryValidationError("duplicate preference keys in canonical state")
        return sorted(preferences, key=lambda item: item.key)

    def list_active_preferences(
        self, *, as_of: datetime | None = None
    ) -> list[Preference]:
        """Return the time-bounded projection eligible for prompt injection."""

        current = _as_utc(as_of)
        return [
            preference
            for preference in self.list_preferences()
            if preference.is_active(as_of=current)
        ]

    def set_preference(
        self,
        key: str,
        value: str,
        *,
        source: str = "explicit",
        updated_at: str | None = None,
        expires_at: str | None = None,
        source_event_id: str | None = None,
    ) -> PreferenceWrite:
        """Create or replace one preference using its stable semantic key.

        A retry is a true no-op only when value, source, expiry, and source event
        all match. Changing lifecycle or provenance is an observable revision,
        even when the user-facing value stays the same.
        Without an event ID, an explicitly newer evidence timestamp is also a
        revision. An implicit wall clock alone does not identify new evidence.
        """

        normalized_key = _preference_key(key)
        normalized_value = _clean_text(
            value, field_name="preference value", max_chars=MAX_PREFERENCE_CHARS
        )
        normalized_source = _clean_text(source, field_name="source", max_chars=100)
        normalized_updated_at = _normalize_timestamp(
            updated_at or _now_iso(), field_name="updated_at"
        )
        normalized_expires_at = (
            None
            if expires_at is None
            else _normalize_timestamp(expires_at, field_name="expires_at")
        )
        if normalized_expires_at is not None and _parse_timestamp(
            normalized_expires_at, field_name="expires_at"
        ) <= _parse_timestamp(normalized_updated_at, field_name="updated_at"):
            raise UserMemoryValidationError("expires_at must be later than updated_at")
        normalized_source_event_id = _optional_source_event_id(source_event_id)
        preferences = {item.key: item for item in self.list_preferences()}
        previous = preferences.get(normalized_key)

        # A fresh confirmation can repeat the value but must still advance
        # the stale-write boundary. Stable event IDs identify true retries;
        # callers without IDs must retain the original time when replaying.
        newer_unidentified_evidence = (
            previous is not None
            and normalized_source_event_id is None
            and updated_at is not None
            and _parse_timestamp(normalized_updated_at, field_name="updated_at")
            > _parse_timestamp(previous.updated_at, field_name="updated_at")
        )
        if previous and not newer_unidentified_evidence and (
            previous.value,
            previous.source,
            previous.expires_at,
            previous.source_event_id,
        ) == (
            normalized_value,
            normalized_source,
            normalized_expires_at,
            normalized_source_event_id,
        ):
            return PreferenceWrite(
                WriteStatus.UNCHANGED,
                normalized_key,
                previous.value,
                previous.value,
                previous.revision,
            )

        if previous and _parse_timestamp(
            normalized_updated_at, field_name="updated_at"
        ) <= _parse_timestamp(previous.updated_at, field_name="updated_at"):
            raise StalePreferenceUpdateError(
                f"preference {normalized_key} has newer canonical evidence"
            )

        revision = previous.revision + 1 if previous else 1
        preferences[normalized_key] = Preference(
            key=normalized_key,
            value=normalized_value,
            source=normalized_source,
            updated_at=normalized_updated_at,
            revision=revision,
            expires_at=normalized_expires_at,
            source_event_id=normalized_source_event_id,
        )
        self._store_preferences(preferences.values())
        return PreferenceWrite(
            WriteStatus.UPDATED if previous else WriteStatus.CREATED,
            normalized_key,
            previous.value if previous else None,
            normalized_value,
            revision,
        )

    def delete_preference(self, key: str) -> PreferenceWrite:
        """Delete by key so removal is explicit and cannot match fuzzy text."""

        normalized_key = _preference_key(key)
        preferences = {item.key: item for item in self.list_preferences()}
        previous = preferences.pop(normalized_key, None)
        if previous is None:
            return PreferenceWrite(
                WriteStatus.UNCHANGED, normalized_key, None, None, 0
            )
        self._store_preferences(preferences.values())
        return PreferenceWrite(
            WriteStatus.DELETED,
            normalized_key,
            previous.value,
            None,
            previous.revision,
        )

    def read_memory(self, *, as_of: datetime | None = None) -> str:
        """Return active preferences without deleting expired canonical state.

        Historical ``as_of`` reads are pure: they never replace the current
        MEMORY.md projection with a time-travel view.
        """

        expected = self._render_preferences(self.list_active_preferences(as_of=as_of))
        if as_of is None and self._read_text(self.memory_path) != expected:
            self._atomic_write_text(self.memory_path, expected)
        return expected

    def append_memory(self, content: str) -> PreferenceWrite:
        """Compatibility helper that still deduplicates free-form rules.

        New integrations should call ``set_preference`` with a meaningful key.
        For older callers, a content digest provides deterministic identity, so
        retrying the same write cannot grow MEMORY.md indefinitely.
        """

        value = _clean_text(
            content, field_name="preference value", max_chars=MAX_PREFERENCE_CHARS
        )
        digest = hashlib.sha256(value.casefold().encode("utf-8")).hexdigest()[:12]
        return self.set_preference(f"legacy.{digest}", value, source="legacy-explicit")

    # ── Assistant identity and prompt assembly ────────────────

    def save_identity(
        self,
        *,
        soul: str,
        assistant_identity: str,
        profile: Mapping[str, object],
    ) -> None:
        """Persist assistant identity separately from facts about the user."""

        self._atomic_write_text(self.soul_path, soul.strip() + "\n")
        self._atomic_write_text(
            self.identity_path, assistant_identity.strip() + "\n"
        )
        self.update_profile(profile)

    def load_identity(self, *, as_of: datetime | None = None) -> dict[str, str]:
        """Load readable prompt blocks without exposing canonical JSON."""

        profile = self.read_profile()
        # Existence alone does not prove freshness. Reconcile even an empty
        # canonical profile so removed fields cannot survive in an old view.
        if profile or self.profile_path.exists() or self.user_path.exists():
            self._write_profile_projection(profile)
        return {
            "soul": self._read_text(self.soul_path),
            "identity": self._read_text(self.identity_path),
            "user": self._read_text(self.user_path),
            "memory": self.read_memory(as_of=as_of),
        }

    def is_identity_established(self) -> bool:
        return bool(self.read_profile()) and self.soul_path.exists() and self.identity_path.exists()

    def get_context_for_agent(self, *, as_of: datetime | None = None) -> str:
        """Build only user-owned prompt blocks; workspace context is a caller concern."""

        if not self.is_identity_established():
            return "(user identity not yet established)"
        identity = self.load_identity(as_of=as_of)
        parts = [
            f"## Assistant values\n{identity['soul'].strip()}",
            f"## Assistant identity\n{identity['identity'].strip()}",
            f"## User profile\n{identity['user'].strip()}",
        ]
        if identity["memory"]:
            parts.append(
                "## Explicit user preferences (cross-project)\n"
                + identity["memory"].strip()
            )
        return "\n\n".join(parts)

    # ── Persistence helpers ───────────────────────────────────

    def _read_scoped_json(self, path: Path, *, default_key: str) -> dict[str, object]:
        if not path.exists():
            return {
                "schema_version": SCHEMA_VERSION,
                "user_scope": self.scope_id,
                default_key: {} if default_key == "profile" else [],
            }
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise UserMemoryValidationError(f"cannot read {path.name}: {exc}") from exc
        if not isinstance(payload, dict):
            raise UserMemoryValidationError(f"{path.name} root must be a JSON object")
        if payload.get("user_scope") != self.scope_id:
            raise UserScopeError(f"{path.name} belongs to another user scope")
        try:
            schema_version = int(payload.get("schema_version", 1))
        except (TypeError, ValueError) as exc:
            raise UserMemoryValidationError(
                f"{path.name} has an invalid schema version"
            ) from exc
        if schema_version not in SUPPORTED_SCHEMA_VERSIONS:
            raise UserMemoryValidationError(
                f"{path.name} uses unsupported schema {schema_version}"
            )
        return payload

    def _write_scoped_json(
        self, path: Path, key: str, value: object
    ) -> None:
        payload = {
            "schema_version": SCHEMA_VERSION,
            "user_scope": self.scope_id,
            key: value,
        }
        self._atomic_write_text(
            path, json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
        )

    def _store_preferences(self, preferences) -> None:
        ordered = sorted(preferences, key=lambda item: item.key)
        self._write_scoped_json(
            self.preferences_path,
            "preferences",
            [asdict(item) for item in ordered],
        )
        active = [item for item in ordered if item.is_active()]
        self._atomic_write_text(self.memory_path, self._render_preferences(active))

    def _write_profile_projection(self, profile: Mapping[str, str]) -> None:
        """Repair a derived view without rewriting an already current file."""
        labels = {
            "name": "Name",
            "call_them": "Call them",
            "pronouns": "Pronouns",
            "city": "City",
            "timezone": "Timezone",
            "notes": "Notes",
        }
        lines = ["# User", ""]
        lines.extend(
            f"{labels[key]}: {profile[key]}" for key in labels if profile.get(key)
        )
        expected = "\n".join(lines).rstrip() + "\n"
        if self._read_text(self.user_path) != expected:
            self._atomic_write_text(self.user_path, expected)

    @staticmethod
    def _render_preferences(preferences: list[Preference]) -> str:
        if not preferences:
            return ""
        lines = ["# Explicit User Preferences", ""]
        for item in preferences:
            expiry = f" (expires {item.expires_at})" if item.expires_at else ""
            lines.append(f"- `{item.key}`: {item.value}{expiry}")
        return "\n".join(lines) + "\n"

    @staticmethod
    def _read_text(path: Path) -> str:
        return path.read_text(encoding="utf-8") if path.exists() else ""

    @staticmethod
    def _atomic_write_text(path: Path, content: str) -> None:
        """Replace a complete state/projection file or leave the old file intact."""

        path.parent.mkdir(parents=True, exist_ok=True)
        temp_name: str | None = None
        try:
            with tempfile.NamedTemporaryFile(
                "w",
                encoding="utf-8",
                dir=path.parent,
                prefix=f".{path.name}.",
                suffix=".tmp",
                delete=False,
            ) as handle:
                # Track the file before any I/O can fail so finally can clean it up.
                temp_name = handle.name
                handle.write(content)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp_name, path)
        finally:
            if temp_name:
                Path(temp_name).unlink(missing_ok=True)


class BootstrapAgent:
    """First-run adapter: conversation -> explicit profile/preference writes."""

    def __init__(self, memory: UserMemory):
        self.memory = memory
        self.client = Anthropic(base_url=os.getenv("ANTHROPIC_BASE_URL"))
        self.model = os.environ["MODEL_ID"]
        self.messages: list[dict] = []
        self.completed = False

    def _build_system(self) -> str:
        return f"""You are an AI assistant doing a first-time setup conversation.

{DEFAULT_SOUL}

# Bootstrap Instructions
{self.memory.read_bootstrap()}

Use save_identity only after the user explicitly supplied the profile and
preference values. Do not infer permanent memory from conversational tone."""

    @staticmethod
    def _build_tools() -> list[dict]:
        return [
            {
                "name": "save_identity",
                "description": "Save explicit first-run identity, profile and preference data.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "user_name": {"type": "string"},
                        "call_them": {"type": "string"},
                        "city": {"type": "string"},
                        "timezone": {"type": "string"},
                        "assistant_name": {"type": "string"},
                        "emoji": {"type": "string"},
                        "preference_key": {"type": "string"},
                        "preference_value": {"type": "string"},
                    },
                    "required": [
                        "user_name",
                        "call_them",
                        "assistant_name",
                        "emoji",
                        "preference_key",
                        "preference_value",
                    ],
                },
            }
        ]

    def chat(self, user_message: str) -> str:
        self.messages.append({"role": "user", "content": user_message})
        while True:
            response = self.client.messages.create(
                model=self.model,
                system=self._build_system(),
                messages=self.messages,
                tools=self._build_tools(),
                max_tokens=4_000,
            )
            self.messages.append({"role": "assistant", "content": response.content})
            if response.stop_reason != "tool_use":
                break
            results = []
            for block in response.content:
                if block.type != "tool_use" or block.name != "save_identity":
                    continue
                self._complete(block.input)
                results.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": "Identity, profile and preference saved explicitly.",
                    }
                )
            self.messages.append({"role": "user", "content": results})
        return self._last_text()

    def _complete(self, data: Mapping[str, object]) -> None:
        assistant_name = str(data.get("assistant_name", "WorkBuddy"))
        emoji = str(data.get("emoji", "🐝"))
        assistant_identity = (
            "# Identity\n\n"
            f"Name: {assistant_name}\n"
            "Type: Desktop AI companion\n"
            f"Emoji: {emoji}\n"
        )
        profile = {
            key: data[key]
            for key in ("user_name", "call_them", "city", "timezone")
            if data.get(key)
        }
        profile["name"] = profile.pop("user_name")
        self.memory.save_identity(
            soul=DEFAULT_SOUL,
            assistant_identity=assistant_identity,
            profile=profile,
        )
        self.memory.set_preference(
            str(data["preference_key"]), str(data["preference_value"])
        )
        self.memory.delete_bootstrap()
        self.completed = True

    def _last_text(self) -> str:
        return "".join(
            block.text
            for block in self.messages[-1]["content"]
            if getattr(block, "type", None) == "text"
        )

    @property
    def is_complete(self) -> bool:
        return self.completed and not self.memory.needs_bootstrap()


class IdentityAwareAgent:
    """Agent adapter exposing explicit user-memory mutations as tools."""

    def __init__(self, memory: UserMemory, cwd: Path):
        self.memory = memory
        self.cwd = cwd
        self.client = Anthropic(base_url=os.getenv("ANTHROPIC_BASE_URL"))
        self.model = os.environ["MODEL_ID"]
        self.messages: list[dict] = []

    def _build_system(self) -> str:
        return f"""You are a coding agent at {self.cwd}.

{self.memory.get_context_for_agent()}

Only persist a profile or preference when the user explicitly asks. User memory
is cross-project; project decisions belong to workspace memory instead. Use
expires_at for explicitly temporary preferences. Provenance IDs are attached by
the harness and must never be invented from conversation text."""

    @staticmethod
    def _build_tools() -> list[dict]:
        return [
            {
                "name": "bash",
                "description": "Run a shell command in the current workspace.",
                "input_schema": {
                    "type": "object",
                    "properties": {"command": {"type": "string"}},
                    "required": ["command"],
                },
            },
            {
                "name": "update_user_profile",
                "description": "Explicitly patch stable facts about this user.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        key: {"type": "string"} for key in sorted(PROFILE_FIELDS)
                    },
                },
            },
            {
                "name": "save_user_preference",
                "description": "Create or replace one cross-project preference by key.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "key": {"type": "string"},
                        "value": {"type": "string"},
                        "expires_at": {
                            "type": "string",
                            "format": "date-time",
                            "description": (
                                "Optional timezone-aware expiry for a temporary "
                                "cross-project preference"
                            ),
                        },
                    },
                    "required": ["key", "value"],
                },
            },
        ]

    def chat(self, user_message: str) -> str:
        self.messages.append({"role": "user", "content": user_message})
        while True:
            response = self.client.messages.create(
                model=self.model,
                system=self._build_system(),
                messages=self.messages,
                tools=self._build_tools(),
                max_tokens=8_000,
            )
            self.messages.append({"role": "assistant", "content": response.content})
            if response.stop_reason != "tool_use":
                break
            results = []
            for block in response.content:
                if block.type != "tool_use":
                    continue
                output = self._dispatch_tool(block.name, block.input)
                results.append(
                    {"type": "tool_result", "tool_use_id": block.id, "content": output}
                )
            self.messages.append({"role": "user", "content": results})
        return "".join(
            block.text
            for block in self.messages[-1]["content"]
            if getattr(block, "type", None) == "text"
        )

    def _dispatch_tool(self, name: str, arguments: Mapping[str, object]) -> str:
        if name == "bash":
            return self._run_bash(str(arguments.get("command", "")))
        if name == "update_user_profile":
            result = self.memory.update_profile(arguments)
            return json.dumps(asdict(result), ensure_ascii=False)
        if name == "save_user_preference":
            result = self.memory.set_preference(
                str(arguments.get("key", "")),
                str(arguments.get("value", "")),
                source="model_tool",
                expires_at=(
                    None
                    if arguments.get("expires_at") in (None, "")
                    else str(arguments["expires_at"])
                ),
            )
            return json.dumps(asdict(result), ensure_ascii=False, default=str)
        return f"Error: unknown tool {name}"

    def _run_bash(self, command: str) -> str:
        # Tool policy is taught in s04.  This small parity guard only prevents
        # the memory lesson from accidentally demonstrating obvious host-wide
        # destructive commands when run standalone.
        dangerous = ("rm -rf /", "sudo", "shutdown", "reboot")
        if any(fragment in command for fragment in dangerous):
            return "Error: dangerous command blocked"
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
            return "Error: timeout (120s)"
        output = (result.stdout + result.stderr).strip()
        return output[:50_000] if output else "(no output)"


def main() -> None:
    user_id = os.getenv("WORKBUDDY_USER_ID", "local-user")
    memory = UserMemory(user_id=user_id)
    print("s11: User Memory — explicit profile + cross-project preferences")
    print(f"user scope: {memory.scope_id}")
    print(f"state dir:  {memory.base_dir}")

    if memory.needs_bootstrap() or not memory.is_identity_established():
        memory.create_bootstrap()
        bootstrap = BootstrapAgent(memory)
        greeting = bootstrap.chat("I am opening the app for the first time.")
        print(greeting)
        while not bootstrap.is_complete:
            try:
                message = input("bootstrap >> ").strip()
            except (EOFError, KeyboardInterrupt):
                return
            if message:
                print(bootstrap.chat(message))

    agent = IdentityAwareAgent(memory, WORKDIR)
    print("commands: /profile, /memory, /identity, /reset-id, q")
    while True:
        try:
            query = input("s11 >> ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if query.lower() in {"q", "quit", "exit"}:
            break
        if query == "/profile":
            print(json.dumps(memory.read_profile(), ensure_ascii=False, indent=2))
        elif query == "/memory":
            print(memory.read_memory() or "(no explicit preferences)")
        elif query == "/identity":
            print(memory.get_context_for_agent())
        elif query == "/reset-id":
            # The interactive reset is intentionally scoped to this user.  It
            # never removes sibling users under the shared root.
            for path in (
                memory.profile_path,
                memory.preferences_path,
                memory.memory_path,
                memory.soul_path,
                memory.identity_path,
                memory.user_path,
                memory.bootstrap_path,
            ):
                path.unlink(missing_ok=True)
            memory.create_bootstrap()
            print("identity reset for this user scope; restart to bootstrap")
            break
        elif query:
            print(agent.chat(query))


if __name__ == "__main__":
    main()
