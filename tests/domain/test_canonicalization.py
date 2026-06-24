from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from actionlineage.domain import (
    CANONICALIZATION_VERSION,
    PLANNED_CANONICALIZATION_VERSION,
    IntegrityMetadata,
    deterministic_json_bytes,
    is_supported_persisted_event_canonicalization,
    persisted_event_canonicalization_policy,
)
from actionlineage.journal.hashing import compute_event_hash
from tests.domain.test_events import build_event

VECTORS_PATH = Path("tests/fixtures/canonicalization/json-canonicalization-v1-vectors.json")


def load_vectors() -> dict[str, object]:
    return json.loads(VECTORS_PATH.read_text(encoding="utf-8"))


def test_planned_v1_conformance_vectors_are_executable() -> None:
    data = load_vectors()

    assert data["schema_version"] == "actionlineage.dev/canonicalization-conformance-vectors-v1"
    assert data["canonicalization"] == PLANNED_CANONICALIZATION_VERSION
    assert data["status"] == "planned_not_persisted"

    valid_vectors = data["valid_vectors"]
    invalid_vectors = data["invalid_vectors"]
    assert isinstance(valid_vectors, list)
    assert isinstance(invalid_vectors, list)

    categories = {vector["category"] for vector in valid_vectors + invalid_vectors}
    assert {
        "object_member_ordering",
        "duplicate_object_key_rejection",
        "unicode_escaping",
        "number_rendering",
        "non_finite_number_rejection",
        "boolean_null_array",
        "utc_timestamp",
        "golden_event",
        "golden_descriptor",
        "golden_evidence_link",
    } <= categories

    for vector in valid_vectors:
        canonical_json = vector["canonical_json"]
        canonical_bytes = canonical_json.encode("utf-8")
        assert not canonical_bytes.startswith(b"\xef\xbb\xbf")
        assert vector["sha256"] == f"sha256:{hashlib.sha256(canonical_bytes).hexdigest()}"


def test_v1_vectors_keep_migration_policy_fail_closed() -> None:
    policy = load_vectors()["migration_policy"]

    assert policy == {
        "active_persisted_event_hash": CANONICALIZATION_VERSION,
        "v1_persisted_event_hash_status": "migration_adr_required",
        "mixed_canonicalization_journals": "rejected_until_migration_adr",
        "old_json_deterministic_v0_journals_remain_readable": True,
        "projection_anchor_manifest_descriptor_digest_policy": (
            "algorithm_label_required_for_each_digest"
        ),
        "unsupported_numeric_values": "fail_closed_before_hash_input",
    }
    runtime_policy = persisted_event_canonicalization_policy()
    assert runtime_policy["active_persisted_event_hash"] == policy["active_persisted_event_hash"]
    assert (
        runtime_policy["v1_persisted_event_hash_status"] == policy["v1_persisted_event_hash_status"]
    )
    assert (
        runtime_policy["mixed_canonicalization_journals"]
        == policy["mixed_canonicalization_journals"]
    )
    assert runtime_policy["old_json_deterministic_v0_journals_remain_readable"] is True


def test_persisted_event_canonicalization_support_is_explicit() -> None:
    assert is_supported_persisted_event_canonicalization(CANONICALIZATION_VERSION)
    assert not is_supported_persisted_event_canonicalization(PLANNED_CANONICALIZATION_VERSION)


def test_v0_serializer_matches_only_vectors_marked_by_current_boundary() -> None:
    # These vectors document the planned v1 byte target. The current
    # json-deterministic-v0 serializer must remain active and separately named.
    vector = next(
        vector for vector in load_vectors()["valid_vectors"] if vector["id"] == "boolean-null-array"
    )

    parsed = json.loads(vector["input_json"])

    assert deterministic_json_bytes(parsed) == vector["canonical_json"].encode("utf-8")


def test_planned_v1_label_is_rejected_for_persisted_event_hashes() -> None:
    event = build_event().model_copy(
        update={
            "integrity": IntegrityMetadata(
                canonicalization=PLANNED_CANONICALIZATION_VERSION,
                previous_event_hash=None,
                event_hash=None,
            )
        }
    )

    with pytest.raises(ValueError, match="unsupported persisted event canonicalization"):
        compute_event_hash(event)
