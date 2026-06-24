"""Local append-only NDJSON journal."""

from __future__ import annotations

import hashlib
import json
import os
import socket
import time
from collections.abc import Iterator
from contextlib import contextmanager, suppress
from dataclasses import dataclass
from datetime import UTC, datetime
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Protocol

from actionlineage.domain import (
    EventEnvelope,
    deterministic_json_bytes,
    parse_event,
    serialize_event,
)
from actionlineage.domain.events import JsonObject
from actionlineage.domain.redaction import RedactionBoundary
from actionlineage.errors import ActionLineageError, safe_error_detail
from actionlineage.journal.hashing import compute_event_hash, prepare_event_for_append
from actionlineage.journal.verify import VerificationIssue, VerificationResult

try:  # pragma: no cover - Windows fallback is exercised only on Windows.
    import fcntl
except ImportError:  # pragma: no cover
    fcntl = None  # type: ignore[assignment]

PRIVATE_DIR_MODE = 0o700
PRIVATE_FILE_MODE = 0o600
JOURNAL_SOURCE_IDENTITY_VERSION = "actionlineage.dev/journal-source-identity-v1"
_PROCESS_START_IDENTITY = f"{os.getpid()}:{time.monotonic_ns()}"


class JournalError(RuntimeError):
    """Base exception for local journal failures."""


class JournalAppendError(JournalError):
    """Raised when an event cannot be appended safely."""


class JournalLockError(JournalError):
    """Raised when the local journal lock cannot be acquired."""


class JournalStoragePermissionError(JournalError):
    """Raised when evidence storage is not private enough for safe writes."""


class JournalWriter(Protocol):
    """Journal writer interface."""

    def append(self, event: EventEnvelope) -> EventEnvelope:
        """Append an event and return the persisted redacted event."""


class JournalReader(Protocol):
    """Journal reader interface."""

    def iter_events(self) -> Iterator[EventEnvelope]:
        """Yield persisted events in journal order without verification."""

    def verified_snapshot(
        self,
        *,
        expected_record_count: int | None = None,
        expected_last_event_hash: str | None = None,
    ) -> VerifiedJournalSnapshot:
        """Return events captured during same-pass journal verification."""

    def verify(
        self,
        *,
        expected_record_count: int | None = None,
        expected_last_event_hash: str | None = None,
    ) -> VerificationResult:
        """Verify journal integrity."""


@dataclass(frozen=True, slots=True)
class JournalFileMetadata:
    """Stable file metadata captured around a verified journal snapshot."""

    device: int
    inode: int
    size: int
    modified_ns: int


@dataclass(frozen=True, slots=True)
class VerifiedJournalSnapshot:
    """Immutable events captured during a single pass over verified journal bytes."""

    path: Path
    events: tuple[EventEnvelope, ...]
    verification: VerificationResult
    metadata_before: JournalFileMetadata | None = None
    metadata_after: JournalFileMetadata | None = None
    journal_sha256: str | None = None

    @property
    def ok(self) -> bool:
        """Return true when the captured bytes verified completely."""

        return self.verification.ok

    @property
    def record_count(self) -> int:
        """Number of verified records in this snapshot."""

        return self.verification.records_verified

    @property
    def terminal_hash(self) -> str | None:
        """Terminal hash of the verified journal chain."""

        return self.verification.last_event_hash

    @property
    def source_identity(self) -> str:
        """Stable identity for the verified journal bytes and terminal chain state."""

        return journal_source_identity(self)

    def as_dict(self) -> dict[str, object]:
        """Return a JSON-compatible snapshot summary without event payloads."""

        return {
            "ok": self.ok,
            "path": str(self.path),
            "record_count": self.record_count,
            "terminal_hash": self.terminal_hash,
            "journal_sha256": self.journal_sha256,
            "source_identity": self.source_identity,
            "verification": self.verification.as_dict(),
        }

    def iter_events(self) -> Iterator[EventEnvelope]:
        """Yield the immutable events captured by this verified snapshot."""

        yield from self.events


@dataclass(frozen=True, slots=True)
class LocalJournal:
    """Local append-only journal backed by newline-delimited canonical events."""

    path: Path
    redaction_policy: RedactionBoundary | None = None
    lock_timeout_seconds: float = 2.0
    lock_poll_seconds: float = 0.01

    def append(self, event: EventEnvelope) -> EventEnvelope:
        return append_event(
            self.path,
            event,
            redaction_policy=self.redaction_policy,
            lock_timeout_seconds=self.lock_timeout_seconds,
            lock_poll_seconds=self.lock_poll_seconds,
        )

    def iter_events(self) -> Iterator[EventEnvelope]:
        return iter_events(self.path)

    def verified_snapshot(
        self,
        *,
        expected_record_count: int | None = None,
        expected_last_event_hash: str | None = None,
    ) -> VerifiedJournalSnapshot:
        return verified_journal_snapshot(
            self.path,
            expected_record_count=expected_record_count,
            expected_last_event_hash=expected_last_event_hash,
            lock_timeout_seconds=self.lock_timeout_seconds,
            lock_poll_seconds=self.lock_poll_seconds,
        )

    def verify(
        self,
        *,
        expected_record_count: int | None = None,
        expected_last_event_hash: str | None = None,
    ) -> VerificationResult:
        return verify_journal(
            self.path,
            expected_record_count=expected_record_count,
            expected_last_event_hash=expected_last_event_hash,
        )


