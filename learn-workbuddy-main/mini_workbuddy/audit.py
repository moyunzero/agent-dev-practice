from __future__ import annotations

import hashlib
import json
import os
import stat
import threading
import time
import uuid
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Iterator

from .config import HarnessConfig


if os.name == "nt":  # pragma: no cover - exercised only on Windows
    import msvcrt
else:  # pragma: no cover - platform branch is covered on POSIX CI
    import fcntl


GENESIS_HASH = "0" * 64
_NOFOLLOW = getattr(os, "O_NOFOLLOW", 0)
_PROCESS_LOCKS: dict[Path, threading.Lock] = {}
_PROCESS_LOCKS_GUARD = threading.Lock()


class AuditCorruptionError(RuntimeError):
    """Raised when an existing audit chain cannot be extended safely."""


@dataclass(frozen=True)
class AuditEntry:
    index: int
    timestamp: int
    action: str
    data: dict[str, Any]
    prev_hash: str
    hash: str


def _process_lock(path: Path) -> threading.Lock:
    """Return one lock for every audit path used by this Python process.

    ``flock`` locks are process-scoped on POSIX, so two ``AuditLog`` objects
    in the threaded HTTP server also need a Python lock to exclude each other.
    """

    key = path.resolve()
    with _PROCESS_LOCKS_GUARD:
        return _PROCESS_LOCKS.setdefault(key, threading.Lock())


