"""Public exception types for ActionLineage APIs."""

from __future__ import annotations

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
