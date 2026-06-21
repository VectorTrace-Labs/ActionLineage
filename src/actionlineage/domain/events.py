"""Versioned lineage event envelope and core value objects."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, ClassVar, Literal, cast

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

SPEC_VERSION: Literal["actionlineage.dev/v1alpha1"] = "actionlineage.dev/v1alpha1"
CANONICALIZATION_VERSION = "actionlineage.dev/json-deterministic-v0"

type JsonScalar = str | int | float | bool | None
type JsonValue = JsonScalar | list[JsonValue] | dict[str, JsonValue]
type JsonObject = dict[str, JsonValue]


class EventType(StrEnum):
    """Known v1alpha1 event types."""

    AGENT_INTENT_RECORDED = "agent.intent.recorded"
    AGENT_RUN_STARTED = "agent.run.started"
    AGENT_RUN_COMPLETED = "agent.run.completed"
    AGENT_RUN_FAILED = "agent.run.failed"
    AGENT_TOOL_DISCOVERED = "agent.tool.discovered"
    AGENT_TOOL_SCHEMA_CHANGED = "agent.tool.schema_changed"
    AGENT_TOOL_CALL_REQUESTED = "agent.tool.call.requested"
    AGENT_TOOL_CALL_STARTED = "agent.tool.call.started"
    AGENT_TOOL_CALL_COMPLETED = "agent.tool.call.completed"
    AGENT_TOOL_CALL_FAILED = "agent.tool.call.failed"
    AGENT_TOOL_CALL_DENIED = "agent.tool.call.denied"
    POLICY_EVALUATION_STARTED = "policy.evaluation.started"
    POLICY_DECISION = "policy.decision"
    APPROVAL_REQUESTED = "approval.requested"
    APPROVAL_RESOLVED = "approval.resolved"
    TOOL_EXECUTION_REQUESTED = "tool.execution.requested"
    TOOL_EXECUTION_AUTHORIZED = "tool.execution.authorized"
    TOOL_EXECUTION_DISPATCHED = "tool.execution.dispatched"
    TOOL_EXECUTION_ACKNOWLEDGED = "tool.execution.acknowledged"
    TOOL_EXECUTION_NOT_DISPATCHED = "tool.execution.not_dispatched"
    SIDE_EFFECT_OBSERVED = "side_effect.observed"
    SIDE_EFFECT_VERIFIED = "side_effect.verified"
    SIDE_EFFECT_UNVERIFIED = "side_effect.unverified"
    SIDE_EFFECT_TIMED_OUT = "side_effect.timed_out"
    SIDE_EFFECT_CONFLICT_DETECTED = "side_effect.conflict_detected"
    RESOURCE_OBSERVED = "resource.observed"
    ACTION_NORMALIZED = "action.normalized"
    LINEAGE_ALERT_CREATED = "lineage.alert.created"
    RECORDER_DEGRADED = "recorder.degraded"
    PROJECTION_REBUILT = "projection.rebuilt"
    INTEGRITY_VERIFICATION_FAILED = "integrity.verification.failed"


class PrincipalType(StrEnum):
    """Principal categories tracked in the event model."""

    HUMAN = "human"
    SERVICE = "service"
    AGENT = "agent"
    MODEL = "model"
    WORKLOAD = "workload"
    CREDENTIAL = "credential"
    UNKNOWN = "unknown"


class ResourceType(StrEnum):
    """Resource categories used by normalized payloads."""

    FILE = "file"
    URL = "url"
    NETWORK_DESTINATION = "network_destination"
    PROCESS = "process"
    HOST = "host"
    IDENTITY = "identity"
    CLOUD_RESOURCE = "cloud_resource"
    DATABASE_RECORD = "database_record"
    MESSAGE = "message"
    SECRET = "secret"
    UNKNOWN = "unknown"


class Sensitivity(StrEnum):
    """Data sensitivity labels for event classification."""

    PUBLIC = "public"
    INTERNAL = "internal"
    CONFIDENTIAL = "confidential"
    RESTRICTED = "restricted"
    SECRET = "secret"
    UNKNOWN = "unknown"


class TrustLevel(StrEnum):
    """Trust labels for sources and destinations."""

    TRUSTED = "trusted"
    UNTRUSTED = "untrusted"
    LOCAL = "local"
    EXTERNAL = "external"
    UNKNOWN = "unknown"


class VerificationStatus(StrEnum):
    """Evidence verification states tracked without implying certainty."""

    UNKNOWN = "unknown"
    UNVERIFIED = "unverified"
    TIMED_OUT = "timed_out"
    CONFLICTING = "conflicting"
    OBSERVED = "observed"
    VERIFIED = "verified"


class EvidenceRelationship(StrEnum):
    """Relationship between a subject event and corroborating evidence."""

    CORROBORATES = "corroborates"
    CONTRADICTS = "contradicts"
    OBSERVES = "observes"
    LIMITS = "limits"


class CorroborationType(StrEnum):
    """Source category for corroborating evidence."""

    INDEPENDENT_OBSERVER = "independent_observer"
    POST_ACTION_READBACK = "post_action_readback"
    FIXTURE_ORACLE = "fixture_oracle"
    SELF_REPORTED = "self_reported"
    UNKNOWN = "unknown"


class FrozenDomainModel(BaseModel):
    """Base model for immutable domain value objects."""

    model_config = ConfigDict(extra="forbid", frozen=True)


class Source(FrozenDomainModel):
    """Component that observed or produced an event."""

    component: str = Field(min_length=1)
    instance_id: str = Field(min_length=1)
    version: str = Field(min_length=1)


class Correlation(FrozenDomainModel):
    """Trace, span, run, and session correlation identifiers."""

    trace_id: str = Field(min_length=1)
    run_id: str = Field(min_length=1)
    span_id: str | None = Field(default=None, min_length=1)
    session_id: str | None = Field(default=None, min_length=1)


class Causality(FrozenDomainModel):
    """Causal position of one event in a lineage graph."""

    root_event_id: str = Field(min_length=1)
    sequence: int = Field(ge=0)
    parent_event_id: str | None = Field(default=None, min_length=1)


class Principal(FrozenDomainModel):
    """Principal evidence attached to an event."""

    principal_id: str = Field(min_length=1)
    principal_type: PrincipalType
    on_behalf_of: str | None = Field(default=None, min_length=1)
    model_id: str | None = Field(default=None, min_length=1)
    credential_id: str | None = Field(default=None, min_length=1)


class Classification(FrozenDomainModel):
    """Sensitivity and trust labels for the event context."""

    sensitivity: Sensitivity = Sensitivity.UNKNOWN
    trust: TrustLevel = TrustLevel.UNKNOWN


class IntegrityMetadata(FrozenDomainModel):
    """Integrity fields reserved for later journal hash-chain work."""

    canonicalization: str = CANONICALIZATION_VERSION
    previous_event_hash: str | None = Field(default=None, min_length=1)
    event_hash: str | None = Field(default=None, min_length=1)


class EvidenceLink(FrozenDomainModel):
    """Typed payload object linking a claim to corroborating evidence."""

    subject_event_id: str = Field(min_length=1)
    relationship: EvidenceRelationship
    evidence_event_id: str = Field(min_length=1)
    corroboration_type: CorroborationType
    observer_identity: str = Field(min_length=1)
    confidence: float = Field(ge=0.0, le=1.0)
    verification_status: VerificationStatus
    limitations: tuple[str, ...] = ()

    @field_validator("limitations")
    @classmethod
    def require_nonempty_limitations(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        """Keep limitation entries useful for incident review."""

        if any(not item for item in value):
            raise ValueError("limitations cannot contain empty strings")
        return value

    def as_payload(self) -> JsonObject:
        """Return a JSON-compatible event payload fragment."""

        return cast(JsonObject, model_json(self))


class EventEnvelope(FrozenDomainModel):
    """Immutable versioned lineage event envelope."""

    documented_root_event_types: ClassVar[frozenset[str]] = frozenset(
        {
            EventType.AGENT_INTENT_RECORDED.value,
            EventType.AGENT_RUN_STARTED.value,
            EventType.RECORDER_DEGRADED.value,
        }
    )

    spec_version: Literal["actionlineage.dev/v1alpha1"] = SPEC_VERSION
    event_id: str = Field(min_length=1)
    event_type: EventType | str = Field(min_length=1)
    occurred_at: datetime
    observed_at: datetime
    source: Source
    correlation: Correlation
    causality: Causality
    principal: Principal
    classification: Classification
    payload: dict[str, Any] = Field(default_factory=dict)
    integrity: IntegrityMetadata = Field(default_factory=IntegrityMetadata)

    @field_validator("occurred_at", "observed_at")
    @classmethod
    def require_aware_utc(cls, value: datetime) -> datetime:
        """Normalize aware datetimes to UTC and reject naive timestamps."""

        if value.tzinfo is None or value.tzinfo.utcoffset(value) is None:
            raise ValueError("event timestamps must be timezone-aware")
        return value.astimezone(UTC)

    @field_validator("payload")
    @classmethod
    def require_json_payload(cls, value: dict[str, Any]) -> dict[str, Any]:
        """Reject payload values that cannot cross the JSON event boundary."""

        validate_json_value(value)
        return value

    @model_validator(mode="after")
    def validate_causality(self) -> EventEnvelope:
        event_type = event_type_value(self.event_type)
        is_documented_root = event_type in self.documented_root_event_types

        if self.causality.parent_event_id is None and not is_documented_root:
            raise ValueError("non-root events require parent_event_id")

        if self.causality.parent_event_id is None and self.causality.root_event_id != self.event_id:
            raise ValueError("root events must set root_event_id to event_id")

        return self


def event_type_value(event_type: EventType | str) -> str:
    """Return the stable string value for a known or future event type."""

    if isinstance(event_type, EventType):
        return event_type.value
    return event_type


def model_json(value: BaseModel) -> dict[str, Any]:
    """Dump a Pydantic model using JSON-compatible values."""

    dumped = value.model_dump(mode="json")
    if not isinstance(dumped, dict):
        raise TypeError("expected model dump to produce an object")
    return dumped


def validate_json_value(value: Any) -> None:
    """Validate that a value can be represented in JSON."""

    if value is None or isinstance(value, str | int | float | bool):
        return

    if isinstance(value, list):
        for item in value:
            validate_json_value(item)
        return

    if isinstance(value, dict):
        for key, item in value.items():
            if not isinstance(key, str):
                raise ValueError("payload object keys must be strings")
            validate_json_value(item)
        return

    raise ValueError(f"payload contains unsupported JSON value type: {type(value).__name__}")