class AuditLog:
    """Append-only hash chain for high-risk harness events.

    Appends are serialized across threads and cooperating processes. The
    chain and its anchor are checked while the lock is held, so a writer never
    extends a tip that it has already proved to be corrupt or stale.
    """

    def __init__(self, config: HarnessConfig) -> None:
        self.config = config
        self.config.ensure_dirs()
        self.path = self.config.audit_dir / "audit.jsonl"
        # Anchor file: records (count, head hash) of the chain tip.
        # A hash chain alone detects *modification* of past entries, but NOT
        # *truncation*: any prefix of a valid chain is itself a valid chain.
        # Anchoring the tip out-of-band closes that gap for the teaching harness.
        self.head_path = self.config.audit_dir / "audit.head"
        self.lock_path = self.config.audit_dir / "audit.lock"
        self._thread_lock = _process_lock(self.lock_path)

    def append(self, action: str, data: dict[str, Any]) -> AuditEntry:
        """Validate and extend the current chain as one serialized operation."""

        with self._exclusive_lock():
            try:
                entries = self._read_entries_unlocked()
                prev_hash = self._validated_tip_unlocked(entries)
            except AuditCorruptionError:
                raise
            except (
                OSError,
                UnicodeDecodeError,
                json.JSONDecodeError,
                TypeError,
            ) as exc:
                raise AuditCorruptionError(
                    "audit chain is unreadable; refusing to append"
                ) from exc

            index = len(entries) + 1
            timestamp = int(time.time() * 1000)
            digest = self._hash_payload(index, timestamp, action, data, prev_hash)
            entry = AuditEntry(
                index=index,
                timestamp=timestamp,
                action=action,
                data=data,
                prev_hash=prev_hash,
                hash=digest,
            )

            # Persist the JSONL record before publishing its new chain tip. A
            # crash between these two fsync boundaries leaves a detectable
            # anchor mismatch; the next append fails closed instead of forking.
            self._append_entry_unlocked(entry)
            self._replace_head_unlocked(index, digest)
            return entry

    def recover_interrupted_append(self) -> bool:
        """Publish one complete entry left behind by an interrupted append.

        The recovery is intentionally narrow.  It advances ``audit.head`` only
        when the complete hash chain is valid, the old anchor still identifies
        the penultimate entry, and exactly one durable JSONL entry follows it.
        Every other mismatch remains a fail-closed corruption error.

        Returns ``True`` when the anchor was advanced and ``False`` when the
        chain was already consistent or no legacy anchor exists.
        """

        with self._exclusive_lock():
            try:
                entries = self._read_entries_unlocked()
                tip_hash = self._validated_chain_tip_unlocked(entries)
                anchor = self._read_anchor_unlocked()
            except AuditCorruptionError:
                raise
            except (OSError, UnicodeDecodeError, json.JSONDecodeError, TypeError) as exc:
                raise AuditCorruptionError(
                    "audit chain is unreadable; refusing recovery"
                ) from exc

            # A missing anchor can be a legitimate legacy log.  Without a
            # previously published tip there is no evidence that distinguishes
            # an interrupted append from an arbitrary complete chain.
            if anchor is None:
                return False

            anchor_count, anchor_hash = anchor
            if anchor_count == len(entries) and anchor_hash == tip_hash:
                return False

            if anchor_count != len(entries) - 1:
                raise AuditCorruptionError(
                    "audit recovery requires exactly one unanchored entry"
                )
            anchored_hash = (
                entries[anchor_count - 1].hash if anchor_count else GENESIS_HASH
            )
            if anchor_hash != anchored_hash:
                raise AuditCorruptionError(
                    "audit head anchor does not match the penultimate entry"
                )

            self._replace_head_unlocked(len(entries), tip_hash)
            return True

    def read_entries(self) -> list[AuditEntry]:
        # Readers share the writer boundary so they cannot observe the brief
        # interval between the durable JSONL append and head replacement.
        with self._exclusive_lock():
            return self._read_entries_unlocked()

    def verify(self) -> bool:
        try:
            with self._exclusive_lock():
                entries = self._read_entries_unlocked()
                self._validated_tip_unlocked(entries)
            return True
        except (
            AuditCorruptionError,
            OSError,
            UnicodeDecodeError,
            json.JSONDecodeError,
            TypeError,
        ):
            return False

    @contextmanager
    def _exclusive_lock(self) -> Iterator[None]:
        """Serialize the read-validate-append-anchor critical section."""

        with self._thread_lock:
            fd = os.open(
                self.lock_path,
                os.O_CREAT | os.O_RDWR | _NOFOLLOW,
                0o600,
            )
            try:
                self._require_regular_file(fd, self.lock_path)
                self._lock_fd(fd)
                try:
                    yield
                finally:
                    self._unlock_fd(fd)
            finally:
                os.close(fd)

    def _read_entries_unlocked(self) -> list[AuditEntry]:
        if not self.path.exists():
            return []
        entries: list[AuditEntry] = []
        for line in self._read_lines_unlocked():
            if not line.strip():
                continue
            data = json.loads(line)
            entries.append(AuditEntry(**data))
        return entries

    def _validated_tip_unlocked(self, entries: list[AuditEntry]) -> str:
        """Return the verified chain tip or reject the existing state."""

        prev_hash = self._validated_chain_tip_unlocked(entries)
        anchor = self._read_anchor_unlocked()
        if anchor is None:
            # Legacy logs written before anchoring existed remain readable. The
            # next successful append upgrades them by creating an anchor.
            return prev_hash

        anchor_count, anchor_hash = anchor
        if anchor_count != len(entries) or anchor_hash != prev_hash:
            raise AuditCorruptionError(
                "audit head anchor does not match the chain tip"
            )
        return prev_hash

    def _validated_chain_tip_unlocked(self, entries: list[AuditEntry]) -> str:
        """Validate JSONL linkage and hashes without consulting the anchor."""

        prev_hash = GENESIS_HASH
        for expected_index, entry in enumerate(entries, start=1):
            if entry.index != expected_index or entry.prev_hash != prev_hash:
                raise AuditCorruptionError(
                    f"audit chain linkage is invalid at entry {expected_index}"
                )
            digest = self._hash_payload(
                entry.index,
                entry.timestamp,
                entry.action,
                entry.data,
                entry.prev_hash,
            )
            if digest != entry.hash:
                raise AuditCorruptionError(
                    f"audit entry hash is invalid at entry {expected_index}"
                )
            prev_hash = entry.hash
        return prev_hash

    def _read_anchor_unlocked(self) -> tuple[int, str] | None:
        if not self.head_path.exists():
            return None

        anchor = json.loads(self._read_text_file(self.head_path))
        if not isinstance(anchor, dict):
            raise AuditCorruptionError("audit head anchor is not an object")
        count = anchor.get("count")
        head = anchor.get("head")
        if type(count) is not int or count < 0:
            raise AuditCorruptionError("audit head count is invalid")
        if (
            not isinstance(head, str)
            or len(head) != len(GENESIS_HASH)
            or any(character not in "0123456789abcdef" for character in head)
        ):
            raise AuditCorruptionError("audit head hash is invalid")
        return count, head

    def _append_entry_unlocked(self, entry: AuditEntry) -> None:
        payload = (
            json.dumps(entry.__dict__, ensure_ascii=False, sort_keys=True) + "\n"
        ).encode("utf-8")
        fd = os.open(
            self.path,
            os.O_APPEND | os.O_CREAT | os.O_WRONLY | _NOFOLLOW,
            0o600,
        )
        try:
            self._require_regular_file(fd, self.path)
            self._write_all(fd, payload)
            os.fsync(fd)
        finally:
            os.close(fd)

    def _replace_head_unlocked(self, count: int, head: str) -> None:
        payload = (
            json.dumps({"count": count, "head": head}, sort_keys=True) + "\n"
        ).encode("utf-8")
        temporary = self.head_path.with_name(
            f".{self.head_path.name}.{os.getpid()}.{uuid.uuid4().hex}.tmp"
        )
        fd = os.open(
            temporary,
            os.O_CREAT | os.O_EXCL | os.O_WRONLY | _NOFOLLOW,
            0o600,
        )
        try:
            try:
                self._require_regular_file(fd, temporary)
                self._write_all(fd, payload)
                os.fsync(fd)
            finally:
                os.close(fd)
            os.replace(temporary, self.head_path)
            self._fsync_directory(self.config.audit_dir)
        finally:
            # Only a failure before os.replace leaves the temporary file.
            try:
                temporary.unlink()
            except FileNotFoundError:
                pass

    def _read_lines_unlocked(self) -> Iterable[str]:
        return self._read_text_file(self.path).splitlines()

    @staticmethod
    def _read_text_file(path: Path) -> str:
        fd = os.open(path, os.O_RDONLY | _NOFOLLOW)
        try:
            AuditLog._require_regular_file(fd, path)
            chunks: list[bytes] = []
            while chunk := os.read(fd, 64 * 1024):
                chunks.append(chunk)
            return b"".join(chunks).decode("utf-8")
        finally:
            os.close(fd)

    @staticmethod
    def _write_all(fd: int, payload: bytes) -> None:
        view = memoryview(payload)
        while view:
            written = os.write(fd, view)
            if written == 0:
                raise OSError("short write while persisting audit state")
            view = view[written:]

    @staticmethod
    def _require_regular_file(fd: int, path: Path) -> None:
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            raise OSError(f"audit path is not a regular file: {path}")

    @staticmethod
    def _lock_fd(fd: int) -> None:
        if os.name == "nt":  # pragma: no cover - exercised only on Windows
            if os.fstat(fd).st_size == 0:
                os.write(fd, b"\0")
                os.fsync(fd)
            os.lseek(fd, 0, os.SEEK_SET)
            msvcrt.locking(fd, msvcrt.LK_LOCK, 1)
        else:
            fcntl.flock(fd, fcntl.LOCK_EX)

    @staticmethod
    def _unlock_fd(fd: int) -> None:
        if os.name == "nt":  # pragma: no cover - exercised only on Windows
            os.lseek(fd, 0, os.SEEK_SET)
            msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
        else:
            fcntl.flock(fd, fcntl.LOCK_UN)

    @staticmethod
    def _fsync_directory(path: Path) -> None:
        if os.name == "nt":  # pragma: no cover - not supported by Windows
            return
        fd = os.open(path, os.O_RDONLY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)

    def _hash_payload(
        self,
        index: int,
        timestamp: int,
        action: str,
        data: dict[str, Any],
        prev_hash: str,
    ) -> str:
        payload = {
            "index": index,
            "timestamp": timestamp,
            "action": action,
            "data": data,
            "prev_hash": prev_hash,
        }
        raw = json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()
