"""Machine-readable journal verification results."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

type VerificationCode = Literal[
    "empty_record",
    "truncated_record",
    "parse_error",
    "sequence_mismatch",
    "previous_hash_mismatch",
    "event_hash_missing",
    "event_hash_mismatch",
    "expected_record_count_mismatch",
    "expected_last_hash_mismatch",
]


class VerificationIssue(BaseModel):
    """One machine-readable verification failure."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    record_number: int = Field(ge=0)
    code: VerificationCode
    message: str
    event_id: str | None = None
    expected: str | int | None = None
    actual: str | int | None = None


class VerificationResult(BaseModel):
    """Machine-readable journal verification result."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    ok: bool
    records_verified: int = Field(ge=0)
    last_event_hash: str | None
    issues: tuple[VerificationIssue, ...] = ()

    def as_dict(self) -> dict[str, object]:
        """Return a JSON-compatible result object."""

        return self.model_dump(mode="json")
