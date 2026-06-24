"""Observer attestation declarations for independent evidence claims."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date
from enum import StrEnum
from types import MappingProxyType
from typing import Any

from actionlineage.domain import ResourceType
from actionlineage.domain.events import JsonObject
from actionlineage.observers.local import ObservationOutcome

DEFAULT_ATTESTATION_MAX_AGE_DAYS = 365


class AttestationEvidenceKind(StrEnum):
    """Declared evidence source category for an observer."""

    INDEPENDENT_LIVE_TELEMETRY = "independent_live_telemetry"
    EXTERNAL_SENSOR_FEED = "external_sensor_feed"
    FIXTURE_ORACLE = "fixture_oracle"
    POST_ACTION_READBACK = "post_action_readback"
    SELF_REPORTED = "self_reported"
    UNKNOWN = "unknown"


class IndependenceBoundary(StrEnum):
    """Boundaries that must be reviewed before claiming independence."""

    TOOL = "tool"
    PRINCIPAL = "principal"
    CREDENTIAL = "credential"
    EXECUTION_HOST = "execution_host"
    NETWORK_PATH = "network_path"
    STORAGE_PLANE = "storage_plane"
    ADMINISTRATIVE_CONTROL_PLANE = "administrative_control_plane"


class IndependenceBoundaryStatus(StrEnum):
    """Independence status for one reviewed boundary."""

    INDEPENDENT = "independent"
    SHARED = "shared"
    UNKNOWN = "unknown"
    NOT_APPLICABLE = "not_applicable"


REQUIRED_INDEPENDENCE_BOUNDARIES: tuple[IndependenceBoundary, ...] = tuple(IndependenceBoundary)


class ObserverAttestationError(ValueError):
    """Raised when an observation lacks valid attestation for a claim."""


@dataclass(frozen=True, slots=True)
class ObserverAttestationDeclaration:
    """Reviewed declaration that scopes observer independence claims."""

    observer_identity: str
    producer_identity: str
    collection_method: str
    subject_action_types: tuple[str, ...]
    resource_types: tuple[ResourceType, ...]
    evidence_kind: AttestationEvidenceKind
    independence_boundaries: Mapping[IndependenceBoundary, IndependenceBoundaryStatus]
    shared_dependencies: tuple[str, ...]
    blind_spots: tuple[str, ...]
    failure_modes: tuple[str, ...]
    tamper_assumptions: tuple[str, ...]
    retention: str
    redaction_scopes: tuple[str, ...]
    policy_version: str
    owner: str
    reviewed_at: date
    valid_until: date | None = None
    limitations: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "observer_identity",
            _required_string(self.observer_identity, "observer_identity"),
        )
        object.__setattr__(
            self,
            "producer_identity",
            _required_string(self.producer_identity, "producer_identity"),
        )
        object.__setattr__(
            self,
            "collection_method",
            _required_string(self.collection_method, "collection_method"),
        )
        object.__setattr__(
            self,
            "subject_action_types",
            _string_tuple(self.subject_action_types, field="subject_action_types"),
        )
        object.__setattr__(
            self,
            "resource_types",
            tuple(
                item if isinstance(item, ResourceType) else ResourceType(item)
                for item in self.resource_types
            ),
        )
        if not self.resource_types:
            raise ValueError("resource_types must contain at least one resource type")
        object.__setattr__(
            self,
            "evidence_kind",
            self.evidence_kind
            if isinstance(self.evidence_kind, AttestationEvidenceKind)
            else AttestationEvidenceKind(self.evidence_kind),
        )
        object.__setattr__(
            self,
            "independence_boundaries",
            MappingProxyType(_boundary_mapping(self.independence_boundaries)),
        )
        object.__setattr__(
            self,
            "shared_dependencies",
            _string_tuple(self.shared_dependencies, field="shared_dependencies", allow_empty=True),
        )
        object.__setattr__(
            self,
            "blind_spots",
            _string_tuple(self.blind_spots, field="blind_spots"),
        )
        object.__setattr__(
            self,
            "failure_modes",
            _string_tuple(self.failure_modes, field="failure_modes"),
        )
        object.__setattr__(
            self,
            "tamper_assumptions",
            _string_tuple(self.tamper_assumptions, field="tamper_assumptions"),
        )
        object.__setattr__(self, "retention", _required_string(self.retention, "retention"))
        object.__setattr__(
            self,
            "redaction_scopes",
            _string_tuple(self.redaction_scopes, field="redaction_scopes"),
        )
        object.__setattr__(
            self,
            "policy_version",
            _required_string(self.policy_version, "policy_version"),
        )
        object.__setattr__(self, "owner", _required_string(self.owner, "owner"))
        object.__setattr__(
            self,
            "limitations",
            _string_tuple(self.limitations, field="limitations", allow_empty=True),
        )
        if self.valid_until is not None and self.valid_until < self.reviewed_at:
            raise ValueError("valid_until cannot be before reviewed_at")

    def as_dict(self) -> JsonObject:
        """Return a JSON-compatible declaration for review artifacts."""

        payload: JsonObject = {
            "observer_identity": self.observer_identity,
            "producer_identity": self.producer_identity,
            "collection_method": self.collection_method,
            "subject_action_types": list(self.subject_action_types),
            "resource_types": [resource_type.value for resource_type in self.resource_types],
            "evidence_kind": self.evidence_kind.value,
            "independence_boundaries": {
                boundary.value: status.value
                for boundary, status in self.independence_boundaries.items()
            },
            "shared_dependencies": list(self.shared_dependencies),
            "blind_spots": list(self.blind_spots),
            "failure_modes": list(self.failure_modes),
            "tamper_assumptions": list(self.tamper_assumptions),
            "retention": self.retention,
            "redaction_scopes": list(self.redaction_scopes),
            "policy_version": self.policy_version,
            "owner": self.owner,
            "reviewed_at": self.reviewed_at.isoformat(),
            "limitations": list(self.limitations),
        }
        if self.valid_until is not None:
            payload["valid_until"] = self.valid_until.isoformat()
        return payload


def independent_claim_rejection_reasons(
    *,
    attestation: ObserverAttestationDeclaration | None,
    observation: ObservationOutcome,
    subject_action_type: str | None,
    subject_resource_type: ResourceType | None,
    reference_date: date | None = None,
    max_review_age_days: int = DEFAULT_ATTESTATION_MAX_AGE_DAYS,
) -> tuple[str, ...]:
    """Return reasons an observation cannot be claimed as independent."""

    if attestation is None:
        return ("missing reviewed observer attestation declaration",)

    reasons: list[str] = []
    today = reference_date or date.today()

    if attestation.observer_identity != observation.observer_identity:
        reasons.append("attestation observer_identity does not match observation observer_identity")

    if attestation.evidence_kind != AttestationEvidenceKind.INDEPENDENT_LIVE_TELEMETRY:
        reasons.append("attestation evidence_kind is not independent_live_telemetry")

    if subject_action_type is None or not subject_action_type.strip():
        reasons.append("subject action type is required for independent observer attestation")
    elif not _scope_contains(attestation.subject_action_types, subject_action_type):
        reasons.append("subject action type is outside observer attestation scope")

    if subject_resource_type is None:
        reasons.append("subject resource type is required for independent observer attestation")
    elif subject_resource_type not in attestation.resource_types:
        reasons.append("subject resource type is outside observer attestation scope")

    if attestation.reviewed_at > today:
        reasons.append("observer attestation review date is in the future")

    if attestation.valid_until is not None and attestation.valid_until < today:
        reasons.append("observer attestation declaration is expired")

    if (today - attestation.reviewed_at).days > max_review_age_days:
        reasons.append("observer attestation declaration is stale")

    if attestation.shared_dependencies:
        reasons.append("observer attestation declares shared dependencies")

    for boundary in REQUIRED_INDEPENDENCE_BOUNDARIES:
        status = attestation.independence_boundaries.get(boundary)
        if status is None:
            reasons.append(f"observer attestation is missing {boundary.value} boundary")
        elif status != IndependenceBoundaryStatus.INDEPENDENT:
            reasons.append(f"observer attestation {boundary.value} boundary is {status.value}")

    return tuple(reasons)


def require_independent_observer_attestation(
    *,
    attestation: ObserverAttestationDeclaration | None,
    observation: ObservationOutcome,
    subject_action_type: str | None,
    subject_resource_type: ResourceType | None,
    reference_date: date | None = None,
    max_review_age_days: int = DEFAULT_ATTESTATION_MAX_AGE_DAYS,
) -> None:
    """Raise unless an observation is in scope for an independent claim."""

    reasons = independent_claim_rejection_reasons(
        attestation=attestation,
        observation=observation,
        subject_action_type=subject_action_type,
        subject_resource_type=subject_resource_type,
        reference_date=reference_date,
        max_review_age_days=max_review_age_days,
    )
    if reasons:
        raise ObserverAttestationError(
            "independent observer attestation required: " + "; ".join(reasons)
        )


def observer_attestation_declaration_from_dict(
    data: Mapping[str, object],
) -> ObserverAttestationDeclaration:
    """Parse a reviewed observer attestation declaration from JSON-compatible data."""

    return ObserverAttestationDeclaration(
        observer_identity=_required_mapping_string(data, "observer_identity"),
        producer_identity=_required_mapping_string(data, "producer_identity"),
        collection_method=_required_mapping_string(data, "collection_method"),
        subject_action_types=_mapping_string_tuple(data, "subject_action_types"),
        resource_types=tuple(
            ResourceType(item) for item in _mapping_string_tuple(data, "resource_types")
        ),
        evidence_kind=AttestationEvidenceKind(_required_mapping_string(data, "evidence_kind")),
        independence_boundaries=_mapping_boundaries(data.get("independence_boundaries")),
        shared_dependencies=_mapping_string_tuple(
            data,
            "shared_dependencies",
            allow_missing=True,
        ),
        blind_spots=_mapping_string_tuple(data, "blind_spots"),
        failure_modes=_mapping_string_tuple(data, "failure_modes"),
        tamper_assumptions=_mapping_string_tuple(data, "tamper_assumptions"),
        retention=_required_mapping_string(data, "retention"),
        redaction_scopes=_mapping_string_tuple(data, "redaction_scopes"),
        policy_version=_required_mapping_string(data, "policy_version"),
        owner=_required_mapping_string(data, "owner"),
        reviewed_at=_mapping_date(data, "reviewed_at"),
        valid_until=_optional_mapping_date(data, "valid_until"),
        limitations=_mapping_string_tuple(data, "limitations", allow_missing=True),
    )


def _boundary_mapping(
    value: Mapping[Any, Any],
) -> dict[
    IndependenceBoundary,
    IndependenceBoundaryStatus,
]:
    mapping: dict[IndependenceBoundary, IndependenceBoundaryStatus] = {}
    for boundary, status in value.items():
        if isinstance(boundary, IndependenceBoundary):
            key = boundary
        elif isinstance(boundary, str):
            key = IndependenceBoundary(boundary)
        else:
            raise ValueError("independence boundary keys must be strings")
        if isinstance(status, IndependenceBoundaryStatus):
            mapping[key] = status
        elif isinstance(status, str):
            mapping[key] = IndependenceBoundaryStatus(status)
        else:
            raise ValueError("independence boundary values must be strings")
    return mapping


def _mapping_boundaries(value: object) -> dict[IndependenceBoundary, IndependenceBoundaryStatus]:
    if not isinstance(value, Mapping):
        raise ValueError("independence_boundaries must be an object")
    return _boundary_mapping(value)


def _required_string(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be a nonempty string")
    return value


def _required_mapping_string(data: Mapping[str, object], field: str) -> str:
    return _required_string(data.get(field), field)


def _string_tuple(
    value: tuple[str, ...],
    *,
    field: str,
    allow_empty: bool = False,
) -> tuple[str, ...]:
    if not isinstance(value, tuple):
        raise ValueError(f"{field} must be a tuple of strings")
    if not value and not allow_empty:
        raise ValueError(f"{field} must contain at least one string")
    for item in value:
        _required_string(item, field)
    return value


def _mapping_string_tuple(
    data: Mapping[str, object],
    field: str,
    *,
    allow_missing: bool = False,
) -> tuple[str, ...]:
    value = data.get(field)
    if value is None and allow_missing:
        return ()
    if not isinstance(value, list):
        raise ValueError(f"{field} must be a list of strings")
    return _string_tuple(tuple(value), field=field, allow_empty=allow_missing)


def _mapping_date(data: Mapping[str, object], field: str) -> date:
    value = data.get(field)
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        return date.fromisoformat(value)
    raise ValueError(f"{field} must be an ISO date string")


def _optional_mapping_date(data: Mapping[str, object], field: str) -> date | None:
    if data.get(field) is None:
        return None
    return _mapping_date(data, field)


def _scope_contains(values: tuple[str, ...], value: str) -> bool:
    return "*" in values or value in values
