from __future__ import annotations

from actionlineage.domain import (
    Classification,
    Correlation,
    EventType,
    FixedClock,
    FixedIdGenerator,
    Principal,
    PrincipalType,
    Sensitivity,
    Source,
    TrustLevel,
)
from actionlineage.evidence import EvidenceNormalizer
from tests.domain.test_events import BASE_TIME


def test_evidence_normalizer_assigns_causal_sequence_and_root() -> None:
    normalizer = EvidenceNormalizer(
        correlation=Correlation(trace_id="trace_normalized", run_id="run_normalized"),
        source=Source(component="unit-adapter", instance_id="adapter_01", version="0.0.0"),
        principal=Principal(principal_id="agent_demo", principal_type=PrincipalType.AGENT),
        classification=Classification(sensitivity=Sensitivity.INTERNAL, trust=TrustLevel.LOCAL),
        clock=FixedClock(BASE_TIME),
        id_generator=FixedIdGenerator(("evt_root", "evt_child")),
    )

    root = normalizer.record(EventType.AGENT_INTENT_RECORDED, {"intent": "demo"})
    child = normalizer.record(EventType.TOOL_EXECUTION_REQUESTED, {"tool_identity": {"name": "x"}})

    assert root.causality.parent_event_id is None
    assert root.causality.root_event_id == "evt_root"
    assert child.causality.parent_event_id == "evt_root"
    assert child.causality.root_event_id == "evt_root"
    assert child.causality.sequence == 1


def test_evidence_normalizer_requires_root_when_first_event_is_not_root() -> None:
    normalizer = EvidenceNormalizer(
        correlation=Correlation(trace_id="trace_normalized", run_id="run_normalized"),
        source=Source(component="unit-adapter", instance_id="adapter_01", version="0.0.0"),
        principal=Principal(principal_id="agent_demo", principal_type=PrincipalType.AGENT),
        classification=Classification(sensitivity=Sensitivity.INTERNAL, trust=TrustLevel.LOCAL),
        clock=FixedClock(BASE_TIME),
        id_generator=FixedIdGenerator(("evt_child",)),
    )

    try:
        normalizer.record(
            EventType.TOOL_EXECUTION_REQUESTED,
            {"tool_identity": {"name": "x"}},
            parent_event_id="evt_prior",
        )
    except ValueError as exc:
        assert "root_event_id is required" in str(exc)
    else:
        raise AssertionError("expected root event validation failure")
