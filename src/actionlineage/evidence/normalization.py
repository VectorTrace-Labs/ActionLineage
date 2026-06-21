"""Normalize source-neutral evidence inputs into event envelopes."""

from __future__ import annotations

from dataclasses import dataclass, field

from actionlineage.domain import (
    Causality,
    Classification,
    Correlation,
    EventEnvelope,
    EventType,
    IdGenerator,
    Principal,
    Source,
)
from actionlineage.domain.events import JsonObject
from actionlineage.domain.time import Clock


@dataclass(slots=True)
class EvidenceNormalizer:
    """Small event factory shared by adapters, demos, and replay fixtures."""

    correlation: Correlation
    source: Source
    principal: Principal
    classification: Classification
    clock: Clock
    id_generator: IdGenerator
    initial_sequence: int = 0
    _sequence: int = field(default=0, init=False)
    _root_event_id: str | None = field(default=None, init=False)
    _last_event_id: str | None = field(default=None, init=False)

    def __post_init__(self) -> None:
        """Initialize the next sequence for append-to-existing-journal use cases."""

        if self.initial_sequence < 0:
            raise ValueError("initial_sequence must be non-negative")
        self._sequence = self.initial_sequence

    def record(
        self,
        event_type: EventType | str,
        payload: JsonObject,
        *,
        source: Source | None = None,
        principal: Principal | None = None,
        classification: Classification | None = None,
        parent_event_id: str | None = None,
        root_event_id: str | None = None,
    ) -> EventEnvelope:
        """Create the next event envelope with deterministic causality."""

        event_id = self.id_generator.new_id("evt")
        sequence = self._sequence
        is_root = self._root_event_id is None and parent_event_id is None and root_event_id is None
        resolved_root_event_id = self._resolve_root_event_id(
            event_id=event_id,
            root_event_id=root_event_id,
            is_root=is_root,
        )
        resolved_parent_event_id = None if is_root else parent_event_id or self._last_event_id

        event = EventEnvelope(
            event_id=event_id,
            event_type=event_type,
            occurred_at=self.clock.now(),
            observed_at=self.clock.now(),
            source=source or self.source,
            correlation=self.correlation,
            causality=Causality(
                root_event_id=resolved_root_event_id,
                parent_event_id=resolved_parent_event_id,
                sequence=sequence,
            ),
            principal=principal or self.principal,
            classification=classification or self.classification,
            payload=payload,
        )

        self._sequence += 1
        self._root_event_id = event.causality.root_event_id
        self._last_event_id = event.event_id
        return event

    @property
    def last_event_id(self) -> str | None:
        """Most recently emitted event ID."""

        return self._last_event_id

    @property
    def root_event_id(self) -> str | None:
        """Root event ID for the current normalized timeline."""

        return self._root_event_id

    def _resolve_root_event_id(
        self,
        *,
        event_id: str,
        root_event_id: str | None,
        is_root: bool,
    ) -> str:
        if is_root:
            return event_id
        if root_event_id is not None:
            return root_event_id
        if self._root_event_id is not None:
            return self._root_event_id
        raise ValueError("root_event_id is required when the first event is not a root event")
