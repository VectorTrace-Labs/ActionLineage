"""Fail-closed pre-persistence redaction and bounded capture."""

from __future__ import annotations

import base64
import hashlib
import math
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Literal, Protocol, cast

from actionlineage.domain.events import (
    DEFAULT_JSON_MAX_ARRAY_LENGTH,
    DEFAULT_JSON_MAX_DEPTH,
    DEFAULT_JSON_MAX_OBJECT_MEMBERS,
    JsonValue,
)

type Path = tuple[str, ...]
type CaptureMarker = Literal["actionlineage.capture.v1"]
type CaptureDigestScope = Literal["actionlineage.capture.v1/redaction-boundary"]

REDACTED_VALUE = "[REDACTED:sensitive]"
CAPTURE_DIGEST_SCOPE: CaptureDigestScope = "actionlineage.capture.v1/redaction-boundary"
DEFAULT_MAX_STRING_LENGTH = 4096
DEFAULT_MAX_BYTES_LENGTH = 4096
DEFAULT_MAX_CAPTURE_COUNT = 128
DEFAULT_MAX_CAPTURE_BYTES = 65536
DEFAULT_SENSITIVE_FIELD_NAMES = frozenset(
    {
        "access_token",
        "api_key",
        "apikey",
        "auth_token",
        "authorization",
        "aws_access_key_id",
        "aws_secret_access_key",
        "aws_session_token",
        "bearer_token",
        "client_secret",
        "client_secret_value",
        "cloud_session_token",
        "connection_string",
        "cookie",
        "database_dsn",
        "database_url",
        "db_url",
        "dsn",
        "id_token",
        "oauth_token",
        "password",
        "pre_signed_url",
        "presigned_url",
        "private_key_pem",
        "private_key",
        "proxy_authorization",
        "refresh_token",
        "secret",
        "security_token",
        "set_cookie",
        "signed_url",
        "signing_secret",
        "session_cookie",
        "session_token",
        "ssh_private_key",
        "token",
        "webhook_secret",
        "webhook_signature",
        "webhook_token",
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
    digest_scope: CaptureDigestScope = CAPTURE_DIGEST_SCOPE

    def as_json(self) -> dict[str, JsonValue]:
        return {
            "marker": self.marker,
            "encoding": self.encoding,
            "value": self.value,
            "original_length": self.original_length,
            "captured_length": self.captured_length,
            "truncated": self.truncated,
            "digest": self.digest,
            "digest_scope": self.digest_scope,
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
    max_capture_count: int = DEFAULT_MAX_CAPTURE_COUNT
    max_capture_bytes: int = DEFAULT_MAX_CAPTURE_BYTES
    max_json_depth: int = DEFAULT_JSON_MAX_DEPTH
    max_object_members: int = DEFAULT_JSON_MAX_OBJECT_MEMBERS
    max_array_length: int = DEFAULT_JSON_MAX_ARRAY_LENGTH
    patterns: tuple[RedactionPattern, ...] = field(default_factory=lambda: DEFAULT_PATTERNS)

    @classmethod
    def from_paths(
        cls,
        paths: Sequence[str | Sequence[str]],
        *,
        max_string_length: int = DEFAULT_MAX_STRING_LENGTH,
        max_bytes_length: int = DEFAULT_MAX_BYTES_LENGTH,
        max_capture_count: int = DEFAULT_MAX_CAPTURE_COUNT,
        max_capture_bytes: int = DEFAULT_MAX_CAPTURE_BYTES,
        max_json_depth: int = DEFAULT_JSON_MAX_DEPTH,
        max_object_members: int = DEFAULT_JSON_MAX_OBJECT_MEMBERS,
        max_array_length: int = DEFAULT_JSON_MAX_ARRAY_LENGTH,
    ) -> RedactionPolicy:
        return cls(
            sensitive_paths=frozenset(normalize_path(path) for path in paths),
            max_string_length=max_string_length,
            max_bytes_length=max_bytes_length,
            max_capture_count=max_capture_count,
            max_capture_bytes=max_capture_bytes,
            max_json_depth=max_json_depth,
            max_object_members=max_object_members,
            max_array_length=max_array_length,
        )

    def apply(self, value: object) -> JsonValue:
        try:
            return redact_value(value, path=(), policy=self, _capture_budget=capture_budget(self))
        except Exception as exc:
            raise RedactionError("redaction failed before persistence") from exc


@dataclass(slots=True)
class _CaptureBudget:
    """Aggregate capture budget for one redaction pass."""

    max_count: int
    max_bytes: int
    count: int = 0
    captured_bytes: int = 0

    def record(self, captured_bytes: int) -> None:
        if captured_bytes < 0:
            raise RedactionError("captured byte count cannot be negative")
        next_count = self.count + 1
        if next_count > self.max_count:
            raise RedactionError(f"captured value count exceeds {self.max_count}")
        next_bytes = self.captured_bytes + captured_bytes
        if next_bytes > self.max_bytes:
            raise RedactionError(f"captured bytes exceed {self.max_bytes}")
        self.count = next_count
        self.captured_bytes = next_bytes


def capture_budget(policy: RedactionPolicy) -> _CaptureBudget:
    if policy.max_capture_count < 0:
        raise RedactionError("max_capture_count must be non-negative")
    if policy.max_capture_bytes < 0:
        raise RedactionError("max_capture_bytes must be non-negative")
    return _CaptureBudget(
        max_count=policy.max_capture_count,
        max_bytes=policy.max_capture_bytes,
    )


def normalize_path(path: str | Sequence[str]) -> Path:
    """Normalize dot-separated or sequence paths for matching."""

    if isinstance(path, str):
        parts = tuple(part for part in path.split(".") if part)
    else:
        parts = tuple(str(part) for part in path)
    if not parts:
        raise ValueError("sensitive path cannot be empty")
    return tuple(part.lower() for part in parts)


def redact_value(
    value: object,
    *,
    path: Path,
    policy: RedactionPolicy,
    _depth: int = 0,
    _capture_budget: _CaptureBudget | None = None,
) -> JsonValue:
    """Redact an arbitrary value into a JSON-compatible value."""

    if is_sensitive_path(path, policy) or is_sensitive_field(path, policy):
        return redacted_marker("sensitive")

    if _depth > policy.max_json_depth:
        raise RedactionError(f"JSON depth exceeds {policy.max_json_depth}")

    if isinstance(value, str):
        captured = capture_string(redact_text(value, policy), max_length=policy.max_string_length)
        record_capture(captured, _capture_budget)
        return captured

    if isinstance(value, bytes):
        captured = capture_bytes(value, max_length=policy.max_bytes_length)
        record_capture(captured, _capture_budget)
        return captured

    if isinstance(value, float) and not math.isfinite(value):
        raise RedactionError("JSON numbers must be finite")

    if value is None or isinstance(value, bool | int | float):
        return cast(JsonValue, value)

    if isinstance(value, Mapping):
        if len(value) > policy.max_object_members:
            raise RedactionError(f"JSON object exceeds {policy.max_object_members} members")
        redacted: dict[str, JsonValue] = {}
        for raw_key, raw_child in value.items():
            if not isinstance(raw_key, str):
                raise RedactionError("redaction only supports string object keys")
            redacted[raw_key] = redact_value(
                raw_child,
                path=(*path, raw_key.lower()),
                policy=policy,
                _depth=_depth + 1,
                _capture_budget=_capture_budget,
            )
        return redacted

    if isinstance(value, Sequence) and not isinstance(value, str | bytes | bytearray):
        if len(value) > policy.max_array_length:
            raise RedactionError(f"JSON array exceeds {policy.max_array_length} items")
        return [
            redact_value(
                child,
                path=path,
                policy=policy,
                _depth=_depth + 1,
                _capture_budget=_capture_budget,
            )
            for child in value
        ]

    raise RedactionError(f"unsupported value type for redaction: {type(value).__name__}")


def record_capture(value: JsonValue, budget: _CaptureBudget | None) -> None:
    if budget is None or not isinstance(value, dict):
        return
    if value.get("marker") != "actionlineage.capture.v1":
        return
    captured = value.get("value")
    if not isinstance(captured, str):
        raise RedactionError("capture metadata value must be a string")
    encoding = value.get("encoding")
    if encoding == "text":
        budget.record(len(captured.encode("utf-8")))
        return
    if encoding == "base64":
        budget.record(len(captured))
        return
    raise RedactionError("capture metadata encoding is invalid")


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
        digest=sha256_capture_text(value),
        digest_scope=CAPTURE_DIGEST_SCOPE,
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
        digest=sha256_capture_bytes(value),
        digest_scope=CAPTURE_DIGEST_SCOPE,
    ).as_json()


def sha256_capture_text(value: str) -> str:
    return sha256_scoped_capture_bytes("text", value.encode("utf-8"))


def sha256_capture_bytes(value: bytes) -> str:
    return sha256_scoped_capture_bytes("base64", value)


def sha256_scoped_capture_bytes(encoding: Literal["text", "base64"], value: bytes) -> str:
    scope = CAPTURE_DIGEST_SCOPE.encode("ascii")
    preimage = b"\x00".join((scope, encoding.encode("ascii"), value))
    return sha256_bytes(preimage)


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
        name="database_url",
        pattern=re.compile(
            r"(?i)\b(?:postgres(?:ql)?|mysql|mariadb|mongodb(?:\+srv)?|redis|rediss|amqp|amqps)"
            r"://[^\s\"'<>]+"
        ),
        replacement="[REDACTED:database_url]",
    ),
    RedactionPattern(
        name="signed_url_parameter",
        pattern=re.compile(
            r"(?i)\b("
            r"x-amz-signature|x-amz-credential|x-amz-security-token|signature|sig|"
            r"access_token|refresh_token|client_secret|token"
            r")=([^&\s\"'<>]{8,})"
        ),
        replacement=r"\1=[REDACTED:secret]",
    ),
    RedactionPattern(
        name="key_value_secret",
        pattern=re.compile(
            r"(?i)(?<![A-Za-z0-9])("
            r"api[_-]?key|access[_-]?token|refresh[_-]?token|id[_-]?token|"
            r"client[_-]?secret|webhook[_-]?(?:secret|token|signature)|"
            r"signing[_-]?secret|session[_-]?token|security[_-]?token|"
            r"aws[_-]?secret[_-]?access[_-]?key|aws[_-]?session[_-]?token|"
            r"private[_-]?key|token|password|secret"
            r")(?![A-Za-z0-9])\s*[:=]\s*['\"]?"
            r"[A-Za-z0-9._~+/=-]{8,}['\"]?"
        ),
        replacement=r"\1=[REDACTED:secret]",
    ),
)
