"""Optional PostgreSQL projection rebuild helpers.

The append-only journal remains canonical. This module writes a rebuildable
PostgreSQL projection through a small executor protocol so ActionLineage does
not require a PostgreSQL driver in the core install.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from actionlineage.domain import EventEnvelope, serialize_event
from actionlineage.domain.events import event_type_value
from actionlineage.journal import verified_journal_snapshot
from actionlineage.projection.sqlite import (
    PROJECTION_SCHEMA_VERSION,
    ProjectionRebuildError,
    ProjectionVerificationError,
)

POSTGRES_PROJECTION_SCHEMA_VERSION = PROJECTION_SCHEMA_VERSION
POSTGRES_DEFAULT_TABLE = "actionlineage_events"
_IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


class PostgresExecutor(Protocol):
    """Minimal DB-API-style executor used by optional runtime integrations."""

    def execute(self, statement: str, parameters: Mapping[str, object] | None = None) -> object:
        """Execute one SQL statement with optional mapping parameters."""


@dataclass(frozen=True, slots=True)
class PostgresRebuildResult:
    """Machine-readable PostgreSQL projection rebuild result."""

    journal_path: Path
    table_name: str
    records_indexed: int
    last_event_hash: str | None
    schema_version: int = POSTGRES_PROJECTION_SCHEMA_VERSION

    def as_dict(self) -> dict[str, object]:
        """Return a JSON-compatible result object."""

        return {
            "ok": True,
            "journal_path": str(self.journal_path),
            "table_name": self.table_name,
            "records_indexed": self.records_indexed,
            "last_event_hash": self.last_event_hash,
            "schema_version": self.schema_version,
        }


def rebuild_postgres_projection(
    journal_path: Path,
    executor: PostgresExecutor,
    *,
    table_name: str = POSTGRES_DEFAULT_TABLE,
) -> PostgresRebuildResult:
    """Rebuild a PostgreSQL projection from a verified local journal."""

    journal_path = Path(journal_path)
    safe_table = _safe_identifier(table_name)
    snapshot = verified_journal_snapshot(journal_path)
    if not snapshot.ok:
        raise ProjectionVerificationError(journal_path, snapshot.verification)

    indexed_count = 0
    try:
        executor.execute("BEGIN")
        for statement in postgres_schema_statements(table_name=safe_table):
            executor.execute(statement)
        executor.execute(f"DELETE FROM {safe_table}")
        for record_number, event in enumerate(snapshot.events, start=1):
            executor.execute(
                postgres_insert_statement(table_name=safe_table),
                _event_projection_parameters(event, journal_record_number=record_number),
            )
            indexed_count += 1
        if indexed_count != snapshot.record_count:
            raise ProjectionRebuildError(
                "indexed record count does not match verified journal snapshot"
            )
        executor.execute(
            f"""
            INSERT INTO {safe_table}_metadata (key, value)
            VALUES
                ('schema_version', %(schema_version)s),
                ('source_journal_path', %(source_journal_path)s),
                ('records_indexed', %(records_indexed)s),
                ('last_event_hash', %(last_event_hash)s)
            ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value
            """,
            {
                "schema_version": str(POSTGRES_PROJECTION_SCHEMA_VERSION),
                "source_journal_path": str(journal_path),
                "records_indexed": str(indexed_count),
                "last_event_hash": snapshot.terminal_hash or "",
            },
        )
        executor.execute("COMMIT")
    except Exception as exc:
        _attempt_rollback(executor)
        if isinstance(exc, ProjectionRebuildError):
            raise
        raise ProjectionRebuildError("postgres projection rebuild failed") from exc

    return PostgresRebuildResult(
        journal_path=journal_path,
        table_name=safe_table,
        records_indexed=indexed_count,
        last_event_hash=snapshot.terminal_hash,
    )


def postgres_schema_statements(*, table_name: str = POSTGRES_DEFAULT_TABLE) -> tuple[str, ...]:
    """Return PostgreSQL DDL statements for the rebuildable projection."""

    safe_table = _safe_identifier(table_name)
    return (
        f"""
        CREATE TABLE IF NOT EXISTS {safe_table} (
            event_id TEXT PRIMARY KEY,
            spec_version TEXT NOT NULL,
            event_type TEXT NOT NULL,
            occurred_at TIMESTAMPTZ NOT NULL,
            observed_at TIMESTAMPTZ NOT NULL,
            trace_id TEXT NOT NULL,
            run_id TEXT NOT NULL,
            span_id TEXT,
            session_id TEXT,
            root_event_id TEXT NOT NULL,
            parent_event_id TEXT,
            sequence INTEGER NOT NULL,
            event_hash TEXT NOT NULL,
            previous_event_hash TEXT,
            verification_status TEXT,
            evidence_subject_event_id TEXT,
            evidence_event_id TEXT,
            journal_record_number INTEGER NOT NULL UNIQUE,
            event_json JSONB NOT NULL
        )
        """,
        f"CREATE INDEX IF NOT EXISTS {safe_table}_trace_idx ON {safe_table} (trace_id)",
        f"CREATE INDEX IF NOT EXISTS {safe_table}_run_idx ON {safe_table} (run_id)",
        f"CREATE INDEX IF NOT EXISTS {safe_table}_type_idx ON {safe_table} (event_type)",
        f"""
        CREATE INDEX IF NOT EXISTS {safe_table}_order_idx
        ON {safe_table} (occurred_at, sequence, journal_record_number, event_id)
        """,
        f"""
        CREATE INDEX IF NOT EXISTS {safe_table}_verification_idx
        ON {safe_table} (verification_status)
        """,
        f"""
        CREATE INDEX IF NOT EXISTS {safe_table}_evidence_idx
        ON {safe_table} (evidence_subject_event_id, evidence_event_id)
        """,
        f"""
        CREATE TABLE IF NOT EXISTS {safe_table}_metadata (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        )
        """,
    )


def postgres_insert_statement(*, table_name: str = POSTGRES_DEFAULT_TABLE) -> str:
    """Return the PostgreSQL insert statement for one projected event."""

    safe_table = _safe_identifier(table_name)
    return f"""
        INSERT INTO {safe_table} (
            event_id,
            spec_version,
            event_type,
            occurred_at,
            observed_at,
            trace_id,
            run_id,
            span_id,
            session_id,
            root_event_id,
            parent_event_id,
            sequence,
            event_hash,
            previous_event_hash,
            verification_status,
            evidence_subject_event_id,
            evidence_event_id,
            journal_record_number,
            event_json
        )
        VALUES (
            %(event_id)s,
            %(spec_version)s,
            %(event_type)s,
            %(occurred_at)s,
            %(observed_at)s,
            %(trace_id)s,
            %(run_id)s,
            %(span_id)s,
            %(session_id)s,
            %(root_event_id)s,
            %(parent_event_id)s,
            %(sequence)s,
            %(event_hash)s,
            %(previous_event_hash)s,
            %(verification_status)s,
            %(evidence_subject_event_id)s,
            %(evidence_event_id)s,
            %(journal_record_number)s,
            %(event_json)s::jsonb
        )
    """


def _event_projection_parameters(
    event: EventEnvelope,
    *,
    journal_record_number: int,
) -> Mapping[str, object]:
    if event.integrity.event_hash is None:
        raise ProjectionRebuildError("cannot project event without integrity.event_hash")

    payload = event.payload
    evidence_link = payload.get("evidence_link")
    evidence = evidence_link if isinstance(evidence_link, dict) else {}
    verification_status = _string_or_none(evidence.get("verification_status")) or _string_or_none(
        payload.get("verification_status")
    )
    return {
        "event_id": event.event_id,
        "spec_version": event.spec_version,
        "event_type": event_type_value(event.event_type),
        "occurred_at": event.occurred_at.isoformat(),
        "observed_at": event.observed_at.isoformat(),
        "trace_id": event.correlation.trace_id,
        "run_id": event.correlation.run_id,
        "span_id": event.correlation.span_id,
        "session_id": event.correlation.session_id,
        "root_event_id": event.causality.root_event_id,
        "parent_event_id": event.causality.parent_event_id,
        "sequence": event.causality.sequence,
        "event_hash": event.integrity.event_hash,
        "previous_event_hash": event.integrity.previous_event_hash,
        "verification_status": verification_status,
        "evidence_subject_event_id": _string_or_none(evidence.get("subject_event_id")),
        "evidence_event_id": _string_or_none(evidence.get("evidence_event_id")),
        "journal_record_number": journal_record_number,
        "event_json": serialize_event(event).decode("utf-8"),
    }


def _string_or_none(value: object) -> str | None:
    return value if isinstance(value, str) else None


def _safe_identifier(value: str) -> str:
    if not _IDENTIFIER_RE.match(value):
        raise ProjectionRebuildError(f"unsupported PostgreSQL identifier: {value}")
    return value


def _attempt_rollback(executor: PostgresExecutor) -> None:
    try:
        executor.execute("ROLLBACK")
    except Exception:
        return
