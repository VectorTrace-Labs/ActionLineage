from __future__ import annotations

import json
import logging
from typing import Any

import pytest

from actionlineage.domain import (
    RedactionError,
    RedactionPolicy,
    capture_bytes,
    serialize_event_for_persistence,
)
from actionlineage.domain.events import JsonValue
from tests.domain.test_events import build_event

CANARY_TOKEN = "al_canary_token_123456789"
CANARY_BEARER = f"Bearer {CANARY_TOKEN}"


def test_canary_bearer_token_is_absent_from_serialized_event_and_logs(
    caplog: pytest.LogCaptureFixture,
) -> None:
    event = build_event(
        payload={
            "message": f"please send {CANARY_BEARER}",
            "headers": {"authorization": CANARY_BEARER},
        }
    )

    with caplog.at_level(logging.INFO, logger="actionlineage.domain.serialization"):
        serialized = serialize_event_for_persistence(event).decode("utf-8")

    assert CANARY_TOKEN not in serialized
    assert CANARY_BEARER not in serialized
    assert CANARY_TOKEN not in caplog.text
    assert CANARY_BEARER not in caplog.text
    assert event.event_id in caplog.text


def test_configured_sensitive_json_path_is_redacted_before_persistence() -> None:
    raw_secret = "path-secret-value-123456789"
    event = build_event(
        payload={
            "arguments": {
                "client_secret_value": raw_secret,
                "benign": "kept",
            }
        }
    )
    policy = RedactionPolicy.from_paths(("payload.arguments.client_secret_value",))

    serialized = serialize_event_for_persistence(event, redaction_policy=policy)
    serialized_text = serialized.decode("utf-8")
    data = json.loads(serialized_text)

    assert raw_secret not in serialized_text
    assert data["payload"]["arguments"]["client_secret_value"]["marker"] == (
        "actionlineage.redacted.v1"
    )
    assert data["payload"]["arguments"]["benign"] == "kept"


def test_oversized_payload_is_truncated_with_metadata_and_digest() -> None:
    oversized_value = "x" * 80
    event = build_event(payload={"body": oversized_value})
    policy = RedactionPolicy(max_string_length=12)

    serialized = serialize_event_for_persistence(event, redaction_policy=policy)
    data = json.loads(serialized)
    captured = data["payload"]["body"]

    assert oversized_value not in serialized.decode("utf-8")
    assert captured["marker"] == "actionlineage.capture.v1"
    assert captured["encoding"] == "text"
    assert captured["value"] == "x" * 12
    assert captured["original_length"] == 80
    assert captured["captured_length"] == 12
    assert captured["truncated"] is True
    assert captured["digest"].startswith("sha256:")


def test_bytes_capture_is_bounded_and_json_compatible() -> None:
    captured = capture_bytes(b"abcdef", max_length=3)

    assert captured["marker"] == "actionlineage.capture.v1"
    assert captured["encoding"] == "base64"
    assert captured["value"] == "YWJj"
    assert captured["original_length"] == 6
    assert captured["captured_length"] == 3
    assert captured["truncated"] is True
    assert str(captured["digest"]).startswith("sha256:")


def test_redaction_failure_cannot_silently_serialize_original_value() -> None:
    raw_secret = "failure-secret-123456789"
    event = build_event(payload={"note": raw_secret})

    class FailingBoundary:
        def apply(self, value: object) -> JsonValue:
            raise RuntimeError("simulated redaction failure")

    with pytest.raises(RedactionError) as exc_info:
        serialize_event_for_persistence(event, redaction_policy=FailingBoundary())

    assert raw_secret not in str(exc_info.value)


def test_non_json_values_fail_closed_before_persistence() -> None:
    event_data: dict[str, Any] = {"payload": object()}

    with pytest.raises(RedactionError, match="redaction failed before persistence"):
        RedactionPolicy().apply(event_data)
