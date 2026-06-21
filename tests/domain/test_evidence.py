from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

from actionlineage.domain import (
    CorroborationType,
    EventEnvelope,
    EventType,
    EvidenceLink,
    EvidenceRelationship,
    VerificationStatus,
    serialize_event,
)
from tests.domain.test_events import build_event


def test_neutral_evidence_plane_event_types_serialize_as_v1alpha1_events() -> None:
    event = build_event(
        event_id="evt_intent",
        event_type=EventType.AGENT_INTENT_RECORDED,
        root_event_id="evt_intent",
        parent_event_id=None,
        sequence=0,
        payload={"intent": {"summary": "review local fixture evidence"}},
    )

    serialized = json.loads(serialize_event(event))
    parsed = EventEnvelope.model_validate(serialized)

    assert serialized["spec_version"] == "actionlineage.dev/v1alpha1"
    assert serialized["event_type"] == "agent.intent.recorded"
    assert parsed.event_type == EventType.AGENT_INTENT_RECORDED


def test_evidence_link_payload_represents_verification_without_envelope_changes() -> None:
    link = EvidenceLink(
        subject_event_id="evt_tool_ack",
        relationship=EvidenceRelationship.CORROBORATES,
        evidence_event_id="evt_receiver_observed",
        corroboration_type=CorroborationType.INDEPENDENT_OBSERVER,
        observer_identity="local_receiver_fixture",
        confidence=0.95,
        verification_status=VerificationStatus.VERIFIED,
        limitations=("local deterministic fixture only",),
    )
    event = build_event(
        event_id="evt_verified",
        event_type=EventType.SIDE_EFFECT_VERIFIED,
        root_event_id="evt_intent",
        parent_event_id="evt_receiver_observed",
        sequence=3,
        payload={"evidence_link": link.as_payload()},
    )

    serialized = json.loads(serialize_event(event))
    evidence_link = serialized["payload"]["evidence_link"]

    assert evidence_link["subject_event_id"] == "evt_tool_ack"
    assert evidence_link["evidence_event_id"] == "evt_receiver_observed"
    assert evidence_link["verification_status"] == "verified"
    assert evidence_link["corroboration_type"] == "independent_observer"


def test_evidence_link_requires_bounded_confidence_and_nonempty_limitations() -> None:
    with pytest.raises(ValidationError):
        EvidenceLink(
            subject_event_id="evt_tool_ack",
            relationship=EvidenceRelationship.CORROBORATES,
            evidence_event_id="evt_receiver_observed",
            corroboration_type=CorroborationType.INDEPENDENT_OBSERVER,
            observer_identity="local_receiver_fixture",
            confidence=1.5,
            verification_status=VerificationStatus.VERIFIED,
        )

    with pytest.raises(ValidationError, match="limitations cannot contain empty strings"):
        EvidenceLink(
            subject_event_id="evt_tool_ack",
            relationship=EvidenceRelationship.LIMITS,
            evidence_event_id="evt_timeout",
            corroboration_type=CorroborationType.FIXTURE_ORACLE,
            observer_identity="local_fixture",
            confidence=0.5,
            verification_status=VerificationStatus.TIMED_OUT,
            limitations=("",),
        )
