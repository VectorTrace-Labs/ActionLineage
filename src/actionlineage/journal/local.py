"""Local append-only NDJSON journal."""

from __future__ import annotations

import os
import time
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from actionlineage.domain import EventEnvelope, parse_event
from actionlineage.domain.redaction import RedactionBoundary
from actionlineage.errors import ActionLineageError
from actionlineage.journal.hashing import compute_event_hash, prepare_event_for_append
from actionlineage.journal.verify import VerificationIssue, VerificationResult


class JournalError(RuntimeError):
    """Base exception for local journal failures."""


class JournalAppendError(JournalError):
    """Raised when an event cannot be appended safely."""


class JournalLockError(JournalError):
    """Raised when the local journal lock cannot be acquired."""


class JournalWriter(Protocol):
    """Journal writer interface."""

    def append(self, event: EventEnvelope) -> EventEnvelope:
        """Append an event and return the persisted redacted event."""


class JournalReader(Protocol):
    """Journal reader interface."""

    def iter_events(self) -> Iterator[EventEnvelope]:
        """Yield persisted events in journal order."""

    def verify(
        self,
        *,
        expected_record_count: int | None = None,
        expected_last_event_hash: str | None = None,
    ) -> VerificationResult:
        """Verify journal integrity."""


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
        path.parent.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise JournalAppendError("failed to prepare journal directory") from exc

    with _journal_lock(
        path.with_suffix(f"{path.suffix}.lock"),
        timeout_seconds=lock_timeout_seconds,
        poll_seconds=lock_poll_seconds,
    ):
        try:
            verification = verify_journal(path)
        except OSError as exc:
            raise JournalAppendError("failed to verify existing journal before append") from exc
        if not verification.ok:
            raise JournalAppendError("cannot append to a journal that fails verification")

        expected_sequence = verification.records_verified
        if event.causality.sequence != expected_sequence:
            raise JournalAppendError(
                f"event sequence {event.causality.sequence} does not match next journal "
                f"sequence {expected_sequence}"
            )

        redacted_event, canonical_bytes = prepare_event_for_append(
            event,
            previous_event_hash=verification.last_event_hash,
            redaction_policy=redaction_policy,
        )
        try:
            _append_line(path, canonical_bytes)
        except OSError as exc:
            raise JournalAppendError("failed to append event to journal") from exc
        return redacted_event


def iter_events(path: Path) -> Iterator[EventEnvelope]:
    """Yield events from a local journal."""

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

    path = Path(path)
    issues: list[VerificationIssue] = []
    expected_previous_hash: str | None = None
    last_event_hash: str | None = None
    records_verified = 0

    if path.exists():
        with path.open("rb") as journal_file:
            for index, raw_line in enumerate(journal_file):
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

                records_verified += 1
                last_event_hash = event.integrity.event_hash
                expected_previous_hash = event.integrity.event_hash

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

    return VerificationResult(
        ok=not issues,
        records_verified=records_verified,
        last_event_hash=last_event_hash,
        issues=tuple(issues),
    )


def _append_line(path: Path, canonical_bytes: bytes) -> None:
    with path.open("ab") as journal_file:
        journal_file.write(canonical_bytes)
        journal_file.write(b"\n")
        journal_file.flush()
        os.fsync(journal_file.fileno())


@dataclass(frozen=True, slots=True)
class _JournalLock:
    path: Path
    timeout_seconds: float
    poll_seconds: float

    def __enter__(self) -> _JournalLock:
        deadline = time.monotonic() + self.timeout_seconds
        while True:
            try:
                fd = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            except FileExistsError:
                if time.monotonic() >= deadline:
                    raise JournalLockError(
                        f"timed out acquiring journal lock: {self.path}"
                    ) from None
                time.sleep(self.poll_seconds)
                continue
            else:
                os.close(fd)
                return self

    def __exit__(self, exc_type: object, exc_value: object, traceback: object) -> None:
        try:
            self.path.unlink()
        except FileNotFoundError:
            return


def _journal_lock(path: Path, *, timeout_seconds: float, poll_seconds: float) -> _JournalLock:
    return _JournalLock(path=path, timeout_seconds=timeout_seconds, poll_seconds=poll_seconds)
