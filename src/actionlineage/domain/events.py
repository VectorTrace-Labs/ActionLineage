"""Versioned lineage event envelope and core value objects."""

from __future__ import annotations

import math
from collections.abc import Iterable, Iterator, Mapping, Sequence
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, ClassVar, Literal, NoReturn, Self, SupportsIndex, cast

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_serializer,
    field_validator,
    model_validator,
)

from actionlineage.domain.canonicalization import CANONICALIZATION_VERSION

SPEC_VERSION: Literal["actionlineage.dev/v1alpha1"] = "actionlineage.dev/v1alpha1"
DEFAULT_JSON_MAX_DEPTH = 64
DEFAULT_JSON_MAX_OBJECT_MEMBERS = 4096
DEFAULT_JSON_MAX_ARRAY_LENGTH = 4096

type JsonScalar = str | int | float | bool | None
type JsonValue = JsonScalar | list[JsonValue] | dict[str, JsonValue]
type JsonObject = dict[str, JsonValue]


class FrozenJsonDict(Mapping[str, Any]):
    """Immutable JSON object container backed by private frozen storage."""

    def _immutable(self) -> NoReturn:
        raise TypeError("event payload JSON objects are immutable")

    def __init__(self, values: Mapping[str, Any]) -> None:
        self._values = dict(values)

    def __getitem__(self, key: str) -> Any:
        return self._values[key]

    def __iter__(self) -> Iterator[str]:
        return iter(self._values)

    def __len__(self) -> int:
        return len(self._values)

    def __eq__(self, other: object) -> bool:
        if isinstance(other, Mapping):
            return dict(self.items()) == dict(other.items())
        return False

    def __setitem__(self, key: str, value: Any) -> None:
        self._immutable()

    def __delitem__(self, key: str) -> None:
        self._immutable()

    def clear(self) -> None:
        self._immutable()

    def pop(self, key: str, default: Any = None) -> Any:
        self._immutable()

    def popitem(self) -> tuple[str, Any]:
        self._immutable()

    def setdefault(self, key: str, default: Any = None) -> Any:
        self._immutable()

    def update(self, *args: object, **kwargs: Any) -> None:
        self._immutable()

    def __ior__(self, other: Any) -> Self:
        self._immutable()

    def copy(self) -> dict[str, Any]:
        """Return a mutable JSON-compatible copy."""

        return cast(dict[str, Any], thaw_json_value(self))


class FrozenJsonList(Sequence[Any]):
    """Immutable JSON array container backed by a private tuple."""

    def _immutable(self) -> NoReturn:
        raise TypeError("event payload JSON arrays are immutable")

    def __init__(self, values: Iterable[Any]) -> None:
        self._values = tuple(values)

    def __getitem__(self, index: SupportsIndex | slice) -> Any:
        return self._values[index]

    def __iter__(self) -> Iterator[Any]:
        return iter(self._values)

    def __len__(self) -> int:
        return len(self._values)

    def __eq__(self, other: object) -> bool:
        if isinstance(other, Sequence) and not isinstance(other, str | bytes | bytearray):
            return list(self) == list(other)
        return False

    def __setitem__(self, index: object, value: Any) -> None:
        self._immutable()

    def __delitem__(self, index: object) -> None:
        self._immutable()

    def append(self, item: Any) -> None:
        self._immutable()

    def clear(self) -> None:
        self._immutable()

    def extend(self, iterable: Iterable[Any]) -> None:
        self._immutable()

    def insert(self, index: SupportsIndex, item: Any) -> None:
        self._immutable()

    def pop(self, index: SupportsIndex = -1) -> Any:
        self._immutable()

    def remove(self, value: Any) -> None:
        self._immutable()

    def reverse(self) -> None:
        self._immutable()

    def sort(self, *args: Any, **kwargs: Any) -> None:
        self._immutable()

    def __iadd__(self, value: Iterable[Any]) -> Self:
        self._immutable()

    def __imul__(self, value: SupportsIndex) -> Self:
        self._immutable()

    def copy(self) -> list[Any]:
        """Return a mutable JSON-compatible copy."""

        return cast(list[Any], thaw_json_value(self))


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
    payload: Mapping[str, Any] = Field(default_factory=dict)
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
    def require_json_payload(cls, value: Mapping[str, Any]) -> Mapping[str, Any]:
        """Reject payload values that cannot cross the JSON event boundary."""

        validate_json_value(value)
        return cast(Mapping[str, Any], freeze_json_value(value))

    @field_serializer("payload")
    def serialize_payload(self, value: Mapping[str, Any]) -> dict[str, Any]:
        """Serialize immutable payload containers as ordinary JSON objects."""

        return cast(dict[str, Any], thaw_json_value(value))

    def model_copy(
        self,
        *,
        update: Mapping[str, Any] | None = None,
        deep: bool = False,
    ) -> Self:
        """Copy through validation so trusted event state remains immutable."""

        copied = super().model_copy(update=update, deep=deep)
        return type(self).model_validate(copied.model_dump(mode="python"))

    @classmethod
    def model_construct(cls, _fields_set: set[str] | None = None, **values: Any) -> Self:
        """Construct through validation; raw trusted construction is intentionally unavailable."""

        return cls.model_validate(values)

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


