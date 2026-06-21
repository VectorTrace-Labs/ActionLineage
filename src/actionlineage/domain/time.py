"""Injectable clocks for deterministic event construction."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol


class Clock(Protocol):
    """Clock interface used by callers that construct events."""

    def now(self) -> datetime:
        """Return the current timezone-aware UTC time."""


@dataclass(frozen=True, slots=True)
class FixedClock:
    """Clock that always returns the same UTC instant."""

    value: datetime

    def now(self) -> datetime:
        if self.value.tzinfo is None or self.value.tzinfo.utcoffset(self.value) is None:
            raise ValueError("fixed clock value must be timezone-aware")
        return self.value.astimezone(UTC)


@dataclass(frozen=True, slots=True)
class SystemClock:
    """System UTC clock."""

    def now(self) -> datetime:
        return datetime.now(UTC)
