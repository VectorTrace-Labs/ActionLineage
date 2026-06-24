"""Deterministic replay and robustness scoring."""

from __future__ import annotations

import json
import time
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import timedelta
from enum import StrEnum
from pathlib import Path

from actionlineage.detection import SequenceRule, evaluate_sequence_rule
from actionlineage.domain import EventEnvelope, EventType, event_to_dict
from actionlineage.journal import JournalError, LocalJournal


class MutationStrategy(StrEnum):
    """Deterministic mutation strategies for replay robustness tests."""

    BENIGN_DISTRACTOR = "benign_distractor"
    DUPLICATE_EVENT = "duplicate_event"
    REORDER_UNRELATED = "reorder_unrelated"
    TIMESTAMP_SKEW = "timestamp_skew"
    MISSING_OPTIONAL_FIELD = "missing_optional_field"
    PATH_URL_NORMALIZATION = "path_url_normalization"
    OUTCOME_UNCERTAINTY = "outcome_uncertainty"


@dataclass(frozen=True, slots=True)
class ReplayCase:
    """One deterministic replay case for a detection rule."""

    name: str
    events: tuple[EventEnvelope, ...]
    expected_match: bool

    def as_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "expected_match": self.expected_match,
            "event_ids": [event.event_id for event in self.events],
        }


@dataclass(frozen=True, slots=True)
class MutationResult:
    """One deterministic mutation and its semantic declaration."""

    name: str
    strategy: MutationStrategy
    semantic_property: str
    events: tuple[EventEnvelope, ...]
    expected_match: bool
    seed: int

    def as_replay_case(self) -> ReplayCase:
        return ReplayCase(name=self.name, events=self.events, expected_match=self.expected_match)

    def as_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "strategy": self.strategy.value,
            "semantic_property": self.semantic_property,
            "expected_match": self.expected_match,
            "seed": self.seed,
            "event_ids": [event.event_id for event in self.events],
        }


@dataclass(frozen=True, slots=True)
class ScenarioManifest:
    """Reviewed replay corpus manifest."""

    name: str
    cases: tuple[ReplayCase, ...]

    def as_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "cases": [case.as_dict() for case in self.cases],
        }


@dataclass(frozen=True, slots=True)
class RobustnessScorecard:
    """Detection survival score over replay cases."""

    rule_name: str
    total_cases: int
    passed_cases: int
    failed_cases: tuple[str, ...]
    false_positive_cases: tuple[str, ...] = ()
    false_negative_cases: tuple[str, ...] = ()
    evidence_completeness: float = 1.0
    latency_seconds: float = 0.0
    required_field_fragility: float = 0.0

    @property
    def survival_rate(self) -> float:
        if self.total_cases == 0:
            return 0.0
        return self.passed_cases / self.total_cases

    def as_dict(self) -> dict[str, object]:
        return {
            "rule_name": self.rule_name,
            "total_cases": self.total_cases,
            "passed_cases": self.passed_cases,
            "failed_cases": list(self.failed_cases),
            "false_positive_cases": list(self.false_positive_cases),
            "false_negative_cases": list(self.false_negative_cases),
            "evidence_completeness": self.evidence_completeness,
            "latency_seconds": self.latency_seconds,
            "required_field_fragility": self.required_field_fragility,
            "survival_rate": self.survival_rate,
        }


def score_detection_robustness(
    rule: SequenceRule,
    cases: tuple[ReplayCase, ...],
) -> RobustnessScorecard:
    """Replay deterministic cases and score expected detection behavior."""

    failed: list[str] = []
    false_positives: list[str] = []
    false_negatives: list[str] = []
    completeness_values: list[float] = []
    positive_cases = 0
    started_at = time.perf_counter()
    for case in cases:
        matches = evaluate_sequence_rule(case.events, rule)
        matched = bool(matches)
        if matched != case.expected_match:
            failed.append(case.name)
            if matched:
                false_positives.append(case.name)
            else:
                false_negatives.append(case.name)
        if case.expected_match:
            positive_cases += 1
            if matches:
                completeness_values.append(min(len(matches[0].event_ids) / len(rule.stages), 1.0))
            else:
                completeness_values.append(0.0)
    latency_seconds = time.perf_counter() - started_at
    evidence_completeness = (
        sum(completeness_values) / len(completeness_values) if completeness_values else 1.0
    )
    required_field_fragility = len(false_negatives) / positive_cases if positive_cases else 0.0
    return RobustnessScorecard(
        rule_name=rule.name,
        total_cases=len(cases),
        passed_cases=len(cases) - len(failed),
        failed_cases=tuple(failed),
        false_positive_cases=tuple(false_positives),
        false_negative_cases=tuple(false_negatives),
        evidence_completeness=evidence_completeness,
        latency_seconds=latency_seconds,
        required_field_fragility=required_field_fragility,
    )


