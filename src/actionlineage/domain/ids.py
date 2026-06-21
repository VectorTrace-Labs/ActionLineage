"""Injectable ID generation for deterministic tests and replay."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol
from uuid import uuid4


class IdGenerator(Protocol):
    """ID generator interface used by event-producing components."""

    def new_id(self, prefix: str) -> str:
        """Return a new stable identifier with the provided prefix."""


@dataclass(frozen=True, slots=True)
class FixedIdGenerator:
    """Deterministic ID generator for tests."""

    values: tuple[str, ...]
    index: int = 0

    def new_id(self, prefix: str) -> str:
        if self.index >= len(self.values):
            raise IndexError("fixed ID generator exhausted")
        value = self.values[self.index]
        if not value.startswith(f"{prefix}_"):
            raise ValueError(f"fixed ID {value!r} does not match prefix {prefix!r}")
        object.__setattr__(self, "index", self.index + 1)
        return value


@dataclass(frozen=True, slots=True)
class PrefixedUuidGenerator:
    """UUID-backed ID generator for production event construction."""

    def new_id(self, prefix: str) -> str:
        return f"{prefix}_{uuid4().hex}"