def append_event(
    path: Path,
    event: EventEnvelope,
    *,
    redaction_policy: RedactionBoundary | None = None,
    lock_timeout_seconds: float = 2.0,
    lock_poll_seconds: float = 0.01,
) -> EventEnvelope:
    """Safely append one redacted event to a local journal."""

    path = Path(path)
    try:
        _ensure_private_directory(path.parent)
    except OSError as exc:
        raise JournalAppendError("failed to prepare journal directory") from exc
    except JournalStoragePermissionError as exc:
        raise JournalAppendError(safe_error_detail(exc)) from exc

    with _journal_lock(
        path.with_suffix(f"{path.suffix}.lock"),
        mode="exclusive",
        operation="append",
        timeout_seconds=lock_timeout_seconds,
        poll_seconds=lock_poll_seconds,
    ):
        try:
            snapshot = verified_journal_snapshot(path, lock=False)
        except OSError as exc:
            raise JournalAppendError("failed to verify existing journal before append") from exc
        if not snapshot.ok:
            raise JournalAppendError("cannot append to a journal that fails verification")

        expected_sequence = snapshot.record_count
        if event.causality.sequence != expected_sequence:
            raise JournalAppendError(
                f"event sequence {event.causality.sequence} does not match next journal "
                f"sequence {expected_sequence}"
            )

        redacted_event, canonical_bytes = prepare_event_for_append(
            event,
            previous_event_hash=snapshot.terminal_hash,
            redaction_policy=redaction_policy,
        )
        try:
            _append_line(path, canonical_bytes)
        except OSError as exc:
            raise JournalAppendError("failed to append event to journal") from exc
        return redacted_event


def iter_events(path: Path) -> Iterator[EventEnvelope]:
    """Unsafely yield events from a local journal without integrity verification.

    Security-sensitive consumers must use `verified_journal_snapshot()` or
    `LocalJournal.verified_snapshot()` instead.
    """

    yield from _unsafe_iter_events(path)


def _unsafe_iter_events(path: Path) -> Iterator[EventEnvelope]:
    """Yield parsed journal events without hash-chain verification."""

    path = Path(path)
    if not path.exists():
        return

    with path.open("rb") as journal_file:
        for raw_line in journal_file:
            line = raw_line.rstrip(b"\n")
            if not line:
                continue
            yield parse_event(line)


def verify_journal(
    path: Path,
    *,
    expected_record_count: int | None = None,
    expected_last_event_hash: str | None = None,
) -> VerificationResult:
    """Verify local journal hash-chain integrity."""

    return verified_journal_snapshot(
        path,
        expected_record_count=expected_record_count,
        expected_last_event_hash=expected_last_event_hash,
    ).verification


def journal_source_identity(snapshot: VerifiedJournalSnapshot) -> str:
    """Return a path-independent identity for one verified journal snapshot.

    The identity is local tamper-evidence metadata, not an external trust root.
    It binds the verified byte digest, verified record count, and terminal event
    hash into a namespaced digest so projections can follow moved journals while
    still failing closed for changed journal contents.
    """

    if not snapshot.ok:
        raise ValueError("cannot compute source identity for an invalid journal snapshot")
    preimage: JsonObject = {
        "journal_sha256": snapshot.journal_sha256,
        "record_count": snapshot.record_count,
        "terminal_hash": snapshot.terminal_hash,
        "version": JOURNAL_SOURCE_IDENTITY_VERSION,
    }
    digest = hashlib.sha256(deterministic_json_bytes(preimage)).hexdigest()
    return f"{JOURNAL_SOURCE_IDENTITY_VERSION}:sha256:{digest}"


