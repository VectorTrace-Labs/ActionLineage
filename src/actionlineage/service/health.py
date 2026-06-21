"""Local service health checks."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from actionlineage.journal import verify_journal


class HealthState(StrEnum):
    """Service health state."""

    OK = "ok"
    DEGRADED = "degraded"


@dataclass(frozen=True, slots=True)
class HealthIssue:
    """One health issue."""

    code: str
    message: str

    def as_dict(self) -> dict[str, object]:
        return {"code": self.code, "message": self.message}


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
    verification = verify_journal(journal_path)
    if not verification.ok:
        issues.append(
            HealthIssue(
                code="journal_degraded",
                message="local journal verification failed",
            )
        )
    if database_path is not None and not Path(database_path).exists():
        issues.append(
            HealthIssue(
                code="projection_missing",
                message="projection database does not exist or has not been rebuilt",
            )
        )
    return HealthReport(
        state=HealthState.DEGRADED if issues else HealthState.OK,
        issues=tuple(issues),
    )
