"""Deterministic event serialization and pre-persistence redaction boundary."""

from __future__ import annotations

import json
import logging
import math
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any, cast

from pydantic import ValidationError

from actionlineage.domain.events import (
    DEFAULT_JSON_MAX_ARRAY_LENGTH,
    DEFAULT_JSON_MAX_DEPTH,
    DEFAULT_JSON_MAX_OBJECT_MEMBERS,
    EventEnvelope,
    JsonObject,
    JsonValue,
    model_json,
)
from actionlineage.domain.redaction import RedactionBoundary, RedactionError, RedactionPolicy
from actionlineage.errors import EventParseError, event_parse_error_from_validation

LOGGER = logging.getLogger(__name__)


def event_to_dict(event: EventEnvelope) -> JsonObject:
    """Return the JSON-compatible event object before persistence redaction."""

    return cast(JsonObject, normalize_json(model_json(event)))


def event_from_json(data: str | bytes) -> EventEnvelope:
    """Validate a serialized event against the typed event model."""

    return EventEnvelope.model_validate_json(data)


def parse_event(data: str | bytes) -> EventEnvelope:
    """Parse serialized event data and raise redacted public errors."""

    try:
        return event_from_json(data)
    except ValidationError as exc:
        raise event_parse_error_from_validation(exc) from None
    except ValueError as exc:
        raise EventParseError(error_count=1, first_error_path=None) from exc


def serialize_event(event: EventEnvelope) -> bytes:
    """Serialize an event deterministically without applying redaction."""

    return deterministic_json_bytes(event_to_dict(event))


def serialize_event_for_persistence(
    event: EventEnvelope,
    *,
    redaction_policy: RedactionBoundary | None = None,
) -> bytes:
    """Redact then serialize an event for any persistence, export, or hashing boundary."""

    policy = redaction_policy or RedactionPolicy()
    try:
        redacted = policy.apply(event_to_dict(event))
    except Exception as exc:
        raise RedactionError("redaction failed before event serialization") from exc

    if not isinstance(redacted, dict):
        raise RedactionError("event redaction produced a non-object value")

    LOGGER.info(
        "serialized lineage event for persistence event_id=%s event_type=%s",
        event.event_id,
        str(event.event_type),
    )
    return deterministic_json_bytes(redacted)


def deterministic_json_bytes(value: JsonObject) -> bytes:
    """Serialize JSON-compatible data with deterministic key ordering.

    This is an interim domain serialization interface. It is intentionally not
    the final journal hash-chain canonicalization algorithm.
    """

    return json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
        allow_nan=False,
    ).encode("utf-8")


def normalize_json(
    value: Any,
    *,
    max_depth: int = DEFAULT_JSON_MAX_DEPTH,
    max_object_members: int = DEFAULT_JSON_MAX_OBJECT_MEMBERS,
    max_array_length: int = DEFAULT_JSON_MAX_ARRAY_LENGTH,
    _depth: int = 0,
) -> JsonValue:
    """Normalize supported Python values into deterministic JSON-compatible values."""

    if _depth > max_depth:
        raise TypeError(f"JSON depth exceeds {max_depth}")

    if isinstance(value, datetime):
        return canonical_timestamp(value)

    if isinstance(value, Mapping):
        if len(value) > max_object_members:
            raise TypeError(f"JSON object exceeds {max_object_members} members")
        normalized: dict[str, JsonValue] = {}
        for key, child in value.items():
            if not isinstance(key, str):
                raise TypeError("JSON object keys must be strings")
            normalized[key] = normalize_json(
                child,
                max_depth=max_depth,
                max_object_members=max_object_members,
                max_array_length=max_array_length,
                _depth=_depth + 1,
            )
        return normalized

    if isinstance(value, list | tuple):
        if len(value) > max_array_length:
            raise TypeError(f"JSON array exceeds {max_array_length} items")
        return [
            normalize_json(
                child,
                max_depth=max_depth,
                max_object_members=max_object_members,
                max_array_length=max_array_length,
                _depth=_depth + 1,
            )
            for child in value
        ]

    if isinstance(value, float) and not math.isfinite(value):
        raise TypeError("JSON numbers must be finite")

    if value is None or isinstance(value, str | int | float | bool):
        return cast(JsonValue, value)

    raise TypeError(f"unsupported JSON value type: {type(value).__name__}")


def canonical_timestamp(value: datetime) -> str:
    """Serialize timezone-aware datetimes as UTC RFC 3339 strings ending in Z."""

    if value.tzinfo is None or value.tzinfo.utcoffset(value) is None:
        raise ValueError("timestamp must be timezone-aware")
    utc_value = value.astimezone(UTC)
    return utc_value.isoformat().replace("+00:00", "Z")
