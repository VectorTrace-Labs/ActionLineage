"""Trusted journal anchors, manifests, and recovery helpers."""

from __future__ import annotations

import hashlib
import hmac
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal, cast

from actionlineage.domain import deterministic_json_bytes
from actionlineage.domain.events import JsonObject
from actionlineage.journal.local import verify_journal
from actionlineage.journal.verify import VerificationIssue, VerificationResult

JOURNAL_ANCHOR_VERSION = "actionlineage.dev/journal-anchor-v1"
JOURNAL_ANCHOR_LOG_VERSION = "actionlineage.dev/journal-anchor-log-v1"
JOURNAL_SEGMENT_MANIFEST_VERSION = "actionlineage.dev/journal-segment-manifest-v1"
ANCHOR_SIGNATURE_ALGORITHM = "hmac-sha256"

type AnchorIssueCode = Literal[
    "journal_verification_failed",
    "signature_key_missing",
    "signature_mismatch",
]
type AnchorLogIssueCode = Literal[
    "empty_record",
    "parse_error",
    "sequence_mismatch",
    "previous_hash_mismatch",
    "entry_hash_missing",
    "entry_hash_mismatch",
    "expected_record_count_mismatch",
    "expected_last_hash_mismatch",
]


class JournalAnchorError(RuntimeError):
    """Raised when an anchor or manifest cannot be created safely."""


@dataclass(frozen=True, slots=True)
class JournalAnchor:
    """Trusted local root for detecting journal truncation and full rewrites."""

    journal_path: str
    record_count: int
    last_event_hash: str | None
    created_at: datetime
    anchor_version: str = JOURNAL_ANCHOR_VERSION
    signature_algorithm: str | None = None
    signature: str | None = None

    def as_dict(self) -> JsonObject:
        """Return a JSON-compatible anchor object."""

        result: JsonObject = {
            "anchor_version": self.anchor_version,
            "created_at": _timestamp(self.created_at),
            "journal_path": self.journal_path,
            "last_event_hash": self.last_event_hash,
            "record_count": self.record_count,
            "signature": self.signature,
            "signature_algorithm": self.signature_algorithm,
        }
        return result

    def unsigned_dict(self) -> JsonObject:
        """Return the signature input object."""

        result = self.as_dict()
        result["signature"] = None
        return result


@dataclass(frozen=True, slots=True)
class JournalSegmentManifest:
    """Manifest for one journal segment.

    A single-segment manifest is enough for local alpha evidence. Multi-segment
    archives can use the same shape for each segment without changing journal
    event bytes.
    """

    segment_path: str
    segment_index: int
    anchor: JournalAnchor
    manifest_version: str = JOURNAL_SEGMENT_MANIFEST_VERSION

    def as_dict(self) -> JsonObject:
        """Return a JSON-compatible segment manifest."""

        return {
            "anchor": self.anchor.as_dict(),
            "manifest_version": self.manifest_version,
            "segment_index": self.segment_index,
            "segment_path": self.segment_path,
        }


@dataclass(frozen=True, slots=True)
class JournalAnchorLogEntry:
    """One append-only record in a local anchor log."""

    sequence: int
    anchor: JournalAnchor
    previous_entry_hash: str | None
    entry_hash: str | None
    created_at: datetime
    log_version: str = JOURNAL_ANCHOR_LOG_VERSION

    def as_dict(self) -> JsonObject:
        """Return a JSON-compatible anchor log entry."""

        return {
            "anchor": self.anchor.as_dict(),
            "created_at": _timestamp(self.created_at),
            "entry_hash": self.entry_hash,
            "log_version": self.log_version,
            "previous_entry_hash": self.previous_entry_hash,
            "sequence": self.sequence,
        }

    def hash_input_dict(self) -> JsonObject:
        """Return the deterministic hash input for this entry."""

        result = self.as_dict()
        result["entry_hash"] = None
        return result


@dataclass(frozen=True, slots=True)
class AnchorVerificationIssue:
    """One anchor verification issue."""

    code: AnchorIssueCode
    message: str

    def as_dict(self) -> dict[str, str]:
        """Return a JSON-compatible issue."""

        return {"code": self.code, "message": self.message}


