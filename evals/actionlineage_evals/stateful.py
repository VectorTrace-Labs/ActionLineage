"""Stateful mutation model for eval scenario generation."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum


class MutationDimension(StrEnum):
    """Scenario mutation dimensions tracked by the lab."""

    PROMPT_WORDING = "prompt_wording"
    INDIRECT_PROMPT_INJECTION = "indirect_prompt_injection"
    DESCRIPTOR_DRIFT = "descriptor_drift"
    PATH_URL_NORMALIZATION = "path_url_normalization"
    MISSING_OPTIONAL_FIELD = "missing_optional_field"
    EVENT_ORDERING_SKEW = "event_ordering_skew"
    DUPLICATE_BENIGN_EVENT = "duplicate_benign_event"
    TOXIPROXY_DELAY_DROP = "toxiproxy_delay_drop"
    REDACTION_CANARY_LOCATION = "redaction_canary_location"
    CONCURRENCY = "concurrency"
    TRANSCRIPT_REPLAY_VARIANT = "transcript_replay_variant"


@dataclass(frozen=True, slots=True)
class GeneratedMutation:
    """One seeded stateful mutation."""

    dimension: MutationDimension
    seed: int

    def as_dict(self) -> dict[str, object]:
        return {"dimension": self.dimension.value, "seed": self.seed}


def deterministic_mutation_sequence(seed: int, *, count: int) -> tuple[GeneratedMutation, ...]:
    """Generate a deterministic mutation sequence without external entropy."""

    dimensions = tuple(MutationDimension)
    return tuple(
        GeneratedMutation(
            dimension=dimensions[(seed + index) % len(dimensions)],
            seed=seed + index,
        )
        for index in range(count)
    )


@dataclass(frozen=True, slots=True)
class StatefulMutationStep:
    """One generated state-machine transition."""

    dimension: MutationDimension
    expected_failure_class: str | None
    operation: str
    seed: int
    semantic_property: str
    target: str

    def as_dict(self) -> dict[str, object]:
        data: dict[str, object] = {
            "dimension": self.dimension.value,
            "operation": self.operation,
            "seed": self.seed,
            "semantic_property": self.semantic_property,
            "target": self.target,
        }
        if self.expected_failure_class is not None:
            data["expected_failure_class"] = self.expected_failure_class
        return data


@dataclass(frozen=True, slots=True)
class StatefulCounterexample:
    """A generated and minimized stateful mutation counterexample."""

    base_scenario_id: str
    failure_class: str
    generated_steps: tuple[StatefulMutationStep, ...]
    minimized_steps: tuple[StatefulMutationStep, ...]
    seed: int

    @property
    def counterexample_found(self) -> bool:
        """Return whether the generated sequence preserves the failure predicate."""

        return stateful_failure_predicate(self.minimized_steps)

    def as_report(self) -> dict[str, object]:
        """Return a stable report suitable for replay bundles and scorecards."""

        return {
            "base_scenario_id": self.base_scenario_id,
            "counterexample_found": self.counterexample_found,
            "failure_class": self.failure_class,
            "generated_steps": [step.as_dict() for step in self.generated_steps],
            "generator": {
                "deterministic_replay": True,
                "engine": "hypothesis_stateful_model",
                "strategy": "bounded_lifecycle_mutation_sequence",
            },
            "minimized_steps": [step.as_dict() for step in self.minimized_steps],
            "original_step_count": len(self.generated_steps),
            "reduced": len(self.minimized_steps) < len(self.generated_steps),
            "replayable": True,
            "schema_version": "actionlineage.dev/eval-stateful-mutation-report-v0",
            "seed": self.seed,
        }


def deterministic_stateful_counterexample(
    seed: int,
    *,
    base_scenario_id: str,
) -> StatefulCounterexample:
    """Build a deterministic stateful mutation failure and minimized counterexample."""

    generated = (
        StatefulMutationStep(
            dimension=MutationDimension.EVENT_ORDERING_SKEW,
            expected_failure_class=None,
            operation="skew_observation_timestamp",
            seed=seed,
            semantic_property="timestamp skew alone must not change lifecycle evidence",
            target="side_effect.observed.timestamp",
        ),
        StatefulMutationStep(
            dimension=MutationDimension.DUPLICATE_BENIGN_EVENT,
            expected_failure_class=None,
            operation="duplicate_benign_resource_observation",
            seed=seed + 1,
            semantic_property="duplicate benign evidence must not change scenario outcome",
            target="resource.observed",
        ),
        StatefulMutationStep(
            dimension=MutationDimension.MISSING_OPTIONAL_FIELD,
            expected_failure_class="product_failure",
            operation="drop_required_verification_status",
            seed=seed + 2,
            semantic_property=(
                "removing verification status from required evidence must fail lifecycle scoring"
            ),
            target="side_effect.verified.evidence_link.verification_status",
        ),
        StatefulMutationStep(
            dimension=MutationDimension.TRANSCRIPT_REPLAY_VARIANT,
            expected_failure_class=None,
            operation="replay_same_tool_call_transcript",
            seed=seed + 3,
            semantic_property="transcript replay variant must preserve generated failure",
            target="transcript.turns[0].tool_calls",
        ),
    )
    minimized = minimize_stateful_steps(generated, still_fails=stateful_failure_predicate)
    return StatefulCounterexample(
        base_scenario_id=base_scenario_id,
        failure_class="product_failure",
        generated_steps=generated,
        minimized_steps=minimized,
        seed=seed,
    )


def minimize_stateful_steps(
    steps: tuple[StatefulMutationStep, ...],
    *,
    still_fails: StatefulFailurePredicate,
) -> tuple[StatefulMutationStep, ...]:
    """Delta-minimize generated mutation steps while preserving a failure predicate."""

    minimized = tuple(steps)
    changed = True
    while changed:
        changed = False
        for index in range(len(minimized)):
            candidate = tuple(
                step for item_index, step in enumerate(minimized) if item_index != index
            )
            if candidate and still_fails(candidate):
                minimized = candidate
                changed = True
                break
    return minimized


def stateful_failure_predicate(steps: tuple[StatefulMutationStep, ...]) -> bool:
    """Return whether a mutation sequence still models the target product failure."""

    return any(step.operation == "drop_required_verification_status" for step in steps)


type StatefulFailurePredicate = Callable[[tuple[StatefulMutationStep, ...]], bool]
