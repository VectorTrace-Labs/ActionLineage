"""Public exception types for ActionLineage APIs."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import TypeGuard

from pydantic import ValidationError


class ActionLineageError(RuntimeError):
    """Base class for public ActionLineage failures."""


class ActionLineageValidationError(ActionLineageError):
    """Raised when caller-provided evidence does not match a public contract."""


class EventParseError(ActionLineageValidationError):
    """Raised when serialized event data cannot be parsed safely."""

    def __init__(
        self,
        *,
        error_count: int,
        first_error_path: str | None,
    ) -> None:
        message = "event data is not a valid ActionLineage event"
        if first_error_path is not None:
            message = f"{message}; first invalid field: {first_error_path}"
        super().__init__(message)
        self.error_count = error_count
        self.first_error_path = first_error_path


def event_parse_error_from_validation(exc: ValidationError) -> EventParseError:
    """Create a redacted public parse error from a Pydantic validation error."""

    errors = exc.errors(include_input=False, include_url=False)
    first_error_path = None
    if errors:
        location = errors[0].get("loc")
        if isinstance(location, tuple):
            first_error_path = ".".join(str(part) for part in location)
        elif isinstance(location, str):
            first_error_path = location

    return EventParseError(error_count=len(errors), first_error_path=first_error_path)


def safe_error_detail(
    exc: Exception,
    *,
    validation_message: str = "request validation failed",
) -> str:
    """Return a redacted, public-safe error detail string."""

    if isinstance(exc, ValidationError):
        return validation_message
    return redact_error_text(str(exc))


def redact_error_text(message: str) -> str:
    """Redact and bound an error string before it reaches logs or public output."""

    from actionlineage.domain.redaction import RedactionPolicy

    try:
        redacted = RedactionPolicy(max_string_length=512).apply(message)
    except Exception:
        return "error detail could not be redacted safely"
    if isinstance(redacted, str):
        return redacted
    if _is_capture_marker(redacted):
        return _capture_limit_note(redacted)
    return json.dumps(redacted, sort_keys=True)


def _is_capture_marker(value: object) -> TypeGuard[Mapping[str, object]]:
    return isinstance(value, Mapping) and value.get("marker") == "actionlineage.capture.v1"


def _capture_limit_note(metadata: Mapping[str, object]) -> str:
    original_length = metadata.get("original_length", "unknown")
    digest = metadata.get("digest", "unknown")
    digest_scope = metadata.get("digest_scope", "unknown")
    return (
        f"[TRUNCATED original_length={original_length} digest={digest} digest_scope={digest_scope}]"
    )
