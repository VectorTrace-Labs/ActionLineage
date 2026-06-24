from __future__ import annotations

import copy
import json
import math
import pickle
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pytest
from jsonschema import Draft202012Validator, FormatChecker
from pydantic import ValidationError

from actionlineage.domain import (
    CANONICALIZATION_VERSION,
    DEFAULT_JSON_MAX_ARRAY_LENGTH,
    DEFAULT_JSON_MAX_DEPTH,
    DEFAULT_JSON_MAX_OBJECT_MEMBERS,
    Causality,
    Classification,
    Correlation,
    EventEnvelope,
    EventType,
    FixedClock,
    FixedIdGenerator,
    IntegrityMetadata,
    Principal,
    PrincipalType,
    Sensitivity,
    Source,
    TrustLevel,
    event_from_json,
    event_to_dict,
    serialize_event,
)

SCHEMA_PATH = Path("schemas/actionlineage-event-v1alpha1.schema.json")
BASE_TIME = datetime(2026, 6, 21, 18, 42, 12, 123456, tzinfo=UTC)


def build_event(
    *,
    event_id: str = "evt_root",
    event_type: EventType | str = EventType.AGENT_RUN_STARTED,
    root_event_id: str = "evt_root",
    parent_event_id: str | None = None,
    sequence: int = 0,
    occurred_at: datetime = BASE_TIME,
    observed_at: datetime = BASE_TIME,
    payload: dict[str, Any] | None = None,
) -> EventEnvelope:
    return EventEnvelope(
        event_id=event_id,
        event_type=event_type,
        occurred_at=occurred_at,
        observed_at=observed_at,
        source=Source(component="unit-test", instance_id="test_01", version="0.0.0"),
        correlation=Correlation(trace_id="trace_01", run_id="run_01"),
        causality=Causality(
            root_event_id=root_event_id,
            parent_event_id=parent_event_id,
            sequence=sequence,
        ),
        principal=Principal(
            principal_id="agent_demo",
            principal_type=PrincipalType.AGENT,
            on_behalf_of="user_demo",
        ),
        classification=Classification(
            sensitivity=Sensitivity.INTERNAL,
            trust=TrustLevel.TRUSTED,
        ),
        payload=payload or {},
        integrity=IntegrityMetadata(canonicalization=CANONICALIZATION_VERSION),
    )


def schema_validator() -> Draft202012Validator:
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    return Draft202012Validator(schema, format_checker=FormatChecker())


def test_event_validates_against_typed_model_and_json_schema() -> None:
    event = build_event(payload={"resource": {"type": "file", "path": "docs/demo.txt"}})
    event_data = event_to_dict(event)

    EventEnvelope.model_validate(event_data)
    errors = sorted(schema_validator().iter_errors(event_data), key=lambda error: error.path)

    assert errors == []


def test_unknown_fields_are_rejected_by_schema_and_typed_model() -> None:
    event_data = event_to_dict(build_event())
    event_data["unexpected"] = "not-in-v1alpha1"

    with pytest.raises(ValidationError):
        EventEnvelope.model_validate(event_data)

    errors = list(schema_validator().iter_errors(event_data))
    assert any("Additional properties are not allowed" in error.message for error in errors)


def test_root_events_may_omit_parent_event_id() -> None:
    event = build_event(event_type=EventType.AGENT_RUN_STARTED, parent_event_id=None)

    assert event.causality.parent_event_id is None
    assert event.causality.root_event_id == event.event_id


def test_non_root_events_require_parent_event_id() -> None:
    with pytest.raises(ValidationError, match="non-root events require parent_event_id"):
        build_event(
            event_id="evt_child",
            event_type=EventType.ACTION_NORMALIZED,
            root_event_id="evt_root",
            parent_event_id=None,
            sequence=1,
        )


def test_ids_remain_stable_through_serialization_deserialization() -> None:
    id_generator = FixedIdGenerator(("evt_root", "run_01"))
    event_id = id_generator.new_id("evt")
    clock = FixedClock(BASE_TIME)
    event = build_event(event_id=event_id, root_event_id=event_id, occurred_at=clock.now())

    serialized = serialize_event(event)
    parsed = event_from_json(serialized)

    assert parsed.event_id == "evt_root"
    assert parsed.correlation.run_id == "run_01"
    assert serialize_event(parsed) == serialized


def test_timestamps_are_canonical_utc_z_strings() -> None:
    central_time = datetime(2026, 6, 21, 13, 42, 12, 123456, tzinfo=timezone(timedelta(hours=-5)))
    event = build_event(occurred_at=central_time, observed_at=central_time)

    serialized = json.loads(serialize_event(event))

    assert serialized["occurred_at"] == "2026-06-21T18:42:12.123456Z"
    assert serialized["observed_at"] == "2026-06-21T18:42:12.123456Z"


