"""Optional PostgreSQL projection rebuild helpers.

The append-only journal remains canonical. This module writes a rebuildable
PostgreSQL projection through a small executor protocol so ActionLineage does
not require a PostgreSQL driver in the core install.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol, cast

from actionlineage.domain import (
    EventEnvelope,
    deterministic_json_bytes,
    event_to_dict,
    serialize_event,
)
from actionlineage.domain.events import JsonObject, event_type_value
from actionlineage.errors import safe_error_detail
from actionlineage.journal import (
    JOURNAL_SOURCE_IDENTITY_VERSION,
    VerifiedJournalSnapshot,
    journal_source_identity,
    verified_journal_snapshot,
)
from actionlineage.projection.sqlite import (
    PROJECTION_SCHEMA_VERSION,
    ProjectionRebuildError,
    ProjectionStateCode,
    ProjectionStateError,
    ProjectionVerificationError,
)

POSTGRES_PROJECTION_SCHEMA_VERSION = PROJECTION_SCHEMA_VERSION + 1
POSTGRES_DEFAULT_TABLE = "actionlineage_events"
POSTGRES_PROJECTED_EVENT_COLUMNS = (
    "event_id",
    "spec_version",
    "event_type",
    "occurred_at",
    "observed_at",
    "trace_id",
    "run_id",
    "span_id",
    "session_id",
    "root_event_id",
    "parent_event_id",
    "sequence",
    "event_hash",
    "previous_event_hash",
    "verification_status",
    "evidence_subject_event_id",
    "evidence_event_id",
    "journal_record_number",
    "event_json",
    "event_json_sha256",
)
_IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


class PostgresExecutor(Protocol):
    """Minimal DB-API-style executor used by optional runtime integrations."""

    def execute(self, statement: str, parameters: Mapping[str, object] | None = None) -> object:
        """Execute one SQL statement with optional mapping parameters."""


class PostgresProjectionReader(Protocol):
    """Minimal read protocol for verifying optional PostgreSQL projections."""

    def fetch_all(
        self,
        statement: str,
        parameters: Mapping[str, object] | None = None,
    ) -> Iterable[Mapping[str, object]]:
        """Return all rows for one SQL statement with optional mapping parameters."""


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


@dataclass(frozen=True, slots=True)
class VerifiedPostgresProjectionSnapshot:
    """PostgreSQL projection state bound to one verified journal snapshot."""

    journal_path: Path
    table_name: str
    journal_snapshot: VerifiedJournalSnapshot
    records_indexed: int
    last_event_hash: str | None
    source_journal_path: str
    source_journal_identity: str
    source_journal_sha256: str | None
    schema_version: int = POSTGRES_PROJECTION_SCHEMA_VERSION
    state: ProjectionStateCode = ProjectionStateCode.HEALTHY

    @property
    def record_count(self) -> int:
        """Number of records bound to the verified journal."""

        return self.journal_snapshot.record_count

    @property
    def terminal_hash(self) -> str | None:
        """Terminal hash bound to the verified journal."""

        return self.journal_snapshot.terminal_hash

    def as_dict(self) -> dict[str, object]:
        """Return a JSON-compatible verified projection state."""

        return {
            "state": self.state.value,
            "journal_path": str(self.journal_path),
            "table_name": self.table_name,
            "records_indexed": self.records_indexed,
            "record_count": self.record_count,
            "last_event_hash": self.last_event_hash,
            "terminal_hash": self.terminal_hash,
            "source_journal_path": self.source_journal_path,
            "source_journal_identity": self.source_journal_identity,
            "source_journal_sha256": self.source_journal_sha256,
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
                ('source_journal_identity', %(source_journal_identity)s),
                ('source_journal_identity_version', %(source_journal_identity_version)s),
                ('source_journal_sha256', %(source_journal_sha256)s),
                ('records_indexed', %(records_indexed)s),
                ('last_event_hash', %(last_event_hash)s)
            ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value
            """,
            {
                "schema_version": str(POSTGRES_PROJECTION_SCHEMA_VERSION),
                "source_journal_path": str(journal_path),
                "source_journal_identity": journal_source_identity(snapshot),
                "source_journal_identity_version": JOURNAL_SOURCE_IDENTITY_VERSION,
                "source_journal_sha256": snapshot.journal_sha256 or "",
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


def verify_postgres_projection_state(
    journal_path: Path,
    reader: PostgresProjectionReader,
    *,
    table_name: str = POSTGRES_DEFAULT_TABLE,
) -> VerifiedPostgresProjectionSnapshot:
    """Verify an optional PostgreSQL projection before any trusted read."""

    journal_path = Path(journal_path)
    safe_table = _safe_identifier(table_name)
    snapshot = verified_journal_snapshot(journal_path)
    if not snapshot.ok:
        raise ProjectionStateError(
            ProjectionStateCode.JOURNAL_INVALID,
            "source journal verification failed",
            details={"verification": snapshot.verification.as_dict()},
        )

    try:
        metadata = _fetch_postgres_metadata(reader, table_name=safe_table)
        records_indexed, last_event_hash = _verify_postgres_metadata(metadata, snapshot)
        rows = _fetch_postgres_projected_rows(reader, table_name=safe_table)
        _verify_postgres_projected_rows(rows, snapshot)
    except ProjectionStateError:
        raise
    except (KeyError, TypeError, ValueError) as exc:
        raise ProjectionStateError(
            ProjectionStateCode.PROJECTION_REBUILD_REQUIRED,
            "postgres projection metadata or rows are incomplete or invalid",
            details={"error": safe_error_detail(exc)},
        ) from exc
    except Exception as exc:
        raise ProjectionStateError(
            ProjectionStateCode.PROJECTION_UNAVAILABLE,
            "postgres projection could not be verified",
            details={"error_type": type(exc).__name__, "error": safe_error_detail(exc)},
        ) from exc

    return VerifiedPostgresProjectionSnapshot(
        journal_path=journal_path,
        table_name=safe_table,
        journal_snapshot=snapshot,
        records_indexed=records_indexed,
        last_event_hash=last_event_hash,
        source_journal_path=metadata["source_journal_path"],
        source_journal_identity=metadata["source_journal_identity"],
        source_journal_sha256=metadata.get("source_journal_sha256") or None,
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
            event_json JSONB NOT NULL,
            event_json_sha256 TEXT NOT NULL
        )
        """,
        f"""
        ALTER TABLE {safe_table}
        ADD COLUMN IF NOT EXISTS event_json_sha256 TEXT NOT NULL DEFAULT ''
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
            event_json,
            event_json_sha256
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
            %(event_json)s::jsonb,
            %(event_json_sha256)s
        )
    """


def _event_projection_parameters(
    event: EventEnvelope,
    *,
    journal_record_number: int,
) -> Mapping[str, object]:
    if event.integrity.event_hash is None:
        raise ProjectionRebuildError("cannot project event without integrity.event_hash")

    event_object = event_to_dict(event)
    event_json = serialize_event(event).decode("utf-8")
    payload = event.payload
    evidence_link = payload.get("evidence_link")
    evidence = evidence_link if isinstance(evidence_link, Mapping) else {}
    verification_status = _string_or_none(evidence.get("verification_status")) or _string_or_none(
        payload.get("verification_status")
    )
    return {
        "event_id": event.event_id,
        "spec_version": event.spec_version,
        "event_type": event_type_value(event.event_type),
        "occurred_at": event_object["occurred_at"],
        "observed_at": event_object["observed_at"],
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
        "event_json": event_json,
        "event_json_sha256": _sha256_text(event_json),
    }


def _fetch_postgres_metadata(
    reader: PostgresProjectionReader,
    *,
    table_name: str,
) -> dict[str, str]:
    rows = reader.fetch_all(f"SELECT key, value FROM {table_name}_metadata")
    metadata: dict[str, str] = {}
    for row in rows:
        key = row.get("key")
        value = row.get("value")
        if not isinstance(key, str) or not isinstance(value, str):
            raise ValueError("postgres projection metadata rows must expose text key/value fields")
        metadata[key] = value
    return metadata


def _verify_postgres_metadata(
    metadata: Mapping[str, str],
    snapshot: VerifiedJournalSnapshot,
) -> tuple[int, str | None]:
    schema_version = _postgres_metadata_int(metadata, "schema_version")
    if schema_version != POSTGRES_PROJECTION_SCHEMA_VERSION:
        raise ProjectionStateError(
            ProjectionStateCode.PROJECTION_REBUILD_REQUIRED,
            "postgres projection schema version is unsupported; rebuild required",
            details={
                "schema_version": schema_version,
                "expected_schema_version": POSTGRES_PROJECTION_SCHEMA_VERSION,
            },
        )

    source_journal_path = metadata.get("source_journal_path")
    if not source_journal_path:
        raise ValueError("postgres projection metadata is missing source_journal_path")

    records_indexed = _postgres_metadata_int(metadata, "records_indexed")
    last_event_hash = _postgres_metadata_hash(metadata, "last_event_hash")
    expected_identity = journal_source_identity(snapshot)
    stored_identity = metadata.get("source_journal_identity")
    if not stored_identity:
        raise ValueError("postgres projection metadata is missing source_journal_identity")
    if stored_identity.startswith("local-file:"):
        raise ProjectionStateError(
            ProjectionStateCode.PROJECTION_REBUILD_REQUIRED,
            "postgres projection uses legacy path-based source journal identity; rebuild required",
            details={
                "source_journal_identity": stored_identity,
                "expected_source_journal_identity": expected_identity,
            },
        )
    stored_identity_version = metadata.get("source_journal_identity_version")
    if stored_identity_version is None:
        raise ValueError("postgres projection metadata is missing source_journal_identity_version")
    if stored_identity_version != JOURNAL_SOURCE_IDENTITY_VERSION:
        raise ProjectionStateError(
            ProjectionStateCode.PROJECTION_REBUILD_REQUIRED,
            "postgres projection source journal identity version is unsupported; rebuild required",
            details={
                "source_journal_identity_version": stored_identity_version,
                "expected_source_journal_identity_version": JOURNAL_SOURCE_IDENTITY_VERSION,
            },
        )
    if stored_identity != expected_identity:
        if _postgres_metadata_matches_verified_prefix(
            snapshot,
            records_indexed=records_indexed,
            last_event_hash=last_event_hash,
        ):
            raise ProjectionStateError(
                ProjectionStateCode.PROJECTION_STALE,
                "postgres projection matches a verified prefix of the source journal; "
                "rebuild required",
                details={
                    "records_indexed": records_indexed,
                    "record_count": snapshot.record_count,
                    "last_event_hash": last_event_hash,
                    "terminal_hash": snapshot.terminal_hash,
                },
            )
        raise ProjectionStateError(
            ProjectionStateCode.PROJECTION_MISMATCH,
            "postgres projection source journal identity does not match the verified journal",
            details={
                "source_journal_identity": stored_identity,
                "expected_source_journal_identity": expected_identity,
            },
        )

    stored_journal_sha256 = metadata.get("source_journal_sha256")
    expected_journal_sha256 = snapshot.journal_sha256 or ""
    if stored_journal_sha256 is None:
        raise ValueError("postgres projection metadata is missing source_journal_sha256")
    if stored_journal_sha256 != expected_journal_sha256:
        raise ProjectionStateError(
            ProjectionStateCode.PROJECTION_MISMATCH,
            "postgres projection source journal byte digest does not match the verified journal",
            details={
                "source_journal_sha256": stored_journal_sha256,
                "expected_source_journal_sha256": expected_journal_sha256,
            },
        )

    if records_indexed != snapshot.record_count or last_event_hash != snapshot.terminal_hash:
        code = (
            ProjectionStateCode.PROJECTION_STALE
            if records_indexed <= snapshot.record_count
            else ProjectionStateCode.PROJECTION_MISMATCH
        )
        raise ProjectionStateError(
            code,
            "postgres projection metadata does not match the verified journal",
            details={
                "records_indexed": records_indexed,
                "record_count": snapshot.record_count,
                "last_event_hash": last_event_hash,
                "terminal_hash": snapshot.terminal_hash,
            },
        )
    return records_indexed, last_event_hash


def _fetch_postgres_projected_rows(
    reader: PostgresProjectionReader,
    *,
    table_name: str,
) -> list[Mapping[str, object]]:
    columns = ", ".join(POSTGRES_PROJECTED_EVENT_COLUMNS)
    rows = reader.fetch_all(
        f"""
        SELECT {columns}
        FROM {table_name}
        ORDER BY journal_record_number ASC
        """
    )
    return list(rows)


def _verify_postgres_projected_rows(
    rows: list[Mapping[str, object]],
    snapshot: VerifiedJournalSnapshot,
) -> None:
    if len(rows) != snapshot.record_count:
        code = (
            ProjectionStateCode.PROJECTION_STALE
            if len(rows) < snapshot.record_count
            else ProjectionStateCode.PROJECTION_MISMATCH
        )
        raise ProjectionStateError(
            code,
            "postgres projection row count does not match the verified journal",
            details={"rows": len(rows), "record_count": snapshot.record_count},
        )

    for record_number, event in enumerate(snapshot.events, start=1):
        actual = _postgres_row_comparison_values(rows[record_number - 1])
        expected = _event_projection_parameters(event, journal_record_number=record_number)
        mismatched_columns = [
            column
            for column in POSTGRES_PROJECTED_EVENT_COLUMNS
            if actual.get(column) != expected.get(column)
        ]
        if mismatched_columns:
            raise ProjectionStateError(
                ProjectionStateCode.PROJECTION_MISMATCH,
                "postgres projection row content does not match the verified journal",
                details={
                    "record_number": record_number,
                    "event_id": actual.get("event_id"),
                    "expected_event_id": event.event_id,
                    "mismatched_columns": mismatched_columns,
                },
            )


def _postgres_row_comparison_values(row: Mapping[str, object]) -> dict[str, object]:
    values = {column: row.get(column) for column in POSTGRES_PROJECTED_EVENT_COLUMNS}
    values["occurred_at"] = _canonical_timestamp_text(values["occurred_at"])
    values["observed_at"] = _canonical_timestamp_text(values["observed_at"])
    values["sequence"] = _integer_value(values["sequence"])
    values["journal_record_number"] = _integer_value(values["journal_record_number"])
    values["event_json"] = _canonical_event_json_text(values["event_json"])
    return values


def _canonical_timestamp_text(value: object) -> object:
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.isoformat()
        return value.astimezone(UTC).isoformat().replace("+00:00", "Z")
    if not isinstance(value, str):
        return value
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return value
    if parsed.tzinfo is None:
        return value
    return parsed.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _canonical_event_json_text(value: object) -> object:
    parsed: object
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return value
    elif isinstance(value, Mapping):
        parsed = value
    else:
        return value
    if not isinstance(parsed, Mapping):
        return value
    return deterministic_json_bytes(cast(JsonObject, parsed)).decode("utf-8")


def _integer_value(value: object) -> object:
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    return value


def _postgres_metadata_int(metadata: Mapping[str, str], key: str) -> int:
    value = metadata.get(key)
    if value is None:
        raise ValueError(f"postgres projection metadata is missing {key}")
    try:
        parsed = int(value)
    except ValueError as exc:
        raise ValueError(f"postgres projection metadata {key} is not an integer") from exc
    if parsed < 0:
        raise ValueError(f"postgres projection metadata {key} cannot be negative")
    return parsed


def _postgres_metadata_hash(metadata: Mapping[str, str], key: str) -> str | None:
    value = metadata.get(key)
    if value is None:
        raise ValueError(f"postgres projection metadata is missing {key}")
    return value or None


def _postgres_metadata_matches_verified_prefix(
    snapshot: VerifiedJournalSnapshot,
    *,
    records_indexed: int,
    last_event_hash: str | None,
) -> bool:
    if records_indexed > snapshot.record_count:
        return False
    expected_last_hash = (
        snapshot.events[records_indexed - 1].integrity.event_hash if records_indexed else None
    )
    return last_event_hash == expected_last_hash


def _sha256_text(value: str) -> str:
    return f"sha256:{hashlib.sha256(value.encode('utf-8')).hexdigest()}"


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
