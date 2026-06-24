"""Canonicalization algorithm labels and persisted-hash policy."""

from __future__ import annotations

from typing import Final

CANONICALIZATION_VERSION: Final = "actionlineage.dev/json-deterministic-v0"
PLANNED_CANONICALIZATION_VERSION: Final = "actionlineage.dev/json-canonicalization-v1"
SUPPORTED_PERSISTED_EVENT_CANONICALIZATIONS: Final[frozenset[str]] = frozenset(
    {CANONICALIZATION_VERSION}
)


class CanonicalizationError(ValueError):
    """Raised when a canonicalization label is unsafe for the requested boundary."""


def is_supported_persisted_event_canonicalization(label: str) -> bool:
    """Return whether a label may be used for persisted event hash input today."""

    return label in SUPPORTED_PERSISTED_EVENT_CANONICALIZATIONS


def require_supported_persisted_event_canonicalization(label: str) -> None:
    """Fail closed before hashing persisted evidence with an unsupported label."""

    if is_supported_persisted_event_canonicalization(label):
        return

    supported = ", ".join(sorted(SUPPORTED_PERSISTED_EVENT_CANONICALIZATIONS))
    raise CanonicalizationError(
        "unsupported persisted event canonicalization: "
        f"{label}; supported persisted event hash labels: {supported}; "
        f"{PLANNED_CANONICALIZATION_VERSION} requires a migration ADR before use"
    )


def persisted_event_canonicalization_policy() -> dict[str, object]:
    """Return the active migration policy for event-hash canonicalization labels."""

    return {
        "active_persisted_event_hash": CANONICALIZATION_VERSION,
        "planned_canonicalization": PLANNED_CANONICALIZATION_VERSION,
        "supported_persisted_event_hashes": sorted(SUPPORTED_PERSISTED_EVENT_CANONICALIZATIONS),
        "v1_persisted_event_hash_status": "migration_adr_required",
        "mixed_canonicalization_journals": "rejected_until_migration_adr",
        "old_json_deterministic_v0_journals_remain_readable": True,
        "projection_anchor_manifest_descriptor_digest_policy": (
            "algorithm_label_required_for_each_digest"
        ),
        "unsupported_numeric_values": "fail_closed_before_hash_input",
    }