def test_naive_timestamps_are_rejected() -> None:
    with pytest.raises(ValidationError, match="timezone-aware"):
        build_event(occurred_at=datetime(2026, 6, 21, 18, 42, 12))


def test_future_event_type_strings_are_preserved_but_not_interpreted() -> None:
    event = build_event(
        event_id="evt_child",
        event_type="vendor.future.observed",
        root_event_id="evt_root",
        parent_event_id="evt_root",
        sequence=1,
    )

    serialized = json.loads(serialize_event(event))
    parsed = event_from_json(serialize_event(event))

    assert serialized["event_type"] == "vendor.future.observed"
    assert parsed.event_type == "vendor.future.observed"


def test_event_payload_is_recursively_immutable_and_serializes_stably() -> None:
    event = build_event(
        payload={
            "metadata": {"reviewed": True},
            "evidence": [{"id": "ev_1", "tags": ["observed", "verified"]}],
        }
    )
    original = serialize_event(event)

    with pytest.raises(TypeError):
        event.payload["added"] = "mutated"  # type: ignore[index]
    with pytest.raises(TypeError):
        event.payload["metadata"]["reviewed"] = False  # type: ignore[index]
    with pytest.raises(TypeError):
        event.payload["evidence"].append({"id": "ev_2"})  # type: ignore[union-attr]
    with pytest.raises(TypeError):
        event.payload["evidence"][0]["id"] = "ev_tampered"  # type: ignore[index]

    assert serialize_event(event) == original
    assert event_to_dict(event)["payload"] == {
        "metadata": {"reviewed": True},
        "evidence": [{"id": "ev_1", "tags": ["observed", "verified"]}],
    }


def test_event_payload_blocks_top_level_field_reassignment() -> None:
    event = build_event(payload={"status": "verified"})
    original = serialize_event(event)

    with pytest.raises(ValidationError, match="frozen"):
        event.payload = {"status": "modified"}  # type: ignore[misc]

    assert serialize_event(event) == original
    assert event_to_dict(event)["payload"] == {"status": "verified"}


def test_event_payload_blocks_reachable_backing_store_bypasses() -> None:
    event = build_event(
        payload={
            "metadata": {"reviewed": True},
            "extensions": {"vendor.example": {"classification": "internal"}},
            "evidence_link": {
                "subject_event_id": "evt_root",
                "verification_status": "verified",
            },
            "evidence": [{"id": "ev_1", "tags": ["observed", "verified"]}],
        }
    )
    original = serialize_event(event)
    original_digest = event.integrity.event_hash

    assert not hasattr(event.payload, "_values")
    assert not hasattr(event.payload["metadata"], "_values")
    assert not hasattr(event.payload["evidence"], "_values")

    with pytest.raises(TypeError):
        event.payload._values = {"replaced": True}  # type: ignore[attr-defined]
    with pytest.raises(TypeError):
        event.payload["metadata"]._values = {"reviewed": False}
    with pytest.raises(TypeError):
        event.payload["evidence"]._values = ({"id": "ev_tampered"},)
    with pytest.raises(TypeError):
        event.payload._items = (("replaced", True),)  # type: ignore[attr-defined]
    with pytest.raises(TypeError):
        event.payload["metadata"]._items = (("reviewed", False),)
    with pytest.raises(TypeError):
        event.payload["evidence"]._items = ("changed",)
    with pytest.raises(TypeError):
        del event.payload._items  # type: ignore[attr-defined]

    backing_items = event.payload._items  # type: ignore[attr-defined]
    assert isinstance(backing_items, tuple)
    nested_mapping = dict(backing_items)["metadata"]
    nested_sequence = dict(backing_items)["evidence"]
    with pytest.raises(TypeError):
        nested_mapping._items = (("reviewed", False),)
    with pytest.raises(TypeError):
        nested_sequence._items = ({"id": "ev_tampered"},)

    assert serialize_event(event) == original
    assert event.integrity.event_hash == original_digest
    assert event_to_dict(event)["payload"]["metadata"] == {"reviewed": True}


def test_event_payload_blocks_base_class_descriptor_mutation_bypasses() -> None:
    event = build_event(payload={"items": [{"id": "ev_1"}], "metadata": {"reviewed": True}})
    original = serialize_event(event)
    items = event.payload["items"]
    first_item = items[0]

    with pytest.raises(TypeError):
        dict.__setitem__(event.payload, "tampered", True)  # type: ignore[arg-type]
    with pytest.raises(TypeError):
        dict.update(event.payload, {"tampered": True})  # type: ignore[arg-type]
    with pytest.raises(TypeError):
        list.append(items, {"id": "ev_2"})  # type: ignore[arg-type]
    with pytest.raises(TypeError):
        list.__setitem__(items, 0, {"id": "ev_tampered"})  # type: ignore[arg-type]
    with pytest.raises(TypeError):
        dict.__setitem__(first_item, "id", "ev_tampered")  # type: ignore[arg-type]

    assert serialize_event(event) == original


