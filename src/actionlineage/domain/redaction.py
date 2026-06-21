"""Fail-closed pre-persistence redaction and bounded capture."""

from __future__ import annotations

import base64
import hashlib
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Literal, Protocol, cast

from actionlineage.domain.events import JsonValue

type Path = tuple[str, ...]
type CaptureMarker = Literal["actionlineage.capture.v1"]

REDACTED_VALUE = "[REDACTED:sensitive]"
DEFAULT_MAX_STRING_LENGTH = 4096
DEFAULT_MAX_BYTES_LENGTH = 4096
DEFAULT_SENSITIVE_FIELD_NAMES = frozenset(
    {
        "api_key",
        "apikey",
        "authorization",
        "bearer_token",
        "cookie",
        "password",
        "private_key",
        "secret",
        "session_cookie",
        "token",
        "x_api_key",
    }
)


class RedactionError(RuntimeError):
    """Raised when data cannot be safely redacted for persistence."""


class RedactionBoundary(Protocol):
    """Protocol for fail-closed redaction policies."""

    def apply(self, value: object) -> JsonValue:
        """Return a redacted JSON-compatible value or raise."""


@dataclass(frozen=True, slots=True)
class CaptureMetadata:
    """Metadata emitted when content is bounded before serialization."""

    marker: CaptureMarker
    encoding: Literal["text", "base64"]
    value: str
    original_length: int
    captured_length: int
    truncated: bool
    digest: str

    def as_json(self) -> dict[str, JsonValue]:
        return {
            "marker": self.marker,
            "encoding": self.encoding,
            "value": self.value,
            "original_length": self.original_length,
            "captured_length": self.captured_length,
            "truncated": self.truncated,
            "digest": self.digest,
        }


@dataclass(frozen=True, slots=True)
class RedactionPattern:
    """Named regex replacement used by a redaction policy."""

    name: str
    pattern: re.Pattern[str]
    replacement: str

    def apply(self, value: str) -> str:
        return self.pattern.sub(self.replacement, value)


@dataclass(frozen=True, slots=True)
class RedactionPolicy:
    """Structured redaction policy for event persistence boundaries."""

    sensitive_paths: frozenset[Path] = field(default_factory=frozenset)
    sensitive_field_names: frozenset[str] = DEFAULT_SENSITIVE_FIELD_NAMES
    max_string_length: int = DEFAULT_MAX_STRING_LENGTH
    max_bytes_length: int = DEFAULT_MAX_BYTES_LENGTH
    patterns: tuple[RedactionPattern, ...] = field(default_factory=lambda: DEFAULT_PATTERNS)

    @classmethod
    def from_paths(
        cls,
        paths: Sequence[str | Sequence[str]],
        *,
        max_string_length: int = DEFAULT_MAX_STRING_LENGTH,
        max_bytes_length: int = DEFAULT_MAX_BYTES_LENGTH,
    ) -> RedactionPolicy:
        return cls(
            sensitive_paths=frozenset(normalize_path(path) for path in paths),
            max_string_length=max_string_length,
            max_bytes_length=max_bytes_length,
        )

    def apply(self, value: object) -> JsonValue:
        try:
            return redact_value(value, path=(), policy=self)
        except Exception as exc:
            raise RedactionError("redaction failed before persistence") from exc


def normalize_path(path: str | Sequence[str]) -> Path:
    """Normalize dot-separated or sequence paths for matching."""

    if isinstance(path, str):
        parts = tuple(part for part in path.split(".") if part)
    else:
        parts = tuple(str(part) for part in path)
    if not parts:
        raise ValueError("sensitive path cannot be empty")
    return tuple(part.lower() for part in parts)


