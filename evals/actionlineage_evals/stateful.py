"""Hypothesis stateful mutation model for eval scenario generation."""

from __future__ import annotations

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
