"""Journal hash-chain helpers."""

from __future__ import annotations

import hashlib

from actionlineage.domain import (
    EventEnvelope,
    IntegrityMetadata,
    RedactionPolicy,
    event_from_json,
    serialize_event,
    serialize_event_for_persistence,
)
from actionlineage.domain.redaction import RedactionBoundary


def sha256_digest(value: bytes) -> str:
    """Return a namespaced SHA-256 digest."""

    return f"sha256:{hashlib.sha256(value).hexdigest()}"


def event_with_integrity(
    event: EventEnvelope,
    *,
    previous_event_hash: str | None,
    event_hash: str | None,
) -> EventEnvelope:
    """Return an event copy with updated integrity metadata."""

    return event.model_copy(
        update={
            "integrity": IntegrityMetadata(
                canonicalization=event.integrity.canonicalization,
                previous_event_hash=previous_event_hash,
                event_hash=event_hash,
            )
        }
    )


def prepare_event_for_append(
    event: EventEnvelope,
    *,
    previous_event_hash: str | None,
    redaction_policy: RedactionBoundary | None = None,
) -> tuple[EventEnvelope, bytes]:
    """Return the redacted event and canonical bytes to append to the journal."""

    event_for_hash = event_with_integrity(
        event,
        previous_event_hash=previous_event_hash,
        event_hash=None,
    )
    policy = redaction_policy or RedactionPolicy()
    redacted_hash_event = event_from_json(
        serialize_event_for_persistence(event_for_hash, redaction_policy=policy)
    )
    event_hash = compute_event_hash(redacted_hash_event)
    redacted_event = event_with_integrity(
        redacted_hash_event,
        previous_event_hash=previous_event_hash,
        event_hash=event_hash,
    )
    return redacted_event, serialize_event(redacted_event)


def compute_event_hash(event: EventEnvelope) -> str:
    """Compute the event hash over canonical bytes with `event_hash` unset."""

    hash_event = event_with_integrity(
        event,
        previous_event_hash=event.integrity.previous_event_hash,
        event_hash=None,
    )
    return sha256_digest(serialize_event(hash_event))