def redact_value(value: object, *, path: Path, policy: RedactionPolicy) -> JsonValue:
    """Redact an arbitrary value into a JSON-compatible value."""

    if is_sensitive_path(path, policy) or is_sensitive_field(path, policy):
        return redacted_marker("sensitive")

    if isinstance(value, str):
        return capture_string(redact_text(value, policy), max_length=policy.max_string_length)

    if isinstance(value, bytes):
        return capture_bytes(value, max_length=policy.max_bytes_length)

    if value is None or isinstance(value, bool | int | float):
        return cast(JsonValue, value)

    if isinstance(value, Mapping):
        redacted: dict[str, JsonValue] = {}
        for raw_key, raw_child in value.items():
            if not isinstance(raw_key, str):
                raise RedactionError("redaction only supports string object keys")
            redacted[raw_key] = redact_value(
                raw_child,
                path=(*path, raw_key.lower()),
                policy=policy,
            )
        return redacted

    if isinstance(value, Sequence) and not isinstance(value, str | bytes | bytearray):
        return [redact_value(child, path=path, policy=policy) for child in value]

    raise RedactionError(f"unsupported value type for redaction: {type(value).__name__}")


def redact_text(value: str, policy: RedactionPolicy) -> str:
    redacted = value
    for pattern in policy.patterns:
        redacted = pattern.apply(redacted)
    return redacted


def is_sensitive_path(path: Path, policy: RedactionPolicy) -> bool:
    return path in policy.sensitive_paths


def is_sensitive_field(path: Path, policy: RedactionPolicy) -> bool:
    if not path:
        return False
    normalized_name = path[-1].replace("-", "_").lower()
    return normalized_name in policy.sensitive_field_names


def redacted_marker(reason: str) -> dict[str, JsonValue]:
    return {
        "marker": "actionlineage.redacted.v1",
        "reason": reason,
        "value": REDACTED_VALUE,
    }


def capture_string(value: str, *, max_length: int = DEFAULT_MAX_STRING_LENGTH) -> JsonValue:
    if max_length < 0:
        raise ValueError("max_length must be non-negative")
    if len(value) <= max_length:
        return value
    captured = value[:max_length]
    return CaptureMetadata(
        marker="actionlineage.capture.v1",
        encoding="text",
        value=captured,
        original_length=len(value),
        captured_length=len(captured),
        truncated=True,
        digest=sha256_text(value),
    ).as_json()


def capture_bytes(
    value: bytes,
    *,
    max_length: int = DEFAULT_MAX_BYTES_LENGTH,
) -> dict[str, JsonValue]:
    if max_length < 0:
        raise ValueError("max_length must be non-negative")
    captured = value[:max_length]
    return CaptureMetadata(
        marker="actionlineage.capture.v1",
        encoding="base64",
        value=base64.b64encode(captured).decode("ascii"),
        original_length=len(value),
        captured_length=len(captured),
        truncated=len(value) > max_length,
        digest=sha256_bytes(value),
    ).as_json()


def sha256_text(value: str) -> str:
    return sha256_bytes(value.encode("utf-8"))


def sha256_bytes(value: bytes) -> str:
    return f"sha256:{hashlib.sha256(value).hexdigest()}"


DEFAULT_PATTERNS: tuple[RedactionPattern, ...] = (
    RedactionPattern(
        name="private_key",
        pattern=re.compile(
            r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?-----END [A-Z ]*PRIVATE KEY-----",
            re.DOTALL,
        ),
        replacement="[REDACTED:private_key]",
    ),
    RedactionPattern(
        name="bearer_token",
        pattern=re.compile(r"\bBearer\s+[A-Za-z0-9._~+/=-]{8,}\b"),
        replacement="Bearer [REDACTED:bearer_token]",
    ),
    RedactionPattern(
        name="key_value_secret",
        pattern=re.compile(
            r"(?i)\b(api[_-]?key|token|password|secret)\b\s*[:=]\s*['\"]?"
            r"[A-Za-z0-9._~+/=-]{8,}['\"]?"
        ),
        replacement=r"\1=[REDACTED:secret]",
    ),
)