def validate_json_value(
    value: Any,
    *,
    max_depth: int = DEFAULT_JSON_MAX_DEPTH,
    max_object_members: int = DEFAULT_JSON_MAX_OBJECT_MEMBERS,
    max_array_length: int = DEFAULT_JSON_MAX_ARRAY_LENGTH,
    _depth: int = 0,
) -> None:
    """Validate that a value can be represented in JSON."""

    if _depth > max_depth:
        raise ValueError(f"payload JSON depth exceeds {max_depth}")

    if isinstance(value, float) and not math.isfinite(value):
        raise ValueError("payload contains non-finite JSON number")

    if value is None or isinstance(value, str | int | float | bool):
        return

    if isinstance(value, Sequence) and not isinstance(value, str | bytes | bytearray):
        if len(value) > max_array_length:
            raise ValueError(f"payload JSON array exceeds {max_array_length} items")
        for item in value:
            validate_json_value(
                item,
                max_depth=max_depth,
                max_object_members=max_object_members,
                max_array_length=max_array_length,
                _depth=_depth + 1,
            )
        return

    if isinstance(value, Mapping):
        if len(value) > max_object_members:
            raise ValueError(f"payload JSON object exceeds {max_object_members} members")
        for key, item in value.items():
            if not isinstance(key, str):
                raise ValueError("payload object keys must be strings")
            validate_json_value(
                item,
                max_depth=max_depth,
                max_object_members=max_object_members,
                max_array_length=max_array_length,
                _depth=_depth + 1,
            )
        return

    raise ValueError(f"payload contains unsupported JSON value type: {type(value).__name__}")


def freeze_json_value(value: Any) -> Any:
    """Return a recursively immutable JSON-compatible value."""

    if value is None or isinstance(value, str | int | float | bool):
        return value

    if isinstance(value, Mapping):
        return FrozenJsonDict({key: freeze_json_value(item) for key, item in value.items()})

    if isinstance(value, Sequence) and not isinstance(value, str | bytes | bytearray):
        return FrozenJsonList(freeze_json_value(item) for item in value)

    raise ValueError(f"payload contains unsupported JSON value type: {type(value).__name__}")


def thaw_json_value(value: Any) -> Any:
    """Return ordinary dict/list JSON containers from immutable event values."""

    if isinstance(value, Mapping):
        return {key: thaw_json_value(item) for key, item in value.items()}

    if isinstance(value, Sequence) and not isinstance(value, str | bytes | bytearray):
        return [thaw_json_value(item) for item in value]

    return value
