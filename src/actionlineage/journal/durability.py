"""Local durability policy for journal-adjacent failure handling."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

LOCAL_DURABILITY_POLICY_VERSION = "actionlineage.dev/local-durability-policy-v1"


class DurabilitySurface(StrEnum):
    """Durability-relevant local surfaces."""

    JOURNAL_APPEND = "journal_append"
    JOURNAL_VERIFICATION = "journal_verification"
    SERVICE_INGEST_BATCH = "service_ingest_batch"
    PROJECTION = "projection"
    CASE_BUNDLE = "case_bundle"
    APPEND_CACHE = "append_cache"
    EXTERNAL_CHECKPOINT = "external_checkpoint"


class DurabilityFault(StrEnum):
    """Reviewed local durability fault classes."""

    APPEND_PREFLIGHT_FAILURE = "append_preflight_failure"
    APPEND_WRITE_FLUSH_FSYNC_FAILURE = "append_write_flush_fsync_failure"
    PARTIAL_RECORD_WITHOUT_NEWLINE = "partial_record_without_newline"
    PROCESS_CRASH_AFTER_APPEND_BEFORE_PROJECTION = "process_crash_after_append_before_projection"
    BATCH_LATER_APPEND_FAILURE = "batch_later_append_failure"
    PROJECTION_REBUILD_FAILURE = "projection_rebuild_failure"
    CASE_BUNDLE_STAGING_FAILURE = "case_bundle_staging_failure"
    CASE_BUNDLE_PUBLISH_COLLISION = "case_bundle_publish_collision"
    FUTURE_APPEND_CACHE_MISMATCH = "future_append_cache_mismatch"
    EXTERNAL_CHECKPOINT_VERIFIER_UNAVAILABLE = "external_checkpoint_verifier_unavailable"


class DurabilityOutcome(StrEnum):
    """Allowed outcomes for local durability fault classes."""

    NO_CANONICAL_APPEND = "no_canonical_append"
    VERIFIED_PREFIX_AVAILABLE = "verified_prefix_available"
    CANONICAL_APPEND_COMMITTED = "canonical_append_committed"
    CANONICAL_PREFIX_COMMITTED = "canonical_prefix_committed"
    DERIVED_ARTIFACT_NOT_PUBLISHED = "derived_artifact_not_published"
    DERIVED_ARTIFACT_STALE = "derived_artifact_stale"
    CACHE_IGNORED_OR_REBUILT = "cache_ignored_or_rebuilt"
    EXTERNAL_STATUS_UNKNOWN = "external_status_unknown"


class LocalDurabilityPolicyError(ValueError):
    """Raised when a durability rule lookup has no reviewed policy."""


@dataclass(frozen=True, slots=True)
class LocalDurabilityRule:
    """One reviewed local durability failure rule."""

    surface: DurabilitySurface
    fault: DurabilityFault
    outcome: DurabilityOutcome
    canonical_journal_state: str
    derived_state: str
    retry_guidance: str
    claim_boundary: str

    def as_dict(self) -> dict[str, str]:
        """Return a deterministic JSON-ready copy."""

        return {
            "surface": self.surface.value,
            "fault": self.fault.value,
            "outcome": self.outcome.value,
            "canonical_journal_state": self.canonical_journal_state,
            "derived_state": self.derived_state,
            "retry_guidance": self.retry_guidance,
            "claim_boundary": self.claim_boundary,
        }


DEFAULT_LOCAL_DURABILITY_RULES: tuple[LocalDurabilityRule, ...] = (
    LocalDurabilityRule(
        surface=DurabilitySurface.JOURNAL_APPEND,
        fault=DurabilityFault.APPEND_PREFLIGHT_FAILURE,
        outcome=DurabilityOutcome.NO_CANONICAL_APPEND,
        canonical_journal_state=(
            "Existing verified journal bytes remain canonical; the candidate event is rejected "
            "before it becomes trusted evidence."
        ),
        derived_state="No projection, cache, anchor, or case-bundle update is trusted.",
        retry_guidance=(
            "Fix storage or integrity preflight issues, then retry the same evidence input."
        ),
        claim_boundary="Do not report a rejected candidate as persisted evidence.",
    ),
    LocalDurabilityRule(
        surface=DurabilitySurface.JOURNAL_APPEND,
        fault=DurabilityFault.APPEND_WRITE_FLUSH_FSYNC_FAILURE,
        outcome=DurabilityOutcome.VERIFIED_PREFIX_AVAILABLE,
        canonical_journal_state=(
            "Verification may stop at an incomplete or corrupt final record; only the prior "
            "verified prefix is usable as canonical evidence."
        ),
        derived_state=(
            "Derived state must be treated as stale until rebuilt from the verified prefix."
        ),
        retry_guidance=(
            "Do not truncate in place; export the verified prefix or retry after storage repair."
        ),
        claim_boundary="Do not claim the failed append committed unless it later verifies.",
    ),
    LocalDurabilityRule(
        surface=DurabilitySurface.JOURNAL_VERIFICATION,
        fault=DurabilityFault.PARTIAL_RECORD_WITHOUT_NEWLINE,
        outcome=DurabilityOutcome.VERIFIED_PREFIX_AVAILABLE,
        canonical_journal_state=(
            "Records before the missing newline can verify; the incomplete record and later bytes "
            "are not trusted evidence."
        ),
        derived_state="Projection and exports must not include unverified suffix records.",
        retry_guidance="Use verified-prefix export to create a separate recovery file.",
        claim_boundary="No in-place repair, deletion, or proof-of-absence claim is implied.",
    ),
    LocalDurabilityRule(
        surface=DurabilitySurface.PROJECTION,
        fault=DurabilityFault.PROJECTION_REBUILD_FAILURE,
        outcome=DurabilityOutcome.DERIVED_ARTIFACT_STALE,
        canonical_journal_state="A successful journal append remains canonical evidence.",
        derived_state=(
            "Projection reads are stale and must fail closed until rebuilt from the journal."
        ),
        retry_guidance="Retry with the same idempotency key or explicitly rebuild the projection.",
        claim_boundary="Projection failure must not roll back or hide committed journal evidence.",
    ),
    LocalDurabilityRule(
        surface=DurabilitySurface.SERVICE_INGEST_BATCH,
        fault=DurabilityFault.PROCESS_CRASH_AFTER_APPEND_BEFORE_PROJECTION,
        outcome=DurabilityOutcome.CANONICAL_APPEND_COMMITTED,
        canonical_journal_state="If the appended record verifies, it remains canonical evidence.",
        derived_state="Projection health is stale until a duplicate retry or rebuild repairs it.",
        retry_guidance=(
            "Retry the same idempotency key; duplicate detection should repair projection state."
        ),
        claim_boundary="Do not report the retry as a second append.",
    ),
    LocalDurabilityRule(
        surface=DurabilitySurface.SERVICE_INGEST_BATCH,
        fault=DurabilityFault.BATCH_LATER_APPEND_FAILURE,
        outcome=DurabilityOutcome.CANONICAL_PREFIX_COMMITTED,
        canonical_journal_state=(
            "Earlier records that verified remain committed; later failed records do not."
        ),
        derived_state=(
            "Projection may represent only the committed prefix until recovery completes."
        ),
        retry_guidance="Retry the original batch; committed records should resolve as duplicates.",
        claim_boundary="Do not claim all-or-nothing batch semantics for the local service path.",
    ),
    LocalDurabilityRule(
        surface=DurabilitySurface.CASE_BUNDLE,
        fault=DurabilityFault.CASE_BUNDLE_STAGING_FAILURE,
        outcome=DurabilityOutcome.DERIVED_ARTIFACT_NOT_PUBLISHED,
        canonical_journal_state="The source journal and verified projection binding are unchanged.",
        derived_state=(
            "The failed staging directory is cleanup-only and is not a published case bundle."
        ),
        retry_guidance=(
            "Retry export after storage recovery; preserve any pre-existing valid bundle."
        ),
        claim_boundary=(
            "A case bundle is a derived artifact, not canonical evidence or a signature."
        ),
    ),
    LocalDurabilityRule(
        surface=DurabilitySurface.CASE_BUNDLE,
        fault=DurabilityFault.CASE_BUNDLE_PUBLISH_COLLISION,
        outcome=DurabilityOutcome.DERIVED_ARTIFACT_NOT_PUBLISHED,
        canonical_journal_state="The source journal remains canonical evidence.",
        derived_state="Existing destination content is preserved and no new bundle is published.",
        retry_guidance="Choose a new output directory or review the existing bundle.",
        claim_boundary="Do not overwrite or partially merge case-bundle artifacts.",
    ),
    LocalDurabilityRule(
        surface=DurabilitySurface.APPEND_CACHE,
        fault=DurabilityFault.FUTURE_APPEND_CACHE_MISMATCH,
        outcome=DurabilityOutcome.CACHE_IGNORED_OR_REBUILT,
        canonical_journal_state=(
            "Verified journal bytes, record count, and terminal hash remain authoritative."
        ),
        derived_state="The cache is ignored or rebuilt; it cannot nominate its own trust root.",
        retry_guidance="Rebuild cache state from a verified journal snapshot.",
        claim_boundary="A future append cache is never canonical or trusted evidence.",
    ),
    LocalDurabilityRule(
        surface=DurabilitySurface.EXTERNAL_CHECKPOINT,
        fault=DurabilityFault.EXTERNAL_CHECKPOINT_VERIFIER_UNAVAILABLE,
        outcome=DurabilityOutcome.EXTERNAL_STATUS_UNKNOWN,
        canonical_journal_state=(
            "Local journal verification may still succeed under local trust assumptions."
        ),
        derived_state="External checkpoint status is unknown, stale, or unverified.",
        retry_guidance=(
            "Retry external verification or use a caller policy that explicitly accepts local-only "
            "evidence."
        ),
        claim_boundary=(
            "Unavailable external verification must not be silently converted to verified."
        ),
    ),
)


def get_local_durability_rule(
    surface: DurabilitySurface,
    fault: DurabilityFault,
) -> LocalDurabilityRule:
    """Return the reviewed durability rule for one surface and fault."""

    for rule in DEFAULT_LOCAL_DURABILITY_RULES:
        if rule.surface is surface and rule.fault is fault:
            return rule
    raise LocalDurabilityPolicyError(
        f"no local durability policy for surface={surface.value!r} fault={fault.value!r}"
    )


def local_durability_policy() -> dict[str, object]:
    """Return the deterministic local durability policy document."""

    return {
        "schema_version": LOCAL_DURABILITY_POLICY_VERSION,
        "canonical_evidence": "append_only_journal",
        "projection_boundary": "derived_rebuildable_state",
        "case_bundle_boundary": "derived_export_artifact",
        "external_checkpoint_boundary": "explicit_unknown_when_unavailable",
        "rules": [rule.as_dict() for rule in DEFAULT_LOCAL_DURABILITY_RULES],
    }
