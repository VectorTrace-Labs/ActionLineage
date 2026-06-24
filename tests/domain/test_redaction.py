from __future__ import annotations

import hashlib
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
from actionlineage.domain.redaction import (
    CAPTURE_DIGEST_SCOPE,
    sha256_capture_bytes,
    sha256_capture_text,
)
from actionlineage.domain.serialization import normalize_json
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
    assert captured["digest"] == sha256_capture_text(oversized_value)
    assert captured["digest"] != f"sha256:{hashlib.sha256(oversized_value.encode()).hexdigest()}"
    assert captured["digest_scope"] == CAPTURE_DIGEST_SCOPE


def test_bytes_capture_is_bounded_and_json_compatible() -> None:
    captured = capture_bytes(b"abcdef", max_length=3)

    assert captured["marker"] == "actionlineage.capture.v1"
    assert captured["encoding"] == "base64"
    assert captured["value"] == "YWJj"
    assert captured["original_length"] == 6
    assert captured["captured_length"] == 3
    assert captured["truncated"] is True
    assert captured["digest"] == sha256_capture_bytes(b"abcdef")
    assert captured["digest"] != f"sha256:{hashlib.sha256(b'abcdef').hexdigest()}"
    assert captured["digest_scope"] == CAPTURE_DIGEST_SCOPE


def test_capture_digest_scope_separates_text_and_bytes() -> None:
    assert sha256_capture_text("abcdef") != sha256_capture_bytes(b"abcdef")


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


def test_redaction_rejects_json_structure_limits() -> None:
    with pytest.raises(RedactionError, match="redaction failed before persistence"):
        RedactionPolicy(max_json_depth=1).apply({"a": {"b": {"c": "too deep"}}})

    with pytest.raises(RedactionError, match="redaction failed before persistence"):
        RedactionPolicy(max_object_members=1).apply({"a": 1, "b": 2})

    with pytest.raises(RedactionError, match="redaction failed before persistence"):
        RedactionPolicy(max_array_length=1).apply({"items": [1, 2]})


def test_redaction_does_not_traverse_sensitive_subtree_for_structure_limits() -> None:
    result = RedactionPolicy(max_json_depth=0).apply(
        {"password": {"nested": [{"secret": "raw-secret"}]}}
    )

    assert isinstance(result, dict)
    assert result["password"]["marker"] == "actionlineage.redacted.v1"


def test_normalize_json_rejects_json_structure_limits() -> None:
    with pytest.raises(TypeError, match="JSON depth"):
        normalize_json({"a": {"b": "too deep"}}, max_depth=1)

    with pytest.raises(TypeError, match="JSON object"):
        normalize_json({"a": 1, "b": 2}, max_object_members=1)

    with pytest.raises(TypeError, match="JSON array"):
        normalize_json([1, 2], max_array_length=1)
