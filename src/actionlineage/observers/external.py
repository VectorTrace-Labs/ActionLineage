"""External OS, EDR, and sensor-feed observer declarations."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
from enum import StrEnum
from typing import cast

from actionlineage.domain import RedactionPolicy, ResourceType, TrustLevel
from actionlineage.domain.events import JsonObject
from actionlineage.observers.local import ObservationOutcome, ObserverOutcome


class ExternalSensorKind(StrEnum):
    """External sensor families understood by ActionLineage declarations."""

    EBPF = "ebpf"
    EDR = "edr"
    FILE_SENSOR = "file_sensor"
    NETWORK_SENSOR = "network_sensor"
    OS_AUDIT = "os_audit"
    PROCESS_SENSOR = "process_sensor"


@dataclass(frozen=True, slots=True)
class ExternalSensorDeclaration:
    """Trust-boundary declaration for an optional external sensor feed."""

    sensor_id: str
    kind: ExternalSensorKind
    producer: str
    capabilities: tuple[str, ...]
    limitations: tuple[str, ...]
    trust: TrustLevel = TrustLevel.EXTERNAL

    def as_dict(self) -> dict[str, object]:
        """Return a JSON-compatible sensor declaration."""

        return {
            "sensor_id": self.sensor_id,
            "kind": self.kind.value,
            "producer": self.producer,
            "trust": self.trust.value,
            "capabilities": list(self.capabilities),
            "limitations": list(self.limitations),
            "collection_model": "external_optional_adapter",
        }


@dataclass(frozen=True, slots=True)
class ExternalSensorObservationRecord:
    """One external sensor observation before normalization."""

    resource_type: ResourceType
    resource_identifier: str
    outcome: ObserverOutcome
    observed_state: JsonObject
    limitations: tuple[str, ...] = ()

    def as_dict(self) -> dict[str, object]:
        """Return a JSON-compatible observation record."""

        return {
            "resource_type": self.resource_type.value,
            "resource_identifier": self.resource_identifier,
            "outcome": self.outcome.value,
            "observed_state": deepcopy(self.observed_state),
            "limitations": list(self.limitations),
        }


@dataclass(frozen=True, slots=True)
class ExternalSensorFeedObserver:
    """Normalize reviewed external sensor records into observation outcomes."""

    declaration: ExternalSensorDeclaration
    redaction_policy: RedactionPolicy = field(default_factory=RedactionPolicy)

    def observe(self, record: ExternalSensorObservationRecord) -> ObservationOutcome:
        """Return a redacted observation outcome from one external sensor record."""

        observed_state = cast(JsonObject, self.redaction_policy.apply(record.observed_state))
        limitations = (
            *self.declaration.limitations,
            *record.limitations,
            "external sensor feed; collection adapter is outside the domain core",
        )
        return ObservationOutcome(
            observer_identity=self.declaration.sensor_id,
            resource_type=record.resource_type,
            resource_identifier=record.resource_identifier,
            outcome=record.outcome,
            observed_state={
                "sensor": cast(JsonObject, self.declaration.as_dict()),
                "record": observed_state,
            },
            limitations=limitations,
            trust=self.declaration.trust,
        )


def external_sensor_declaration_from_dict(data: dict[str, object]) -> ExternalSensorDeclaration:
    """Parse a sensor declaration from a JSON-compatible dictionary."""

    return ExternalSensorDeclaration(
        sensor_id=_required_string(data, "sensor_id"),
        kind=ExternalSensorKind(_required_string(data, "kind")),
        producer=_required_string(data, "producer"),
        trust=TrustLevel(_optional_string(data, "trust") or TrustLevel.EXTERNAL.value),
        capabilities=_string_tuple(data.get("capabilities"), field="capabilities"),
        limitations=_string_tuple(data.get("limitations"), field="limitations"),
    )


def external_sensor_observation_from_dict(
    data: dict[str, object],
) -> ExternalSensorObservationRecord:
    """Parse an external sensor observation record from JSON-compatible data."""

    observed_state = data.get("observed_state")
    if not isinstance(observed_state, dict):
        raise ValueError("external sensor observed_state must be an object")
    return ExternalSensorObservationRecord(
        resource_type=ResourceType(_required_string(data, "resource_type")),
        resource_identifier=_required_string(data, "resource_identifier"),
        outcome=ObserverOutcome(_required_string(data, "outcome")),
        observed_state=cast(JsonObject, observed_state),
        limitations=_string_tuple(data.get("limitations"), field="limitations"),
    )


def _required_string(data: dict[str, object], field: str) -> str:
    value = data.get(field)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"external sensor field must be a nonempty string: {field}")
    return value


def _optional_string(data: dict[str, object], field: str) -> str | None:
    value = data.get(field)
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"external sensor field must be a string: {field}")
    return value


def _string_tuple(value: object, *, field: str) -> tuple[str, ...]:
    if value is None:
        return ()
    if not isinstance(value, list):
        raise ValueError(f"external sensor field must be a string list: {field}")
    strings: list[str] = []
    for item in value:
        if not isinstance(item, str) or not item.strip():
            raise ValueError(f"external sensor field must contain strings: {field}")
        strings.append(item)
    return tuple(strings)