def load_replay_case_from_journal(
    journal_path: Path,
    *,
    name: str,
    expected_match: bool,
) -> ReplayCase:
    """Load a replay case from a canonical local journal."""

    snapshot = LocalJournal(Path(journal_path)).verified_snapshot()
    if not snapshot.ok:
        raise JournalError("cannot load replay case from an unverified journal")
    return ReplayCase(
        name=name,
        events=snapshot.events,
        expected_match=expected_match,
    )


def build_mutation_cases(
    events: tuple[EventEnvelope, ...],
    *,
    expected_match: bool,
    seed: int,
    strategies: tuple[MutationStrategy, ...],
) -> tuple[ReplayCase, ...]:
    """Build deterministic replay cases from mutation strategies."""

    return tuple(
        mutate_events(
            events, strategy=strategy, expected_match=expected_match, seed=seed
        ).as_replay_case()
        for strategy in strategies
    )


def mutate_events(
    events: tuple[EventEnvelope, ...],
    *,
    strategy: MutationStrategy,
    expected_match: bool,
    seed: int,
) -> MutationResult:
    """Apply one deterministic mutation to an event tuple."""

    if not events:
        return MutationResult(
            name=f"{strategy.value}-{seed}",
            strategy=strategy,
            semantic_property="empty corpus remains empty",
            events=(),
            expected_match=expected_match,
            seed=seed,
        )
    if strategy == MutationStrategy.BENIGN_DISTRACTOR:
        return _benign_distractor(events, expected_match=expected_match, seed=seed)
    if strategy == MutationStrategy.DUPLICATE_EVENT:
        return _duplicate_event(events, expected_match=expected_match, seed=seed)
    if strategy == MutationStrategy.REORDER_UNRELATED:
        return MutationResult(
            name=f"reorder-unrelated-{seed}",
            strategy=strategy,
            semantic_property="arrival order changes while occurrence order remains event-local",
            events=tuple(reversed(events)),
            expected_match=expected_match,
            seed=seed,
        )
    if strategy == MutationStrategy.TIMESTAMP_SKEW:
        return _timestamp_skew(events, expected_match=expected_match, seed=seed)
    if strategy == MutationStrategy.MISSING_OPTIONAL_FIELD:
        return _missing_optional_field(events, expected_match=expected_match, seed=seed)
    if strategy == MutationStrategy.PATH_URL_NORMALIZATION:
        return _path_url_normalization(events, expected_match=expected_match, seed=seed)
    if strategy == MutationStrategy.OUTCOME_UNCERTAINTY:
        return _outcome_uncertainty(events, seed=seed)
    raise ValueError(f"unsupported mutation strategy: {strategy}")


def minimize_counterexample(rule: SequenceRule, case: ReplayCase) -> ReplayCase:
    """Remove irrelevant events while preserving a failing replay result."""

    if bool(evaluate_sequence_rule(case.events, rule)) == case.expected_match:
        return case

    minimized = list(case.events)
    changed = True
    while changed:
        changed = False
        for event in tuple(minimized):
            candidate = tuple(item for item in minimized if item is not event)
            if bool(evaluate_sequence_rule(candidate, rule)) != case.expected_match:
                minimized = list(candidate)
                changed = True
                break
    return ReplayCase(
        name=f"{case.name}-minimized",
        events=tuple(minimized),
        expected_match=case.expected_match,
    )


def write_minimized_counterexample(path: Path, case: ReplayCase) -> None:
    """Write a minimized replay case as a reviewed JSON fixture."""

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "name": case.name,
                "expected_match": case.expected_match,
                "events": [event_to_dict(event) for event in case.events],
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )


def _benign_distractor(
    events: tuple[EventEnvelope, ...],
    *,
    expected_match: bool,
    seed: int,
) -> MutationResult:
    event = events[-1]
    distractor = event.model_copy(
        update={
            "event_id": f"{event.event_id}_benign_{seed}",
            "event_type": EventType.RESOURCE_OBSERVED,
            "payload": {"resource": {"type": "file", "path": f"demo://benign-{seed}.txt"}},
        }
    )
    return MutationResult(
        name=f"benign-distractor-{seed}",
        strategy=MutationStrategy.BENIGN_DISTRACTOR,
        semantic_property="adds unrelated evidence that should not change the expected result",
        events=(*events, distractor),
        expected_match=expected_match,
        seed=seed,
    )


