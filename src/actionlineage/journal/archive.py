"""Journal archive manifests for object-storage workflows."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal, cast

from actionlineage.domain import deterministic_json_bytes
from actionlineage.domain.events import JsonObject
from actionlineage.journal.anchors import JournalAnchorError
from actionlineage.journal.local import verified_journal_snapshot, verify_journal
from actionlineage.journal.verify import VerificationResult

JOURNAL_ARCHIVE_MANIFEST_VERSION = "actionlineage.dev/journal-archive-manifest-v1"

type ArchiveRetentionMode = Literal["none", "governance", "compliance", "legal_hold"]
type ArchiveIssueCode = Literal[
    "journal_file_missing",
    "journal_hash_mismatch",
    "journal_verification_failed",
]


@dataclass(frozen=True, slots=True)
class JournalArchiveManifest:
    """Local manifest describing an archived journal object.

    The manifest records the intended object location and local journal bytes.
    It does not upload the journal or prove object-lock enforcement by itself.
    """

    journal_path: str
    object_uri: str
    journal_sha256: str
    size_bytes: int
    record_count: int
    last_event_hash: str | None
    created_at: datetime
    retention_mode: ArchiveRetentionMode = "none"
    storage_class: str | None = None
    manifest_version: str = JOURNAL_ARCHIVE_MANIFEST_VERSION

    def as_dict(self) -> JsonObject:
        """Return a JSON-compatible archive manifest."""

        return {
            "created_at": _timestamp(self.created_at),
            "journal_path": self.journal_path,
            "journal_sha256": self.journal_sha256,
            "last_event_hash": self.last_event_hash,
            "manifest_version": self.manifest_version,
            "object_uri": self.object_uri,
            "record_count": self.record_count,
            "retention_mode": self.retention_mode,
            "size_bytes": self.size_bytes,
            "storage_class": self.storage_class,
        }


@dataclass(frozen=True, slots=True)
class ArchiveVerificationIssue:
    """One archive manifest verification issue."""

    code: ArchiveIssueCode
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
        }


@dataclass(frozen=True, slots=True)
class ArchiveVerificationResult:
    """Result of verifying a local journal against an archive manifest."""

    ok: bool
    journal_verification: VerificationResult | None
    issues: tuple[ArchiveVerificationIssue, ...] = ()

    def as_dict(self) -> dict[str, object]:
        """Return a JSON-compatible result object."""

        return {
            "ok": self.ok,
            "journal_verification": (
                self.journal_verification.as_dict()
                if self.journal_verification is not None
                else None
            ),
            "issues": [issue.as_dict() for issue in self.issues],
        }


def create_journal_archive_manifest(
    journal_path: Path,
    *,
    object_uri: str,
    retention_mode: ArchiveRetentionMode = "none",
    storage_class: str | None = None,
    created_at: datetime | None = None,
) -> JournalArchiveManifest:
    """Create an archive manifest from a verified local journal."""

    snapshot = verified_journal_snapshot(journal_path)
    if not snapshot.ok:
        raise JournalAnchorError("cannot archive-manifest a journal that fails verification")
    if snapshot.metadata_after is None or snapshot.journal_sha256 is None:
        raise JournalAnchorError("cannot archive-manifest a missing journal file")
    if not object_uri:
        raise JournalAnchorError("archive manifest object_uri is required")
    return JournalArchiveManifest(
        journal_path=str(journal_path),
        object_uri=object_uri,
        journal_sha256=snapshot.journal_sha256,
        size_bytes=snapshot.metadata_after.size,
        record_count=snapshot.record_count,
        last_event_hash=snapshot.terminal_hash,
        created_at=created_at or datetime.now(UTC),
        retention_mode=retention_mode,
        storage_class=storage_class,
    )


def write_journal_archive_manifest(
    manifest: JournalArchiveManifest,
    manifest_path: Path,
) -> None:
    """Write an archive manifest as deterministic JSON."""

    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_bytes(deterministic_json_bytes(manifest.as_dict()) + b"\n")


def load_journal_archive_manifest(manifest_path: Path) -> JournalArchiveManifest:
    """Load an archive manifest from JSON."""

    raw = json.loads(manifest_path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise JournalAnchorError("journal archive manifest must be a JSON object")
    return _manifest_from_dict(raw)


def verify_journal_archive_manifest(
    manifest: JournalArchiveManifest,
    *,
    journal_path: Path | None = None,
) -> ArchiveVerificationResult:
    """Verify local journal bytes and trusted tail values against a manifest."""

    effective_journal_path = journal_path or Path(manifest.journal_path)
    issues: list[ArchiveVerificationIssue] = []
    if not effective_journal_path.exists():
        return ArchiveVerificationResult(
            ok=False,
            journal_verification=None,
            issues=(
                ArchiveVerificationIssue(
                    code="journal_file_missing",
                    message="journal file referenced by archive manifest is missing",
                    expected=manifest.journal_path,
                    actual=str(effective_journal_path),
                ),
            ),
        )

    actual_hash = _file_sha256(effective_journal_path)
    if actual_hash != manifest.journal_sha256:
        issues.append(
            ArchiveVerificationIssue(
                code="journal_hash_mismatch",
                message="journal bytes do not match archive manifest",
                expected=manifest.journal_sha256,
                actual=actual_hash,
            )
        )

    journal_verification = verify_journal(
        effective_journal_path,
        expected_record_count=manifest.record_count,
        expected_last_event_hash=manifest.last_event_hash,
    )
    if not journal_verification.ok:
        issues.append(
            ArchiveVerificationIssue(
                code="journal_verification_failed",
                message="journal does not match archive manifest trusted tail values",
            )
        )

    return ArchiveVerificationResult(
        ok=not issues,
        journal_verification=journal_verification,
        issues=tuple(issues),
    )


def _manifest_from_dict(raw: dict[str, Any]) -> JournalArchiveManifest:
    created_at_raw = _required_str(raw, "created_at")
    created_at = datetime.fromisoformat(created_at_raw.replace("Z", "+00:00")).astimezone(UTC)
    last_event_hash = raw.get("last_event_hash")
    storage_class = raw.get("storage_class")
    return JournalArchiveManifest(
        created_at=created_at,
        journal_path=_required_str(raw, "journal_path"),
        journal_sha256=_required_str(raw, "journal_sha256"),
        last_event_hash=cast(str | None, last_event_hash),
        manifest_version=_required_str(raw, "manifest_version"),
        object_uri=_required_str(raw, "object_uri"),
        record_count=_required_int(raw, "record_count"),
        retention_mode=_retention_mode(raw.get("retention_mode")),
        size_bytes=_required_int(raw, "size_bytes"),
        storage_class=cast(str | None, storage_class),
    )


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    return f"sha256:{digest}"


def _retention_mode(value: object) -> ArchiveRetentionMode:
    if value in {"none", "governance", "compliance", "legal_hold"}:
        return cast(ArchiveRetentionMode, value)
    raise JournalAnchorError("journal archive manifest has invalid retention_mode")


def _required_str(raw: dict[str, Any], key: str) -> str:
    value = raw.get(key)
    if not isinstance(value, str) or not value:
        raise JournalAnchorError(f"journal archive manifest field is required: {key}")
    return value


def _required_int(raw: dict[str, Any], key: str) -> int:
    value = raw.get(key)
    if not isinstance(value, int):
        raise JournalAnchorError(f"journal archive manifest integer field is required: {key}")
    return value


def _timestamp(value: datetime) -> str:
    if value.tzinfo is None or value.tzinfo.utcoffset(value) is None:
        raise JournalAnchorError("journal archive manifest timestamps must be timezone-aware")
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")
