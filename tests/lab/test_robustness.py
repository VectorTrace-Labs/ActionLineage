from __future__ import annotations

import json
from collections.abc import Mapping

from actionlineage.demo import run_demo
from actionlineage.demo.scenario import build_demo_events
from actionlineage.domain import EventType, event_to_dict
from actionlineage.lab import (
    MutationStrategy,
    ReplayCase,
    ScenarioManifest,
    build_mutation_cases,
    load_replay_case_from_journal,
    minimize_counterexample,
    mutate_events,
    score_detection_robustness,
    write_minimized_counterexample,
)
from tests.detection.test_sequence import verified_file_read_rule


def test_replay_scorecard_survives_benign_distractor_and_rejects_unverified_variant() -> None:
    events = build_demo_events()
    benign = events[-1].model_copy(
        update={
            "event_id": "evt_demo_benign",
            "event_type": EventType.RESOURCE_OBSERVED,
            "payload": {"resource": {"type": "file", "path": "demo://benign.txt"}},
        }
    )
    unverified_variant = tuple(
        event
        for event in events
        if str(event.event_type) not in {"side_effect.observed", "side_effect.verified"}
    )
    scorecard = score_detection_robustness(
        verified_file_read_rule(),
        (
            ReplayCase(name="baseline", events=events, expected_match=True),
            ReplayCase(name="benign-distractor", events=(*events, benign), expected_match=True),
            ReplayCase(name="unverified-only", events=unverified_variant, expected_match=False),
        ),
    )

    assert scorecard.total_cases == 3
    assert scorecard.passed_cases == 3
    assert scorecard.failed_cases == ()
    assert scorecard.survival_rate == 1.0
    assert scorecard.false_positive_cases == ()
    assert scorecard.false_negative_cases == ()
    assert scorecard.evidence_completeness == 1.0


def test_mutation_cases_are_deterministic_and_semantics_declared() -> None:
    events = build_demo_events()
    cases = build_mutation_cases(
        events,
        expected_match=True,
        seed=7,
        strategies=(
            MutationStrategy.BENIGN_DISTRACTOR,
            MutationStrategy.DUPLICATE_EVENT,
            MutationStrategy.REORDER_UNRELATED,
            MutationStrategy.TIMESTAMP_SKEW,
            MutationStrategy.MISSING_OPTIONAL_FIELD,
            MutationStrategy.PATH_URL_NORMALIZATION,
        ),
    )
    repeated = build_mutation_cases(
        events,
        expected_match=True,
        seed=7,
        strategies=(
            MutationStrategy.BENIGN_DISTRACTOR,
            MutationStrategy.DUPLICATE_EVENT,
            MutationStrategy.REORDER_UNRELATED,
            MutationStrategy.TIMESTAMP_SKEW,
            MutationStrategy.MISSING_OPTIONAL_FIELD,
            MutationStrategy.PATH_URL_NORMALIZATION,
        ),
    )
    scorecard = score_detection_robustness(verified_file_read_rule(), cases)

    assert [case.as_dict() for case in cases] == [case.as_dict() for case in repeated]
    assert scorecard.failed_cases == ()
    assert scorecard.as_dict()["latency_seconds"] >= 0.0


def test_path_url_normalization_mutation_is_semantics_preserving() -> None:
    events = build_demo_events()
    url_event = events[0].model_copy(
        update={
            "event_id": "evt_url_variant",
            "causality": events[0].causality.model_copy(
                update={"root_event_id": "evt_url_variant"}
            ),
            "payload": {"destination": "http://receiver.local/collect"},
        }
    )
    mutation = mutate_events(
        (*events, url_event),
        strategy=MutationStrategy.PATH_URL_NORMALIZATION,
        expected_match=True,
        seed=23,
    )
    payload_text = json.dumps(
        [event_to_dict(event)["payload"] for event in mutation.events],
        sort_keys=True,
    )
    destination_values = [
        event.payload["destination"]
        for event in mutation.events
        if isinstance(event.payload, Mapping) and "destination" in event.payload
    ]

    assert mutation.expected_match is True
    assert mutation.semantic_property == (
        "path and URL representation variants preserve side-effect meaning"
    )
    assert "demo://workspace/./" in payload_text
    assert destination_values == ["http://receiver.local:80/collect"]
    assert not score_detection_robustness(
        verified_file_read_rule(),
        (mutation.as_replay_case(),),
    ).failed_cases


def test_outcome_uncertainty_mutation_changes_expected_result() -> None:
    mutation = mutate_events(
        build_demo_events(),
        strategy=MutationStrategy.OUTCOME_UNCERTAINTY,
        expected_match=True,
        seed=13,
    )

    assert mutation.expected_match is False
    assert mutation.semantic_property == "verified outcome is degraded to unverified evidence"
    assert not score_detection_robustness(
        verified_file_read_rule(),
        (mutation.as_replay_case(),),
    ).failed_cases


def test_replay_case_loads_from_canonical_journal(tmp_path) -> None:
    demo = run_demo(tmp_path / "demo")
    case = load_replay_case_from_journal(
        demo.journal_path,
        name="demo-journal",
        expected_match=True,
    )
    manifest = ScenarioManifest(name="demo-corpus", cases=(case,))

    assert case.events[0].event_id == "evt_demo_00"
    assert manifest.as_dict()["cases"][0]["name"] == "demo-journal"


def test_minimizer_preserves_failing_counterexample(tmp_path) -> None:
    rule = verified_file_read_rule()
    failing_events = tuple(
        event
        for event in build_demo_events()
        if str(event.event_type) not in {"side_effect.observed", "side_effect.verified"}
    )
    failing_case = ReplayCase(
        name="missing-verification",
        events=failing_events,
        expected_match=True,
    )

    minimized = minimize_counterexample(rule, failing_case)
    output_path = tmp_path / "counterexample.json"
    write_minimized_counterexample(output_path, minimized)
    written = json.loads(output_path.read_text(encoding="utf-8"))

    assert len(minimized.events) < len(failing_case.events)
    assert bool(score_detection_robustness(rule, (minimized,)).failed_cases)
    assert written["name"] == "missing-verification-minimized"
