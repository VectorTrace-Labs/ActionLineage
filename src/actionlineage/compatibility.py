"""Compatibility helpers for supported ActionLineage event streams."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from actionlineage.domain import SPEC_VERSION, EventEnvelope, EventType
from actionlineage.domain.events import event_type_value

COMPATIBILITY_POLICY_VERSION = "actionlineage.dev/compatibility-policy-v1"
SUPPORTED_EVENT_SPEC_VERSIONS: tuple[str, ...] = (SPEC_VERSION,)
READABLE_EVENT_SPEC_VERSIONS: tuple[str, ...] = SUPPORTED_EVENT_SPEC_VERSIONS
KNOWN_EVENT_TYPES: frozenset[str] = frozenset(event_type.value for event_type in EventType)


class CompatibilityStatus(StrEnum):
    """Compatibility assessment for one parsed event."""

    SUPPORTED_KNOWN_EVENT = "supported_known_event"
    SUPPORTED_UNKNOWN_EVENT = "supported_unknown_event"


@dataclass(frozen=True, slots=True)
class CompatibilityAssessment:
    """Documented compatibility result for one event."""

    policy_version: str
    spec_version: str
    event_type: str
    status: CompatibilityStatus
    can_read: bool
    can_interpret_semantics: bool
    notes: tuple[str, ...]

    def as_dict(self) -> dict[str, object]:
        """Return a JSON-compatible compatibility report."""

        return {
            "policy_version": self.policy_version,
            "spec_version": self.spec_version,
            "event_type": self.event_type,
            "status": self.status.value,
            "can_read": self.can_read,
            "can_interpret_semantics": self.can_interpret_semantics,
            "notes": list(self.notes),
        }


def is_supported_spec_version(spec_version: str) -> bool:
    """Return true when this package supports reading the event spec version."""

    return spec_version in READABLE_EVENT_SPEC_VERSIONS


def is_known_event_type(event_type: EventType | str) -> bool:
    """Return true when the event type has documented semantics in this package."""

    return event_type_value(event_type) in KNOWN_EVENT_TYPES


def assess_event_compatibility(event: EventEnvelope) -> CompatibilityAssessment:
    """Assess read and semantic compatibility for a parsed event."""

    event_type = event_type_value(event.event_type)
    if is_known_event_type(event_type):
        return CompatibilityAssessment(
            policy_version=COMPATIBILITY_POLICY_VERSION,
            spec_version=event.spec_version,
            event_type=event_type,
            status=CompatibilityStatus.SUPPORTED_KNOWN_EVENT,
            can_read=True,
            can_interpret_semantics=True,
            notes=("event type has documented v1alpha1 semantics",),
        )

    return CompatibilityAssessment(
        policy_version=COMPATIBILITY_POLICY_VERSION,
        spec_version=event.spec_version,
        event_type=event_type,
        status=CompatibilityStatus.SUPPORTED_UNKNOWN_EVENT,
        can_read=True,
        can_interpret_semantics=False,
        notes=("event type is preserved as evidence but not interpreted as safe behavior",),
    )
