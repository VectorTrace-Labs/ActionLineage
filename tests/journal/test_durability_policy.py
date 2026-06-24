from __future__ import annotations

import json
from dataclasses import FrozenInstanceError

import pytest

import actionlineage
from actionlineage.journal import (
    DEFAULT_LOCAL_DURABILITY_RULES,
    LOCAL_DURABILITY_POLICY_VERSION,
    DurabilityFault,
    DurabilityOutcome,
    DurabilitySurface,
    LocalDurabilityPolicyError,
    get_local_durability_rule,
    local_durability_policy,
)


def test_local_durability_policy_is_deterministic_json() -> None:
    policy = local_durability_policy()
    encoded = json.dumps(policy, sort_keys=True)

    assert json.loads(encoded) == policy
    assert policy["schema_version"] == "actionlineage.dev/local-durability-policy-v1"
    assert policy["schema_version"] == LOCAL_DURABILITY_POLICY_VERSION
    assert policy["canonical_evidence"] == "append_only_journal"
    assert policy["projection_boundary"] == "derived_rebuildable_state"
    assert policy["case_bundle_boundary"] == "derived_export_artifact"
    assert policy["external_checkpoint_boundary"] == "explicit_unknown_when_unavailable"
    assert len(policy["rules"]) == len(DEFAULT_LOCAL_DURABILITY_RULES)


def test_local_durability_policy_covers_required_faults() -> None:
    rules = {(rule.surface, rule.fault): rule for rule in DEFAULT_LOCAL_DURABILITY_RULES}

    assert (
        rules[
            (
                DurabilitySurface.JOURNAL_APPEND,
                DurabilityFault.APPEND_PREFLIGHT_FAILURE,
            )
        ].outcome
        is DurabilityOutcome.NO_CANONICAL_APPEND
    )
    assert (
        rules[
            (
                DurabilitySurface.JOURNAL_VERIFICATION,
                DurabilityFault.PARTIAL_RECORD_WITHOUT_NEWLINE,
            )
        ].outcome
        is DurabilityOutcome.VERIFIED_PREFIX_AVAILABLE
    )
    assert (
        rules[
            (
                DurabilitySurface.PROJECTION,
                DurabilityFault.PROJECTION_REBUILD_FAILURE,
            )
        ].outcome
        is DurabilityOutcome.DERIVED_ARTIFACT_STALE
    )
    assert (
        rules[
            (
                DurabilitySurface.SERVICE_INGEST_BATCH,
                DurabilityFault.BATCH_LATER_APPEND_FAILURE,
            )
        ].outcome
        is DurabilityOutcome.CANONICAL_PREFIX_COMMITTED
    )
    assert (
        rules[
            (
                DurabilitySurface.CASE_BUNDLE,
                DurabilityFault.CASE_BUNDLE_STAGING_FAILURE,
            )
        ].outcome
        is DurabilityOutcome.DERIVED_ARTIFACT_NOT_PUBLISHED
    )
    assert (
        rules[
            (
                DurabilitySurface.APPEND_CACHE,
                DurabilityFault.FUTURE_APPEND_CACHE_MISMATCH,
            )
        ].outcome
        is DurabilityOutcome.CACHE_IGNORED_OR_REBUILT
    )
    assert (
        rules[
            (
                DurabilitySurface.EXTERNAL_CHECKPOINT,
                DurabilityFault.EXTERNAL_CHECKPOINT_VERIFIER_UNAVAILABLE,
            )
        ].outcome
        is DurabilityOutcome.EXTERNAL_STATUS_UNKNOWN
    )


def test_local_durability_rule_lookup_and_immutability() -> None:
    rule = get_local_durability_rule(
        DurabilitySurface.APPEND_CACHE,
        DurabilityFault.FUTURE_APPEND_CACHE_MISMATCH,
    )

    assert rule.outcome is DurabilityOutcome.CACHE_IGNORED_OR_REBUILT
    assert "never canonical" in rule.claim_boundary
    with pytest.raises(FrozenInstanceError):
        rule.outcome = DurabilityOutcome.CANONICAL_APPEND_COMMITTED  # type: ignore[misc]


def test_local_durability_rule_lookup_fails_closed_for_unreviewed_pairs() -> None:
    with pytest.raises(LocalDurabilityPolicyError, match="no local durability policy"):
        get_local_durability_rule(
            DurabilitySurface.CASE_BUNDLE,
            DurabilityFault.FUTURE_APPEND_CACHE_MISMATCH,
        )


def test_local_durability_exports_are_public() -> None:
    assert actionlineage.LOCAL_DURABILITY_POLICY_VERSION == LOCAL_DURABILITY_POLICY_VERSION
    assert actionlineage.local_durability_policy() == local_durability_policy()
    assert actionlineage.DurabilitySurface.APPEND_CACHE is DurabilitySurface.APPEND_CACHE
    assert actionlineage.DurabilityFault.FUTURE_APPEND_CACHE_MISMATCH is (
        DurabilityFault.FUTURE_APPEND_CACHE_MISMATCH
    )