def _duplicate_event(
    events: tuple[EventEnvelope, ...],
    *,
    expected_match: bool,
    seed: int,
) -> MutationResult:
    index = seed % len(events)
    event = events[index]
    duplicate = event.model_copy(
        update={
            "event_id": f"{event.event_id}_duplicate_{seed}",
            "causality": event.causality.model_copy(
                update={"sequence": event.causality.sequence + 10_000 + seed}
            ),
        }
    )
    return MutationResult(
        name=f"duplicate-event-{seed}",
        strategy=MutationStrategy.DUPLICATE_EVENT,
        semantic_property="duplicates one event as an arrival artifact",
        events=(*events, duplicate),
        expected_match=expected_match,
        seed=seed,
    )


def _timestamp_skew(
    events: tuple[EventEnvelope, ...],
    *,
    expected_match: bool,
    seed: int,
) -> MutationResult:
    skew = timedelta(milliseconds=(seed % 5) + 1)
    skewed = tuple(
        event.model_copy(
            update={
                "observed_at": event.observed_at + skew,
            }
        )
        for event in events
    )
    return MutationResult(
        name=f"timestamp-skew-{seed}",
        strategy=MutationStrategy.TIMESTAMP_SKEW,
        semantic_property="arrival timestamps skew without changing occurrence ordering",
        events=skewed,
        expected_match=expected_match,
        seed=seed,
    )


def _missing_optional_field(
    events: tuple[EventEnvelope, ...],
    *,
    expected_match: bool,
    seed: int,
) -> MutationResult:
    mutated: list[EventEnvelope] = []
    removed = False
    for event in events:
        payload = dict(event.payload)
        acknowledgement = payload.get("acknowledgement")
        if not removed and isinstance(acknowledgement, Mapping) and "note" in acknowledgement:
            acknowledgement = dict(acknowledgement)
            acknowledgement.pop("note")
            payload["acknowledgement"] = acknowledgement
            mutated.append(event.model_copy(update={"payload": payload}))
            removed = True
        else:
            mutated.append(event)
    return MutationResult(
        name=f"missing-optional-field-{seed}",
        strategy=MutationStrategy.MISSING_OPTIONAL_FIELD,
        semantic_property="removes an optional field that detections should not require",
        events=tuple(mutated),
        expected_match=expected_match,
        seed=seed,
    )


def _path_url_normalization(
    events: tuple[EventEnvelope, ...],
    *,
    expected_match: bool,
    seed: int,
) -> MutationResult:
    mutated = tuple(
        event.model_copy(update={"payload": _normalize_path_url_value(event.payload)})
        for event in events
    )
    return MutationResult(
        name=f"path-url-normalization-{seed}",
        strategy=MutationStrategy.PATH_URL_NORMALIZATION,
        semantic_property="path and URL representation variants preserve side-effect meaning",
        events=mutated,
        expected_match=expected_match,
        seed=seed,
    )


def _normalize_path_url_value(value: object) -> object:
    if isinstance(value, str):
        return _normalize_path_url_string(value)
    if isinstance(value, list | tuple):
        return [_normalize_path_url_value(item) for item in value]
    if isinstance(value, Mapping):
        return {str(key): _normalize_path_url_value(child) for key, child in value.items()}
    return value


def _normalize_path_url_string(value: str) -> str:
    if value.startswith("demo://workspace/") and "demo://workspace/./" not in value:
        return value.replace("demo://workspace/", "demo://workspace/./", 1)
    if value.startswith("http://receiver.local/"):
        return value.replace("http://receiver.local/", "http://receiver.local:80/", 1)
    return value


def _outcome_uncertainty(events: tuple[EventEnvelope, ...], *, seed: int) -> MutationResult:
    mutated: list[EventEnvelope] = []
    replaced = False
    for event in events:
        if not replaced and event_type_value(event) == EventType.SIDE_EFFECT_VERIFIED.value:
            payload = dict(event.payload)
            evidence_link = payload.get("evidence_link")
            if isinstance(evidence_link, Mapping):
                evidence_link = dict(evidence_link)
                evidence_link["verification_status"] = "unverified"
                evidence_link["limitations"] = [
                    *evidence_link.get("limitations", []),
                    "mutation replaced verified outcome with unverified evidence",
                ]
                payload["evidence_link"] = evidence_link
            mutated.append(
                event.model_copy(
                    update={
                        "event_type": EventType.SIDE_EFFECT_UNVERIFIED,
                        "payload": payload,
                    }
                )
            )
            replaced = True
        else:
            mutated.append(event)
    return MutationResult(
        name=f"outcome-uncertainty-{seed}",
        strategy=MutationStrategy.OUTCOME_UNCERTAINTY,
        semantic_property="verified outcome is degraded to unverified evidence",
        events=tuple(mutated),
        expected_match=False,
        seed=seed,
    )


def event_type_value(event: EventEnvelope) -> str:
    value = event.event_type
    return value.value if isinstance(value, EventType) else str(value)
