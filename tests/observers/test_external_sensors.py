from __future__ import annotations

from actionlineage.domain import ResourceType, TrustLevel, VerificationStatus
from actionlineage.observers import (
    ExternalSensorDeclaration,
    ExternalSensorFeedObserver,
    ExternalSensorKind,
    ExternalSensorObservationRecord,
    ObserverOutcome,
    external_sensor_declaration_from_dict,
    external_sensor_observation_from_dict,
)


def test_external_sensor_feed_redacts_observed_state_before_payload() -> None:
    declaration = ExternalSensorDeclaration(
        sensor_id="edr-prod-01",
        kind=ExternalSensorKind.EDR,
        producer="Reviewed EDR Adapter",
        capabilities=("process_start", "network_connection"),
        limitations=("fixture sensor feed",),
        trust=TrustLevel.EXTERNAL,
    )
    observer = ExternalSensorFeedObserver(declaration=declaration)
    outcome = observer.observe(
        ExternalSensorObservationRecord(
            resource_type=ResourceType.PROCESS,
            resource_identifier="pid:4242",
            outcome=ObserverOutcome.OBSERVED,
            observed_state={
                "pid": 4242,
                "process": "curl",
                "authorization": "Bearer raw-secret-value",
            },
        )
    )
    payload = outcome.as_payload()

    assert outcome.verification_status == VerificationStatus.OBSERVED
    assert payload["observer_identity"] == "edr-prod-01"
    assert payload["trust"] == "external"
    assert payload["observed_state"]["record"]["authorization"]["marker"].startswith(
        "actionlineage.redacted"
    )
    assert "external sensor feed" in payload["limitations"][-1]


def test_external_sensor_unavailable_remains_unverified() -> None:
    declaration = ExternalSensorDeclaration(
        sensor_id="ebpf-node-01",
        kind=ExternalSensorKind.EBPF,
        producer="Reviewed eBPF Adapter",
        capabilities=("file_write",),
        limitations=("node-local feed",),
    )
    outcome = ExternalSensorFeedObserver(declaration=declaration).observe(
        ExternalSensorObservationRecord(
            resource_type=ResourceType.FILE,
            resource_identifier="/tmp/demo.txt",
            outcome=ObserverOutcome.UNAVAILABLE,
            observed_state={"status": "collector_unavailable"},
            limitations=("collector process unavailable",),
        )
    )

    assert outcome.verification_status == VerificationStatus.UNVERIFIED
    assert outcome.event_type.value == "side_effect.unverified"
    assert "collector process unavailable" in outcome.limitations


def test_external_sensor_record_as_dict_returns_defensive_observed_state_copy() -> None:
    record = ExternalSensorObservationRecord(
        resource_type=ResourceType.FILE,
        resource_identifier="/tmp/demo.txt",
        outcome=ObserverOutcome.OBSERVED,
        observed_state={"nested": {"status": "original"}},
    )
    data = record.as_dict()
    observed_state = data["observed_state"]
    assert isinstance(observed_state, dict)
    nested = observed_state["nested"]
    assert isinstance(nested, dict)

    nested["status"] = "tampered"

    repeated_state = record.as_dict()["observed_state"]
    assert isinstance(repeated_state, dict)
    repeated_nested = repeated_state["nested"]
    assert isinstance(repeated_nested, dict)
    assert repeated_nested["status"] == "original"


def test_external_sensor_records_parse_from_json_compatible_dicts() -> None:
    declaration = external_sensor_declaration_from_dict(
        {
            "sensor_id": "auditd-host-01",
            "kind": "os_audit",
            "producer": "Reviewed audit adapter",
            "trust": "local",
            "capabilities": ["file_write"],
            "limitations": ["audit policy dependent"],
        }
    )
    record = external_sensor_observation_from_dict(
        {
            "resource_type": "file",
            "resource_identifier": "/var/tmp/example",
            "outcome": "conflicting",
            "observed_state": {"operation": "write", "result": "denied"},
            "limitations": ["event stream replay fixture"],
        }
    )

    assert declaration.kind == ExternalSensorKind.OS_AUDIT
    assert declaration.trust == TrustLevel.LOCAL
    assert record.outcome == ObserverOutcome.CONFLICTING
    assert record.resource_type == ResourceType.FILE