def verified_journal_snapshot(
    path: Path,
    *,
    expected_record_count: int | None = None,
    expected_last_event_hash: str | None = None,
    lock_timeout_seconds: float = 2.0,
    lock_poll_seconds: float = 0.01,
    lock: bool = True,
) -> VerifiedJournalSnapshot:
    """Read, verify, and capture immutable journal events in one pass."""

    path = Path(path)
    if lock:
        with _journal_lock(
            path.with_suffix(f"{path.suffix}.lock"),
            mode="shared",
            operation="snapshot",
            timeout_seconds=lock_timeout_seconds,
            poll_seconds=lock_poll_seconds,
        ):
            return verified_journal_snapshot(
                path,
                expected_record_count=expected_record_count,
                expected_last_event_hash=expected_last_event_hash,
                lock_timeout_seconds=lock_timeout_seconds,
                lock_poll_seconds=lock_poll_seconds,
                lock=False,
            )

    issues: list[VerificationIssue] = []
    expected_previous_hash: str | None = None
    last_event_hash: str | None = None
    records_verified = 0
    events: list[EventEnvelope] = []
    metadata_before: JournalFileMetadata | None = None
    metadata_after: JournalFileMetadata | None = None
    journal_digest: hashlib._Hash | None = None

    if path.exists():
        fd = os.open(path, os.O_RDONLY | getattr(os, "O_CLOEXEC", 0))
        try:
            metadata_before = _metadata_from_stat(os.fstat(fd))
            journal_digest = hashlib.sha256()
            with os.fdopen(fd, "rb") as journal_file:
                fd = -1
                for index, raw_line in enumerate(journal_file):
                    journal_digest.update(raw_line)
                    record_number = index + 1
                    if not raw_line.endswith(b"\n"):
                        issues.append(
                            VerificationIssue(
                                record_number=record_number,
                                code="truncated_record",
                                message="journal record is missing its newline terminator",
                            )
                        )
                        break

                    line = raw_line.rstrip(b"\n")
                    if not line:
                        issues.append(
                            VerificationIssue(
                                record_number=record_number,
                                code="empty_record",
                                message="journal record is empty",
                            )
                        )
                        break

                    try:
                        event = parse_event(line)
                    except (ActionLineageError, ValueError):
                        issues.append(
                            VerificationIssue(
                                record_number=record_number,
                                code="parse_error",
                                message="journal record is not a valid event",
                            )
                        )
                        break

                    expected_line = serialize_event(event) + b"\n"
                    if raw_line != expected_line:
                        issues.append(
                            VerificationIssue(
                                record_number=record_number,
                                event_id=event.event_id,
                                code="noncanonical_record",
                                message=(
                                    "journal record bytes do not exactly match canonical "
                                    "serialization"
                                ),
                                expected="canonical_event_line",
                                actual="journal_record_line",
                            )
                        )
                        break

                    if event.causality.sequence != index:
                        issues.append(
                            VerificationIssue(
                                record_number=record_number,
                                event_id=event.event_id,
                                code="sequence_mismatch",
                                message="event sequence does not match journal record order",
                                expected=index,
                                actual=event.causality.sequence,
                            )
                        )
                        break

                    if event.integrity.previous_event_hash != expected_previous_hash:
                        issues.append(
                            VerificationIssue(
                                record_number=record_number,
                                event_id=event.event_id,
                                code="previous_hash_mismatch",
                                message="previous_event_hash does not match prior record hash",
                                expected=expected_previous_hash,
                                actual=event.integrity.previous_event_hash,
                            )
                        )
                        break

                    if event.integrity.event_hash is None:
                        issues.append(
                            VerificationIssue(
                                record_number=record_number,
                                event_id=event.event_id,
                                code="event_hash_missing",
                                message="event_hash is required for journal verification",
                            )
                        )
                        break

                    computed_hash = compute_event_hash(event)
                    if event.integrity.event_hash != computed_hash:
                        issues.append(
                            VerificationIssue(
                                record_number=record_number,
                                event_id=event.event_id,
                                code="event_hash_mismatch",
                                message="event_hash does not match canonical event bytes",
                                expected=computed_hash,
                                actual=event.integrity.event_hash,
                            )
                        )
                        break

                    events.append(event)
                    records_verified += 1
                    last_event_hash = event.integrity.event_hash
                    expected_previous_hash = event.integrity.event_hash
                metadata_after = _metadata_from_stat(os.fstat(journal_file.fileno()))
        finally:
            if fd >= 0:
                os.close(fd)

    if (
        metadata_before is not None
        and metadata_after is not None
        and metadata_before != metadata_after
    ):
        issues.append(
            VerificationIssue(
                record_number=records_verified,
                code="journal_changed_during_read",
                message="journal file metadata changed during snapshot capture",
            )
        )

    if expected_record_count is not None and records_verified != expected_record_count:
        issues.append(
            VerificationIssue(
                record_number=records_verified,
                code="expected_record_count_mismatch",
                message="verified record count does not match expected trusted count",
                expected=expected_record_count,
                actual=records_verified,
            )
        )

    if expected_last_event_hash is not None and last_event_hash != expected_last_event_hash:
        issues.append(
            VerificationIssue(
                record_number=records_verified,
                code="expected_last_hash_mismatch",
                message="last event hash does not match expected trusted hash",
                expected=expected_last_event_hash,
                actual=last_event_hash,
            )
        )

    verification = VerificationResult(
        ok=not issues,
        records_verified=records_verified,
        last_event_hash=last_event_hash,
        issues=tuple(issues),
    )
    return VerifiedJournalSnapshot(
        path=path,
        events=tuple(events),
        verification=verification,
        metadata_before=metadata_before,
        metadata_after=metadata_after,
        journal_sha256=(
            f"sha256:{journal_digest.hexdigest()}" if verification.ok and journal_digest else None
        ),
    )