def test_event_payload_is_not_mutated_by_source_aliases() -> None:
    source: dict[str, Any] = {"nested": []}
    event = build_event(payload=source)
    original = serialize_event(event)

    source["nested"].append("changed")
    source["added"] = True

    assert serialize_event(event) == original
    assert event_to_dict(event)["payload"] == {"nested": []}


def test_event_payload_aliases_do_not_cross_events() -> None:
    source: dict[str, Any] = {"nested": {"x": 1}, "items": [{"id": "ev_1"}]}
    first = build_event(payload=source)
    second = build_event(payload=source)
    first_original = serialize_event(first)
    second_original = serialize_event(second)

    source["nested"]["x"] = 999
    source["items"][0]["id"] = "ev_tampered"
    source["items"].append({"id": "ev_2"})

    with pytest.raises(TypeError):
        first.payload["nested"]._items = (("x", 999),)
    with pytest.raises(TypeError):
        second.payload["items"][0]._items = (("id", "ev_tampered"),)

    assert serialize_event(first) == first_original
    assert serialize_event(second) == second_original
    assert event_to_dict(first)["payload"] == {"nested": {"x": 1}, "items": [{"id": "ev_1"}]}
    assert event_to_dict(second)["payload"] == {"nested": {"x": 1}, "items": [{"id": "ev_1"}]}


def test_event_model_copy_update_revalidates_payload_immutability() -> None:
    event = build_event(payload={"items": []})

    copied = event.model_copy(update={"payload": {"items": []}})
    original = serialize_event(copied)

    with pytest.raises(TypeError):
        copied.payload["items"].append("changed")  # type: ignore[union-attr]
    with pytest.raises(TypeError):
        list.append(copied.payload["items"], "changed")  # type: ignore[arg-type]
    with pytest.raises(TypeError):
        copied.payload._values = {"items": ["changed"]}  # type: ignore[attr-defined]
    with pytest.raises(TypeError):
        copied.payload["items"]._items = ("changed",)

    assert serialize_event(copied) == original


def test_event_model_construct_revalidates_payload_immutability() -> None:
    event_data = event_to_dict(build_event(payload={"items": []}))
    event_data["payload"] = {"items": []}

    constructed = EventEnvelope.model_construct(**event_data)
    original = serialize_event(constructed)

    with pytest.raises(TypeError):
        constructed.payload["items"].append("changed")  # type: ignore[union-attr]
    with pytest.raises(TypeError):
        list.append(constructed.payload["items"], "changed")  # type: ignore[arg-type]
    with pytest.raises(TypeError):
        constructed.payload._values = {"items": ["changed"]}  # type: ignore[attr-defined]
    with pytest.raises(TypeError):
        constructed.payload["items"]._items = ("changed",)

    assert serialize_event(constructed) == original


def test_event_payload_copy_deepcopy_and_pickle_keep_payload_sealed() -> None:
    event = build_event(payload={"nested": {"x": 1}, "items": [{"id": "ev_1"}]})
    original_payload = event_to_dict(event)["payload"]

    for copied in (
        copy.copy(event),
        copy.deepcopy(event),
        pickle.loads(pickle.dumps(event)),
    ):
        original = serialize_event(copied)

        with pytest.raises(TypeError):
            copied.payload._values = {"nested": {"x": 999}}  # type: ignore[attr-defined]
        with pytest.raises(TypeError):
            copied.payload["nested"]._items = (("x", 999),)
        with pytest.raises(TypeError):
            copied.payload["items"][0]["id"] = "ev_tampered"  # type: ignore[index]

        assert serialize_event(copied) == original
        assert event_to_dict(copied)["payload"] == original_payload


@pytest.mark.parametrize("value", [math.nan, math.inf, -math.inf])
def test_non_finite_payload_numbers_are_rejected(value: float) -> None:
    with pytest.raises(ValidationError, match="non-finite"):
        build_event(payload={"number": value})

    with pytest.raises(ValidationError, match="non-finite"):
        build_event(payload={"nested": [value]})


def test_payload_rejects_json_depth_over_default_limit() -> None:
    value: object = "leaf"
    for _ in range(DEFAULT_JSON_MAX_DEPTH + 2):
        value = [value]

    with pytest.raises(ValidationError, match="JSON depth"):
        build_event(payload={"nested": value})


def test_payload_rejects_object_member_count_over_default_limit() -> None:
    payload = {f"k{i}": i for i in range(DEFAULT_JSON_MAX_OBJECT_MEMBERS + 1)}

    with pytest.raises(ValidationError, match="object exceeds"):
        build_event(payload=payload)


def test_payload_rejects_array_length_over_default_limit() -> None:
    payload = {"items": list(range(DEFAULT_JSON_MAX_ARRAY_LENGTH + 1))}

    with pytest.raises(ValidationError, match="array exceeds"):
        build_event(payload=payload)
