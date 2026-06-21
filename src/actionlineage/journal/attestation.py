"""External attestation sidecars for journal anchors."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path

from actionlineage.domain import deterministic_json_bytes
from actionlineage.domain.events import JsonObject
from actionlineage.journal.anchors import JournalAnchor
from actionlineage.journal.hashing import sha256_digest

EXTERNAL_ANCHOR_ATTESTATION_VERSION = "actionlineage.dev/external-anchor-attestation-v1"


class ExternalAttestationType(StrEnum):
    """External attestation mechanism labels."""

    HARDWARE_KEY = "hardware_key"
    REMOTE_ATTESTATION = "remote_attestation"
    TIMESTAMP_AUTHORITY = "timestamp_authority"
    TRANSPARENCY_LOG = "transparency_log"


@dataclass(frozen=True, slots=True)
class ExternalAnchorAttestation:
    """Sidecar linking a journal anchor to an external attestation artifact."""

    anchor_hash: str
    anchor_version: str
    attester: str
    attestation_type: ExternalAttestationType
    statement_digest: str
    statement_reference: str | None
    created_at: datetime
    limitations: tuple[str, ...]
    attestation_version: str = EXTERNAL_ANCHOR_ATTESTATION_VERSION

    def as_dict(self) -> JsonObject:
        """Return a JSON-compatible attestation statement."""

        return {
            "anchor_hash": self.anchor_hash,
            "anchor_version": self.anchor_version,
            "attestation_type": self.attestation_type.value,
            "attestation_version": self.attestation_version,
            "attester": self.attester,
            "created_at": self.created_at.isoformat().replace("+00:00", "Z"),
            "limitations": list(self.limitations),
            "statement_digest": self.statement_digest,
            "statement_reference": self.statement_reference,
        }


@dataclass(frozen=True, slots=True)
class ExternalAnchorAttestationIssue:
    """One external anchor attestation verification issue."""

    code: str
    message: str

    def as_dict(self) -> dict[str, str]:
        """Return a JSON-compatible issue."""

        return {"code": self.code, "message": self.message}


@dataclass(frozen=True, slots=True)
class ExternalAnchorAttestationVerificationResult:
    """Local consistency verification for an external attestation sidecar."""

    ok: bool
    issues: tuple[ExternalAnchorAttestationIssue, ...] = ()

    def as_dict(self) -> dict[str, object]:
        """Return a JSON-compatible verification result."""

        return {
            "ok": self.ok,
            "issues": [issue.as_dict() for issue in self.issues],
        }


def create_external_anchor_attestation(
    anchor: JournalAnchor,
    *,
    attester: str,
    attestation_type: ExternalAttestationType,
    statement_bytes: bytes,
    statement_reference: str | None = None,
    created_at: datetime | None = None,
    limitations: tuple[str, ...] = (
        "external attestation statement is verified outside ActionLineage",
    ),
) -> ExternalAnchorAttestation:
    """Create a sidecar linking an anchor to externally produced attestation bytes."""

    if not attester.strip():
        raise ValueError("attester must be nonempty")
    return ExternalAnchorAttestation(
        anchor_hash=_anchor_hash(anchor),
        anchor_version=anchor.anchor_version,
        attester=attester,
        attestation_type=attestation_type,
        statement_digest=sha256_digest(statement_bytes),
        statement_reference=statement_reference,
        created_at=created_at or datetime.now(UTC),
        limitations=limitations,
    )


def verify_external_anchor_attestation(
    anchor: JournalAnchor,
    attestation: ExternalAnchorAttestation,
    *,
    statement_bytes: bytes | None = None,
) -> ExternalAnchorAttestationVerificationResult:
    """Verify local consistency of an external anchor attestation sidecar."""

    issues: list[ExternalAnchorAttestationIssue] = []
    if attestation.attestation_version != EXTERNAL_ANCHOR_ATTESTATION_VERSION:
        issues.append(
            ExternalAnchorAttestationIssue(
                code="unsupported_attestation_version",
                message="external anchor attestation version is unsupported",
            )
        )
    if attestation.anchor_version != anchor.anchor_version:
        issues.append(
            ExternalAnchorAttestationIssue(
                code="anchor_version_mismatch",
                message="attestation anchor version does not match anchor",
            )
        )
    if attestation.anchor_hash != _anchor_hash(anchor):
        issues.append(
            ExternalAnchorAttestationIssue(
                code="anchor_hash_mismatch",
                message="attestation anchor hash does not match current anchor bytes",
            )
        )
    if statement_bytes is not None and attestation.statement_digest != sha256_digest(
        statement_bytes
    ):
        issues.append(
            ExternalAnchorAttestationIssue(
                code="statement_digest_mismatch",
                message="external attestation statement digest does not match local bytes",
            )
        )
    return ExternalAnchorAttestationVerificationResult(ok=not issues, issues=tuple(issues))


def write_external_anchor_attestation(
    attestation: ExternalAnchorAttestation,
    path: Path,
) -> None:
    """Write a deterministic external attestation sidecar."""

    Path(path).write_bytes(deterministic_json_bytes(attestation.as_dict()) + b"\n")


def load_external_anchor_attestation(path: Path) -> ExternalAnchorAttestation:
    """Load an external anchor attestation sidecar from JSON."""

    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("external anchor attestation must be a JSON object")
    created_at_raw = _required_string(data, "created_at")
    created_at = datetime.fromisoformat(created_at_raw.replace("Z", "+00:00"))
    limitations_value = data.get("limitations")
    if not isinstance(limitations_value, list):
        raise ValueError("external anchor attestation limitations must be a list")
    return ExternalAnchorAttestation(
        anchor_hash=_required_string(data, "anchor_hash"),
        anchor_version=_required_string(data, "anchor_version"),
        attester=_required_string(data, "attester"),
        attestation_type=ExternalAttestationType(_required_string(data, "attestation_type")),
        statement_digest=_required_string(data, "statement_digest"),
        statement_reference=_optional_string(data, "statement_reference"),
        created_at=created_at,
        limitations=tuple(value for value in limitations_value if isinstance(value, str)),
        attestation_version=_required_string(data, "attestation_version"),
    )


def _anchor_hash(anchor: JournalAnchor) -> str:
    return sha256_digest(deterministic_json_bytes(anchor.as_dict()))


def _required_string(data: dict[str, object], field: str) -> str:
    value = data.get(field)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"external anchor attestation field must be a nonempty string: {field}")
    return value


def _optional_string(data: dict[str, object], field: str) -> str | None:
    value = data.get(field)
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"external anchor attestation field must be a string: {field}")
    return value