@dataclass(frozen=True, slots=True)
class AnchorLogVerificationIssue:
    """One local anchor-log verification issue."""

    record_number: int
    code: AnchorLogIssueCode
    message: str
    expected: str | int | None = None
    actual: str | int | None = None

    def as_dict(self) -> dict[str, object]:
        """Return a JSON-compatible issue."""

        return {
            "actual": self.actual,
            "code": self.code,
            "expected": self.expected,
            "message": self.message,
            "record_number": self.record_number,
        }


@dataclass(frozen=True, slots=True)
class AnchorVerificationResult:
    """Result of verifying a journal against an anchor."""

    ok: bool
    journal_verification: VerificationResult
    issues: tuple[AnchorVerificationIssue, ...] = ()

    def as_dict(self) -> dict[str, object]:
        """Return a JSON-compatible result object."""

        return {
            "ok": self.ok,
            "journal_verification": self.journal_verification.as_dict(),
            "issues": [issue.as_dict() for issue in self.issues],
        }


@dataclass(frozen=True, slots=True)
class AnchorLogVerificationResult:
    """Result of verifying a local append-only anchor log."""

    ok: bool
    records_verified: int
    last_entry_hash: str | None
    issues: tuple[AnchorLogVerificationIssue, ...] = ()

    def as_dict(self) -> dict[str, object]:
        """Return a JSON-compatible result object."""

        return {
            "ok": self.ok,
            "records_verified": self.records_verified,
            "last_entry_hash": self.last_entry_hash,
            "issues": [issue.as_dict() for issue in self.issues],
        }


@dataclass(frozen=True, slots=True)
class VerifiedPrefixExport:
    """Result of exporting a verified journal prefix."""

    source_path: Path
    output_path: Path
    records_exported: int
    verification: VerificationResult

    def as_dict(self) -> dict[str, object]:
        """Return a JSON-compatible result object."""

        return {
            "ok": True,
            "source_path": str(self.source_path),
            "output_path": str(self.output_path),
            "records_exported": self.records_exported,
            "verification": self.verification.as_dict(),
        }


def create_journal_anchor(
    journal_path: Path,
    *,
    signing_key: bytes | None = None,
    created_at: datetime | None = None,
) -> JournalAnchor:
    """Create a trusted anchor from the current verified journal state."""

    verification = verify_journal(journal_path)
    if not verification.ok:
        raise JournalAnchorError("cannot anchor a journal that fails verification")

    anchor = JournalAnchor(
        journal_path=str(journal_path),
        record_count=verification.records_verified,
        last_event_hash=verification.last_event_hash,
        created_at=created_at or datetime.now(UTC),
    )
    if signing_key is None:
        return anchor

    signing_anchor = JournalAnchor(
        journal_path=anchor.journal_path,
        record_count=anchor.record_count,
        last_event_hash=anchor.last_event_hash,
        created_at=anchor.created_at,
        signature_algorithm=ANCHOR_SIGNATURE_ALGORITHM,
    )
    signature = _anchor_signature(signing_anchor, signing_key)
    return JournalAnchor(
        journal_path=anchor.journal_path,
        record_count=anchor.record_count,
        last_event_hash=anchor.last_event_hash,
        created_at=anchor.created_at,
        signature_algorithm=ANCHOR_SIGNATURE_ALGORITHM,
        signature=signature,
    )


def write_journal_anchor(anchor: JournalAnchor, anchor_path: Path) -> None:
    """Write an anchor as deterministic JSON."""

    anchor_path.parent.mkdir(parents=True, exist_ok=True)
    anchor_path.write_bytes(deterministic_json_bytes(anchor.as_dict()) + b"\n")


