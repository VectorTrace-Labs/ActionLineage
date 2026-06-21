"""Side-effect verification payload helpers."""

from __future__ import annotations

from dataclasses import dataclass

from actionlineage.domain import (
    CorroborationType,
    EventType,
    EvidenceLink,
    EvidenceRelationship,
    VerificationStatus,
)
from actionlineage.domain.events import JsonObject
from actionlineage.observers.local import ObservationOutcome, ObserverOutcome


@dataclass(frozen=True, slots=True)
class VerificationDecision:
    """One verification result payload and event type."""

    event_type: EventType
    evidence_link: EvidenceLink
    outcome: ObserverOutcome

    def as_payload(self) -> JsonObject:
        return {"evidence_link": self.evidence_link.as_payload()}


def verify_observation(
    *,
    subject_event_id: str,
    evidence_event_id: str,
    observation: ObservationOutcome,
    confidence: float,
    corroboration_type: CorroborationType = CorroborationType.INDEPENDENT_OBSERVER,
) -> VerificationDecision:
    """Create a verification decision from an observer outcome."""

    status = _verification_status_for_observation(observation)
    relationship = (
        EvidenceRelationship.CONTRADICTS
        if status == VerificationStatus.CONFLICTING
        else EvidenceRelationship.CORROBORATES
        if status == VerificationStatus.VERIFIED
        else EvidenceRelationship.LIMITS
    )
    return VerificationDecision(
        event_type=_event_type_for_status(status),
        outcome=observation.outcome,
        evidence_link=EvidenceLink(
            subject_event_id=subject_event_id,
            relationship=relationship,
            evidence_event_id=evidence_event_id,
            corroboration_type=corroboration_type,
            observer_identity=observation.observer_identity,
            confidence=confidence,
            verification_status=status,
            limitations=observation.limitations,
        ),
    )


def self_reported_verification(
    *,
    subject_event_id: str,
    observer_identity: str,
    confidence: float = 0.2,
    limitations: tuple[str, ...] = ("self-reported tool acknowledgement only",),
) -> VerificationDecision:
    """Represent explicitly identified self-reported evidence."""

    return VerificationDecision(
        event_type=EventType.SIDE_EFFECT_UNVERIFIED,
        outcome=ObserverOutcome.UNVERIFIED,
        evidence_link=EvidenceLink(
            subject_event_id=subject_event_id,
            relationship=EvidenceRelationship.LIMITS,
            evidence_event_id=subject_event_id,
            corroboration_type=CorroborationType.SELF_REPORTED,
            observer_identity=observer_identity,
            confidence=confidence,
            verification_status=VerificationStatus.UNVERIFIED,
            limitations=limitations,
        ),
    )


def _verification_status_for_observation(observation: ObservationOutcome) -> VerificationStatus:
    if observation.outcome == ObserverOutcome.OBSERVED:
        return VerificationStatus.VERIFIED
    if observation.outcome == ObserverOutcome.TIMED_OUT:
        return VerificationStatus.TIMED_OUT
    if observation.outcome == ObserverOutcome.CONFLICTING:
        return VerificationStatus.CONFLICTING
    return VerificationStatus.UNVERIFIED


def _event_type_for_status(status: VerificationStatus) -> EventType:
    if status == VerificationStatus.VERIFIED:
        return EventType.SIDE_EFFECT_VERIFIED
    if status == VerificationStatus.TIMED_OUT:
        return EventType.SIDE_EFFECT_TIMED_OUT
    if status == VerificationStatus.CONFLICTING:
        return EventType.SIDE_EFFECT_CONFLICT_DETECTED
    return EventType.SIDE_EFFECT_UNVERIFIED
