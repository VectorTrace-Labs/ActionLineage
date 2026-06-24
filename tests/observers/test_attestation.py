from __future__ import annotations

from datetime import date

import pytest

from actionlineage.domain import (
    CorroborationType,
    EventType,
    ResourceType,
    TrustLevel,
    VerificationStatus,
)
from actionlineage.observers import (
    AttestationEvidenceKind,
    IndependenceBoundary,
    IndependenceBoundaryStatus,
    ObservationOutcome,
    ObserverAttestationDeclaration,
    ObserverAttestationError,
    ObserverOutcome,
    independent_claim_rejection_reasons,
    observer_attestation_declaration_from_dict,
    verify_observation,
)

REVIEW_DATE = date(2026, 6, 1)
REFERENCE_DATE = date(2026, 6, 24)


def observed_file_outcome(*, observer_identity: str = "edr-prod-01") -> ObservationOutcome:
    return ObservationOutcome(
        observer_identity=observer_identity,
        resource_type=ResourceType.FILE,
        resource_identifier="/srv/demo/report.txt",
        outcome=ObserverOutcome.OBSERVED,
        observed_state={"path": "/srv/demo/report.txt", "operation": "write"},
        limitations=("reviewed sensor event",),
        trust=TrustLevel.EXTERNAL,
    )


def independent_boundaries() -> dict[IndependenceBoundary, IndependenceBoundaryStatus]:
    return {boundary: IndependenceBoundaryStatus.INDEPENDENT for boundary in IndependenceBoundary}


def reviewed_declaration(
    *,
    observer_identity: str = "edr-prod-01",
    reviewed_at: date = REVIEW_DATE,
    shared_dependencies: tuple[str, ...] = (),
    subject_action_types: tuple[str, ...] = ("file.write",),
    resource_types: tuple[ResourceType, ...] = (ResourceType.FILE,),
    evidence_kind: AttestationEvidenceKind = AttestationEvidenceKind.INDEPENDENT_LIVE_TELEMETRY,
    boundaries: dict[
        IndependenceBoundary,
        IndependenceBoundaryStatus,
    ]
    | None = None,
) -> ObserverAttestationDeclaration:
    return ObserverAttestationDeclaration(
        observer_identity=observer_identity,
        producer_identity="Reviewed EDR Adapter",
        collection_method="endpoint sensor event stream",
        subject_action_types=subject_action_types,
        resource_types=resource_types,
        evidence_kind=evidence_kind,
        independence_boundaries=boundaries or independent_boundaries(),
        shared_dependencies=shared_dependencies,
        blind_spots=("offline hosts",),
        failure_modes=("collector delay", "dropped endpoint events"),
        tamper_assumptions=("sensor source retention is managed outside ActionLineage",),
        retention="30 days in reviewed EDR tenant",
        redaction_scopes=("process metadata only",),
        policy_version="observer-attestation-v1",
        owner="security-platform",
        reviewed_at=reviewed_at,
        limitations=("endpoint sensor cannot see historical writes before enrollment",),
    )


def test_independent_observer_claim_requires_attestation() -> None:
    observation = observed_file_outcome()

    with pytest.raises(
        ObserverAttestationError,
        match="missing reviewed observer attestation declaration",
    ):
        verify_observation(
            subject_event_id="evt_ack",
            evidence_event_id="evt_observed",
            observation=observation,
            confidence=0.95,
            corroboration_type=CorroborationType.INDEPENDENT_OBSERVER,
            subject_action_type="file.write",
            subject_resource_type=ResourceType.FILE,
            attestation_reference_date=REFERENCE_DATE,
        )


def test_independent_observer_claim_accepts_reviewed_in_scope_attestation() -> None:
    observation = observed_file_outcome()
    decision = verify_observation(
        subject_event_id="evt_ack",
        evidence_event_id="evt_observed",
        observation=observation,
        confidence=0.95,
        corroboration_type=CorroborationType.INDEPENDENT_OBSERVER,
        attestation=reviewed_declaration(),
        subject_action_type="file.write",
        subject_resource_type=ResourceType.FILE,
        attestation_reference_date=REFERENCE_DATE,
    )

    assert decision.event_type == EventType.SIDE_EFFECT_VERIFIED
    assert decision.evidence_link.corroboration_type == CorroborationType.INDEPENDENT_OBSERVER
    assert decision.evidence_link.verification_status == VerificationStatus.VERIFIED


@pytest.mark.parametrize(
    ("declaration", "reason"),
    (
        (
            reviewed_declaration(reviewed_at=date(2025, 1, 1)),
            "observer attestation declaration is stale",
        ),
        (
            reviewed_declaration(shared_dependencies=("same cloud account",)),
            "observer attestation declares shared dependencies",
        ),
        (
            reviewed_declaration(subject_action_types=("process.start",)),
            "subject action type is outside observer attestation scope",
        ),
        (
            reviewed_declaration(
                boundaries={
                    **independent_boundaries(),
                    IndependenceBoundary.ADMINISTRATIVE_CONTROL_PLANE: (
                        IndependenceBoundaryStatus.SHARED
                    ),
                }
            ),
            "observer attestation administrative_control_plane boundary is shared",
        ),
    ),
)
def test_independent_observer_claim_rejects_stale_shared_or_out_of_scope_declaration(
    declaration: ObserverAttestationDeclaration,
    reason: str,
) -> None:
    reasons = independent_claim_rejection_reasons(
        attestation=declaration,
        observation=observed_file_outcome(),
        subject_action_type="file.write",
        subject_resource_type=ResourceType.FILE,
        reference_date=REFERENCE_DATE,
    )

    assert reason in reasons


def test_attestation_declaration_from_dict_round_trips_review_fields() -> None:
    data = reviewed_declaration().as_dict()
    parsed = observer_attestation_declaration_from_dict(data)

    assert parsed == reviewed_declaration()
    assert parsed.as_dict()["reviewed_at"] == REVIEW_DATE.isoformat()
    assert parsed.as_dict()["independence_boundaries"]["tool"] == "independent"