def append_journal_anchor_log(
    log_path: Path,
    anchor: JournalAnchor,
    *,
    created_at: datetime | None = None,
) -> JournalAnchorLogEntry:
    """Append an anchor to a local transparency-style log.

    The log is a sidecar trusted-root artifact. It does not alter canonical
    journal bytes and is still local evidence, not a public transparency log.
    """

    verification = verify_journal_anchor_log(log_path)
    if not verification.ok:
        raise JournalAnchorError("cannot append to an anchor log that fails verification")

    unsigned_entry = JournalAnchorLogEntry(
        sequence=verification.records_verified + 1,
        anchor=anchor,
        previous_entry_hash=verification.last_entry_hash,
        entry_hash=None,
        created_at=created_at or datetime.now(UTC),
    )
    entry = JournalAnchorLogEntry(
        sequence=unsigned_entry.sequence,
        anchor=unsigned_entry.anchor,
        previous_entry_hash=unsigned_entry.previous_entry_hash,
        entry_hash=_anchor_log_entry_hash(unsigned_entry),
        created_at=unsigned_entry.created_at,
    )
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("ab") as handle:
        handle.write(deterministic_json_bytes(entry.as_dict()) + b"\n")
    return entry


def load_journal_anchor(anchor_path: Path) -> JournalAnchor:
    """Load a journal anchor from JSON."""

    raw = json.loads(anchor_path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise JournalAnchorError("journal anchor must be a JSON object")
    return _anchor_from_dict(raw)


def load_journal_anchor_log(log_path: Path) -> tuple[JournalAnchorLogEntry, ...]:
    """Load anchor log entries after verifying the local hash chain."""

    verification = verify_journal_anchor_log(log_path)
    if not verification.ok:
        raise JournalAnchorError("cannot load an anchor log that fails verification")

    if not log_path.exists():
        return ()

    entries: list[JournalAnchorLogEntry] = []
    for raw_line in log_path.read_bytes().splitlines():
        raw = json.loads(raw_line)
        if not isinstance(raw, dict):
            raise JournalAnchorError("anchor log record must be a JSON object")
        entries.append(_anchor_log_entry_from_dict(raw))
    return tuple(entries)


def verify_journal_anchor(
    journal_path: Path,
    anchor: JournalAnchor,
    *,
    signing_key: bytes | None = None,
) -> AnchorVerificationResult:
    """Verify a journal against a trusted anchor."""

    issues: list[AnchorVerificationIssue] = []

    if anchor.signature is not None:
        if signing_key is None:
            issues.append(
                AnchorVerificationIssue(
                    code="signature_key_missing",
                    message="signed anchor verification requires a signing key",
                )
            )
        elif anchor.signature != _anchor_signature(anchor, signing_key):
            issues.append(
                AnchorVerificationIssue(
                    code="signature_mismatch",
                    message="anchor signature does not match trusted key",
                )
            )

    verification = verify_journal(
        journal_path,
        expected_record_count=anchor.record_count,
        expected_last_event_hash=anchor.last_event_hash,
    )
    if not verification.ok:
        issues.append(
            AnchorVerificationIssue(
                code="journal_verification_failed",
                message="journal does not match trusted anchor",
            )
        )

    return AnchorVerificationResult(
        ok=not issues,
        journal_verification=verification,
        issues=tuple(issues),
    )


def verify_journal_anchor_log(
    log_path: Path,
    *,
    expected_record_count: int | None = None,
    expected_last_entry_hash: str | None = None,
) -> AnchorLogVerificationResult:
    """Verify a local append-only anchor log."""

    issues: list[AnchorLogVerificationIssue] = []
    records_verified = 0
    last_entry_hash: str | None = None

    if log_path.exists():
        for record_number, raw_line in enumerate(log_path.read_bytes().splitlines(), start=1):
            if raw_line == b"":
                issues.append(
                    AnchorLogVerificationIssue(
                        record_number=record_number,
                        code="empty_record",
                        message="anchor log record is empty",
                    )
                )
                break

            try:
                raw = json.loads(raw_line)
            except json.JSONDecodeError:
                issues.append(
                    AnchorLogVerificationIssue(
                        record_number=record_number,
                        code="parse_error",
                        message="anchor log record is not valid JSON",
                    )
                )
                break

            if not isinstance(raw, dict):
                issues.append(
                    AnchorLogVerificationIssue(
                        record_number=record_number,
                        code="parse_error",
                        message="anchor log record must be a JSON object",
                    )
                )
                break

            try:
                entry = _anchor_log_entry_from_dict(raw)
            except (JournalAnchorError, ValueError):
                issues.append(
                    AnchorLogVerificationIssue(
                        record_number=record_number,
                        code="parse_error",
                        message="anchor log record is malformed",
                    )
                )
                break

            expected_sequence = records_verified + 1
            if entry.sequence != expected_sequence:
                issues.append(
                    AnchorLogVerificationIssue(
                        record_number=record_number,
                        code="sequence_mismatch",
                        message="anchor log sequence does not match record order",
                        expected=expected_sequence,
                        actual=entry.sequence,
                    )
                )
                break

            if entry.previous_entry_hash != last_entry_hash:
                issues.append(
                    AnchorLogVerificationIssue(
                        record_number=record_number,
                        code="previous_hash_mismatch",
                        message="anchor log previous hash does not match prior record",
                        expected=last_entry_hash,
                        actual=entry.previous_entry_hash,
                    )
                )
                break

            if entry.entry_hash is None:
                issues.append(
                    AnchorLogVerificationIssue(
                        record_number=record_number,
                        code="entry_hash_missing",
                        message="anchor log record is missing entry hash",
                    )
                )
                break

            expected_entry_hash = _anchor_log_entry_hash(entry)
            if entry.entry_hash != expected_entry_hash:
                issues.append(
                    AnchorLogVerificationIssue(
                        record_number=record_number,
                        code="entry_hash_mismatch",
                        message="anchor log entry hash does not match record bytes",
                        expected=expected_entry_hash,
                        actual=entry.entry_hash,
                    )
                )
                break

            records_verified += 1
            last_entry_hash = entry.entry_hash

    if expected_record_count is not None and records_verified != expected_record_count:
        issues.append(
            AnchorLogVerificationIssue(
                record_number=records_verified + 1,
                code="expected_record_count_mismatch",
                message="anchor log does not match trusted record count",
                expected=expected_record_count,
                actual=records_verified,
            )
        )
    if expected_last_entry_hash is not None and last_entry_hash != expected_last_entry_hash:
        issues.append(
            AnchorLogVerificationIssue(
                record_number=records_verified,
                code="expected_last_hash_mismatch",
                message="anchor log does not match trusted last entry hash",
                expected=expected_last_entry_hash,
                actual=last_entry_hash,
            )
        )

    return AnchorLogVerificationResult(
        ok=not issues,
        records_verified=records_verified,
        last_entry_hash=last_entry_hash,
        issues=tuple(issues),
    )


def create_segment_manifest(
    segment_path: Path,
    *,
    segment_index: int = 0,
    signing_key: bytes | None = None,
    created_at: datetime | None = None,
) -> JournalSegmentManifest:
    """Create a manifest for one journal segment."""

    return JournalSegmentManifest(
        segment_path=str(segment_path),
        segment_index=segment_index,
        anchor=create_journal_anchor(
            segment_path,
            signing_key=signing_key,
            created_at=created_at,
        ),
    )


def write_segment_manifest(manifest: JournalSegmentManifest, manifest_path: Path) -> None:
    """Write a segment manifest as deterministic JSON."""

    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_bytes(deterministic_json_bytes(manifest.as_dict()) + b"\n")


def load_segment_manifest(manifest_path: Path) -> JournalSegmentManifest:
    """Load a segment manifest from JSON."""

    raw = json.loads(manifest_path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise JournalAnchorError("journal segment manifest must be a JSON object")

    anchor_raw = raw.get("anchor")
    if not isinstance(anchor_raw, dict):
        raise JournalAnchorError("journal segment manifest missing anchor object")

    return JournalSegmentManifest(
        segment_path=_required_str(raw, "segment_path"),
        segment_index=_required_int(raw, "segment_index"),
        manifest_version=_required_str(raw, "manifest_version"),
        anchor=_anchor_from_dict(anchor_raw),
    )


def locate_first_corrupt_record(
    journal_path: Path,
    *,
    expected_record_count: int | None = None,
    expected_last_event_hash: str | None = None,
) -> VerificationIssue | None:
    """Return the first verification issue, if any."""

    result = verify_journal(
        journal_path,
        expected_record_count=expected_record_count,
        expected_last_event_hash=expected_last_event_hash,
    )
    if result.ok:
        return None
    return result.issues[0]


def export_verified_prefix(
    journal_path: Path,
    output_path: Path,
    *,
    expected_record_count: int | None = None,
    expected_last_event_hash: str | None = None,
) -> VerifiedPrefixExport:
    """Export records verified before the first detected issue."""

    verification = verify_journal(
        journal_path,
        expected_record_count=expected_record_count,
        expected_last_event_hash=expected_last_event_hash,
    )
    lines = journal_path.read_bytes().splitlines()
    verified_lines = lines[: verification.records_verified]

    output_path.parent.mkdir(parents=True, exist_ok=True)
    if verified_lines:
        output_path.write_bytes(b"\n".join(verified_lines) + b"\n")
    else:
        output_path.write_bytes(b"")

    return VerifiedPrefixExport(
        source_path=journal_path,
        output_path=output_path,
        records_exported=verification.records_verified,
        verification=verification,
    )


def _anchor_signature(anchor: JournalAnchor, signing_key: bytes) -> str:
    signature = hmac.new(
        signing_key,
        deterministic_json_bytes(anchor.unsigned_dict()),
        hashlib.sha256,
    ).hexdigest()
    return f"{ANCHOR_SIGNATURE_ALGORITHM}:{signature}"


def _anchor_log_entry_hash(entry: JournalAnchorLogEntry) -> str:
    digest = hashlib.sha256(deterministic_json_bytes(entry.hash_input_dict())).hexdigest()
    return f"sha256:{digest}"


def _anchor_from_dict(raw: dict[str, Any]) -> JournalAnchor:
    created_at_raw = _required_str(raw, "created_at")
    created_at = datetime.fromisoformat(created_at_raw.replace("Z", "+00:00")).astimezone(UTC)
    last_event_hash = raw.get("last_event_hash")
    signature_algorithm = raw.get("signature_algorithm")
    signature = raw.get("signature")

    return JournalAnchor(
        anchor_version=_required_str(raw, "anchor_version"),
        created_at=created_at,
        journal_path=_required_str(raw, "journal_path"),
        last_event_hash=cast(str | None, last_event_hash),
        record_count=_required_int(raw, "record_count"),
        signature_algorithm=cast(str | None, signature_algorithm),
        signature=cast(str | None, signature),
    )


def _anchor_log_entry_from_dict(raw: dict[str, Any]) -> JournalAnchorLogEntry:
    created_at_raw = _required_str(raw, "created_at")
    created_at = datetime.fromisoformat(created_at_raw.replace("Z", "+00:00")).astimezone(UTC)
    anchor_raw = raw.get("anchor")
    if not isinstance(anchor_raw, dict):
        raise JournalAnchorError("anchor log record missing anchor object")

    previous_entry_hash = raw.get("previous_entry_hash")
    entry_hash = raw.get("entry_hash")
    return JournalAnchorLogEntry(
        anchor=_anchor_from_dict(anchor_raw),
        created_at=created_at,
        entry_hash=cast(str | None, entry_hash),
        log_version=_required_str(raw, "log_version"),
        previous_entry_hash=cast(str | None, previous_entry_hash),
        sequence=_required_int(raw, "sequence"),
    )


def _required_str(raw: dict[str, Any], key: str) -> str:
    value = raw.get(key)
    if not isinstance(value, str) or not value:
        raise JournalAnchorError(f"anchor field is required: {key}")
    return value


def _required_int(raw: dict[str, Any], key: str) -> int:
    value = raw.get(key)
    if not isinstance(value, int):
        raise JournalAnchorError(f"anchor integer field is required: {key}")
    return value


def _timestamp(value: datetime) -> str:
    if value.tzinfo is None or value.tzinfo.utcoffset(value) is None:
        raise JournalAnchorError("anchor timestamps must be timezone-aware")
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")