def _append_line(path: Path, canonical_bytes: bytes) -> None:
    fd = os.open(
        path,
        os.O_WRONLY | os.O_APPEND | os.O_CREAT | getattr(os, "O_CLOEXEC", 0),
        PRIVATE_FILE_MODE,
    )
    try:
        if os.name == "posix" and (os.fstat(fd).st_mode & 0o077):
            os.fchmod(fd, PRIVATE_FILE_MODE)
        _raise_if_insecure_file(path, fd)
        with os.fdopen(fd, "ab") as journal_file:
            fd = -1
            journal_file.write(canonical_bytes)
            journal_file.write(b"\n")
            journal_file.flush()
            os.fsync(journal_file.fileno())
    finally:
        if fd >= 0:
            os.close(fd)


def _ensure_private_directory(path: Path) -> None:
    path.mkdir(mode=PRIVATE_DIR_MODE, parents=True, exist_ok=True)
    if os.name == "posix":
        mode = path.stat().st_mode & 0o777
        if mode & 0o077:
            raise JournalStoragePermissionError(
                f"journal directory is not private: {path}; expected mode 0700 or stricter"
            )


def _raise_if_insecure_file(path: Path, fd: int) -> None:
    if os.name != "posix":
        return
    mode = os.fstat(fd).st_mode & 0o777
    if mode & 0o077:
        raise JournalStoragePermissionError(
            f"journal file is not private: {path}; expected mode 0600 or stricter"
        )


def _metadata_from_stat(value: os.stat_result) -> JournalFileMetadata:
    return JournalFileMetadata(
        device=value.st_dev,
        inode=value.st_ino,
        size=value.st_size,
        modified_ns=value.st_mtime_ns,
    )


def _read_lock_metadata(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")[:800]
    except OSError:
        return "unavailable"


def _lock_metadata(operation: str) -> bytes:
    try:
        app_version = version("actionlineage")
    except PackageNotFoundError:
        app_version = "0+local"
    payload = {
        "schema_version": "actionlineage.dev/journal-lock-metadata-v1",
        "pid": os.getpid(),
        "hostname": socket.gethostname(),
        "process_start_identity": _PROCESS_START_IDENTITY,
        "acquired_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "application_version": app_version,
        "operation": operation,
    }
    return (json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def _lock_file(path: Path, *, mode: str, operation: str) -> int:
    fd = os.open(
        path,
        os.O_RDWR | os.O_CREAT | getattr(os, "O_CLOEXEC", 0),
        PRIVATE_FILE_MODE,
    )
    try:
        if os.name == "posix" and (os.fstat(fd).st_mode & 0o077):
            os.fchmod(fd, PRIVATE_FILE_MODE)
        _raise_if_insecure_file(path, fd)
        if fcntl is not None:
            flag = fcntl.LOCK_EX if mode == "exclusive" else fcntl.LOCK_SH
            fcntl.flock(fd, flag | fcntl.LOCK_NB)
        if mode == "exclusive":
            os.ftruncate(fd, 0)
            os.write(fd, _lock_metadata(operation))
            os.fsync(fd)
        return fd
    except Exception:
        os.close(fd)
        raise


@contextmanager
def _journal_lock(
    path: Path,
    *,
    mode: str,
    operation: str,
    timeout_seconds: float,
    poll_seconds: float,
) -> Iterator[None]:
    deadline = time.monotonic() + timeout_seconds
    path.parent.mkdir(mode=PRIVATE_DIR_MODE, parents=True, exist_ok=True)
    while True:
        try:
            fd = _lock_file(path, mode=mode, operation=operation)
        except BlockingIOError:
            if time.monotonic() >= deadline:
                metadata = _read_lock_metadata(path)
                raise JournalLockError(
                    f"timed out acquiring journal lock: {path}; owner={metadata}"
                ) from None
            time.sleep(poll_seconds)
            continue
        else:
            break

    try:
        yield
    finally:
        if mode == "exclusive":
            with suppress(OSError):
                os.ftruncate(fd, 0)
                os.fsync(fd)
        if fcntl is not None:
            with suppress(OSError):
                fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)
