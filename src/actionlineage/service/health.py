"""Local service health checks."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from actionlineage.journal import JournalError, verify_journal
from actionlineage.projection import (
    ProjectionStateCode,
    ProjectionStateError,
    verify_projection_state,
)


class HealthState(StrEnum):
    """Service health state."""

    OK = "ok"
    DEGRADED = "degraded"


@dataclass(frozen=True, slots=True)
class HealthIssue:
    """One health issue."""

    code: str
    message: str
    details: dict[str, object] | None = None

    def as_dict(self) -> dict[str, object]:
        return {
            "code": self.code,
            "message": self.message,
            "details": deepcopy(self.details) if self.details is not None else {},
        }


@dataclass(frozen=True, slots=True)
class HealthReport:
    """Machine-readable local health report."""

    state: HealthState
    issues: tuple[HealthIssue, ...]

    @property
    def ok(self) -> bool:
        return self.state == HealthState.OK

    def as_dict(self) -> dict[str, object]:
        return {
            "ok": self.ok,
            "state": self.state.value,
            "issues": [issue.as_dict() for issue in self.issues],
        }


def check_local_health(*, journal_path: Path, database_path: Path | None = None) -> HealthReport:
    """Check local journal and projection health without mutating state."""

    issues: list[HealthIssue] = []
    try:
        verification = verify_journal(journal_path)
    except JournalError as exc:
        issues.append(
            HealthIssue(
                code="journal_unavailable",
                message="local journal could not be locked or read for verification",
                details={"error_type": type(exc).__name__},
            )
        )
        verification = None
    if verification is not None and not verification.ok:
        issues.append(
            HealthIssue(
                code=ProjectionStateCode.JOURNAL_INVALID.value,
                message="local journal verification failed",
                details={"verification": verification.as_dict()},
            )
        )
    if database_path is not None and verification is not None and verification.ok:
        try:
            verify_projection_state(database_path, journal_path=journal_path)
        except ProjectionStateError as exc:
            issues.append(
                HealthIssue(
                    code=exc.code.value,
                    message=str(exc),
                    details=exc.details,
                )
            )
    return HealthReport(
        state=HealthState.DEGRADED if issues else HealthState.OK,
        issues=tuple(issues),
    )
