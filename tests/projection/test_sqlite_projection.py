from __future__ import annotations

import hashlib
import json
import os
import sqlite3
from contextlib import closing
from pathlib import Path

import pytest
from typer.testing import CliRunner

import actionlineage.projection.sqlite as sqlite_projection
from actionlineage.cli import app
from actionlineage.domain import (
    CANONICALIZATION_VERSION,
    CorroborationType,
    EventEnvelope,
    EventType,
    EvidenceLink,
    EvidenceRelationship,
    RedactionPolicy,
    VerificationStatus,
)
from actionlineage.domain.redaction import CAPTURE_DIGEST_SCOPE
from actionlineage.journal import LocalJournal
from actionlineage.projection import (
    CASE_BUNDLE_MANIFEST_VERSION,
    ProjectionQueryError,
    ProjectionStateCode,
    ProjectionStateError,
    ProjectionVerificationError,
    explain_event,
    export_case_bundle,
    export_incident,
    export_investigation_graph,
    query_filtered_timeline,
    query_timeline,
    rebuild_projection,
    summarize_incident,
    verify_projection_state,
)
from actionlineage.projection.sqlite import ensure_schema, index_event
from tests.domain.test_events import BASE_TIME, build_event

runner = CliRunner()


def timeline_event(
    index: int,
    event_type: EventType | str,
    *,
    parent_event_id: str | None,
    payload: dict[str, object] | None = None,
) -> EventEnvelope:
    event_id = f"evt_{index}"
    return build_event(
        event_id=event_id,
        event_type=event_type,
        root_event_id="evt_0",
        parent_event_id=parent_event_id,
        sequence=index,
        occurred_at=BASE_TIME,
        observed_at=BASE_TIME,
        payload=payload,
    )


def complete_timeline_events() -> tuple[EventEnvelope, ...]:
    return (
        timeline_event(
            0,
            EventType.AGENT_RUN_STARTED,
            parent_event_id=None,
            payload={"phase": "started"},
        ),
        timeline_event(
            1,
            EventType.AGENT_TOOL_CALL_REQUESTED,
            parent_event_id="evt_0",
            payload={"tool": "synthetic.http_post", "target": "https://example.test/upload"},
        ),
        timeline_event(
            2,
            EventType.POLICY_DECISION,
            parent_event_id="evt_1",
            payload={"decision": "deny", "rule_id": "demo.restricted_external"},
        ),
        timeline_event(
            3,
            EventType.AGENT_TOOL_CALL_DENIED,
            parent_event_id="evt_2",
            payload={"reason": "restricted data to external destination"},
        ),
        timeline_event(
            4,
            EventType.AGENT_RUN_COMPLETED,
            parent_event_id="evt_3",
            payload={"outcome": "completed_with_denial"},
        ),
    )


def write_journal(
    path: Path,
    events: tuple[EventEnvelope, ...],
    *,
    redaction_policy: RedactionPolicy | None = None,
) -> LocalJournal:
    journal = LocalJournal(path, redaction_policy=redaction_policy)
    for event in events:
        journal.append(event)
    return journal


def journal_lines(path: Path) -> list[bytes]:
    return path.read_bytes().splitlines()


def replace_journal_lines(path: Path, lines: list[bytes]) -> None:
    path.write_bytes(b"\n".join(lines) + b"\n")


def sha256_digest(data: bytes) -> str:
    return f"sha256:{hashlib.sha256(data).hexdigest()}"


def capture_markers(value: object) -> list[dict[str, object]]:
    markers: list[dict[str, object]] = []
    if isinstance(value, dict):
        if value.get("marker") == "actionlineage.capture.v1":
            markers.append(value)
        for child in value.values():
            markers.extend(capture_markers(child))
    elif isinstance(value, list):
        for child in value:
            markers.extend(capture_markers(child))
    return markers


def database_fingerprint(path: Path) -> dict[str, object]:
    if not path.exists():
        return {"exists": False}
    stat = path.stat()
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    user_version: int | None = None
    schema_objects: list[tuple[object, ...]] | None = None
    metadata: list[tuple[object, ...]] | None = None
    try:
        with closing(sqlite3.connect(f"{path.resolve().as_uri()}?mode=ro", uri=True)) as connection:
            user_version = connection.execute("PRAGMA user_version").fetchone()[0]
            schema_objects = connection.execute(
                """
                SELECT type, name, sql
                FROM sqlite_master
                ORDER BY type, name
                """
            ).fetchall()
            if any(row[1] == "projection_metadata" for row in schema_objects):
                metadata = connection.execute(
                    "SELECT key, value FROM projection_metadata ORDER BY key"
                ).fetchall()
    except sqlite3.Error:
        schema_objects = None
    return {
        "exists": True,
        "size": stat.st_size,
        "mtime_ns": stat.st_mtime_ns,
        "digest": digest,
        "user_version": user_version,
        "schema_objects": schema_objects,
        "metadata": metadata,
    }


def test_projection_rebuild_is_repeatable_and_rebuilds_after_delete(tmp_path: Path) -> None:
    journal_path = tmp_path / "events.jsonl"
    database_path = tmp_path / "projection.sqlite"
    write_journal(journal_path, complete_timeline_events())

    first = rebuild_projection(journal_path, database_path)
    second = rebuild_projection(journal_path, database_path)
    database_path.unlink()
    rebuilt = rebuild_projection(journal_path, database_path)
    timeline = query_timeline(database_path, journal_path=journal_path, trace_id="trace_01")

    assert first.records_indexed == 5
    assert second.records_indexed == 5
    assert rebuilt.records_indexed == 5
    assert timeline.as_dict()["event_count"] == 5
    assert [event.event_id for event in timeline.events] == [
        "evt_0",
        "evt_1",
        "evt_2",
        "evt_3",
        "evt_4",
    ]


def test_projection_state_verifies_against_journal_snapshot(tmp_path: Path) -> None:
    journal_path = tmp_path / "events.jsonl"
    database_path = tmp_path / "projection.sqlite"
    journal = write_journal(journal_path, complete_timeline_events())
    rebuild_projection(journal_path, database_path)

    projection = verify_projection_state(database_path, journal_path=journal_path)

    assert projection.state == ProjectionStateCode.HEALTHY
    assert projection.record_count == journal.verify().records_verified
    assert projection.terminal_hash == journal.verify().last_event_hash


def test_projection_verification_does_not_create_missing_database(tmp_path: Path) -> None:
    journal_path = tmp_path / "events.jsonl"
    database_path = tmp_path / "missing.sqlite"
    write_journal(journal_path, complete_timeline_events())

    before = database_fingerprint(database_path)
    with pytest.raises(ProjectionStateError) as exc_info:
        verify_projection_state(database_path, journal_path=journal_path)
    after = database_fingerprint(database_path)

    assert exc_info.value.code == ProjectionStateCode.PROJECTION_MISSING
    assert after == before


def test_projection_verification_does_not_mutate_incomplete_schema(tmp_path: Path) -> None:
    journal_path = tmp_path / "events.jsonl"
    database_path = tmp_path / "incomplete.sqlite"
    write_journal(journal_path, complete_timeline_events())
    database_path.write_bytes(b"")

    before = database_fingerprint(database_path)
    with pytest.raises(ProjectionStateError) as exc_info:
        verify_projection_state(database_path, journal_path=journal_path)
    after = database_fingerprint(database_path)

    assert exc_info.value.code in {
        ProjectionStateCode.PROJECTION_REBUILD_REQUIRED,
        ProjectionStateCode.PROJECTION_UNAVAILABLE,
    }
    assert after == before


def test_projection_verification_redacts_schema_exception_detail(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    journal_path = tmp_path / "events.jsonl"
    database_path = tmp_path / "projection.sqlite"
    write_journal(journal_path, complete_timeline_events())
    with closing(sqlite3.connect(database_path)):
        pass
    raw_secret = "projectionsecretvalue123456789"

    def fail_schema_validation(_connection: sqlite3.Connection) -> None:
        raise sqlite_projection.ProjectionSchemaError(
            f"unsupported projection schema for Bearer {raw_secret}"
        )

    monkeypatch.setattr(sqlite_projection, "validate_schema", fail_schema_validation)

    with pytest.raises(ProjectionStateError) as exc_info:
        verify_projection_state(database_path, journal_path=journal_path)

    details = json.dumps(exc_info.value.details, sort_keys=True)
    assert exc_info.value.code == ProjectionStateCode.PROJECTION_REBUILD_REQUIRED
    assert raw_secret not in details
    assert "Bearer [REDACTED:bearer_token]" in details


def test_timeline_query_fails_closed_when_journal_advances_after_rebuild(
    tmp_path: Path,
) -> None:
    journal_path = tmp_path / "events.jsonl"
    database_path = tmp_path / "projection.sqlite"
    journal = write_journal(journal_path, complete_timeline_events())
    rebuild_projection(journal_path, database_path)
    journal.append(
        timeline_event(
            5,
            EventType.AGENT_RUN_COMPLETED,
            parent_event_id="evt_4",
            payload={"outcome": "late_event"},
        )
    )

    with pytest.raises(ProjectionStateError) as exc_info:
        query_timeline(database_path, journal_path=journal_path, trace_id="trace_01")

    assert exc_info.value.code == ProjectionStateCode.PROJECTION_STALE


def test_projection_verification_detects_missing_extra_and_tampered_rows(
    tmp_path: Path,
) -> None:
    journal_path = tmp_path / "events.jsonl"
    database_path = tmp_path / "projection.sqlite"
    write_journal(journal_path, complete_timeline_events())
    rebuild_projection(journal_path, database_path)

    with closing(sqlite3.connect(database_path)) as connection, connection:
        connection.execute("DELETE FROM events WHERE journal_record_number = 5")
    with pytest.raises(ProjectionStateError) as missing:
        query_timeline(database_path, journal_path=journal_path, trace_id="trace_01")
    assert missing.value.code == ProjectionStateCode.PROJECTION_STALE

    rebuild_projection(journal_path, database_path)
    with closing(sqlite3.connect(database_path)) as connection, connection:
        connection.execute(
            """
            INSERT INTO events (
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
            SELECT
                'evt_extra',
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
                999,
                event_json
            FROM events
            WHERE journal_record_number = 1
            """
        )
    with pytest.raises(ProjectionStateError) as extra:
        query_timeline(database_path, journal_path=journal_path, trace_id="trace_01")
    assert extra.value.code == ProjectionStateCode.PROJECTION_MISMATCH

    rebuild_projection(journal_path, database_path)
    with closing(sqlite3.connect(database_path)) as connection, connection:
        connection.execute(
            "UPDATE events SET event_json = replace(event_json, 'started', 'tampered') "
            "WHERE journal_record_number = 1"
        )
    with pytest.raises(ProjectionStateError) as tampered:
        query_timeline(database_path, journal_path=journal_path, trace_id="trace_01")
    assert tampered.value.code == ProjectionStateCode.PROJECTION_MISMATCH


@pytest.mark.parametrize(
    ("column", "tampered_value"),
    [
        ("event_id", "evt_tampered"),
        ("spec_version", "actionlineage.dev/tampered"),
        ("event_type", "tampered.event"),
        ("occurred_at", "1900-01-01T00:00:00Z"),
        ("observed_at", "1900-01-01T00:00:00Z"),
        ("trace_id", "other-trace"),
        ("run_id", "other-run"),
        ("span_id", "other-span"),
        ("session_id", "other-session"),
        ("root_event_id", "evt_other_root"),
        ("parent_event_id", "evt_other_parent"),
        ("sequence", 999999),
        ("event_hash", "sha256:tampered"),
        ("previous_event_hash", "sha256:tampered_previous"),
        ("verification_status", "verified"),
        ("evidence_subject_event_id", "evt_subject_tampered"),
        ("evidence_event_id", "evt_evidence_tampered"),
        ("journal_record_number", 999999),
        ("event_json", '{"tampered":true}'),
    ],
)
def test_projection_verification_detects_single_projected_column_tamper(
    tmp_path: Path,
    column: str,
    tampered_value: object,
) -> None:
    journal_path = tmp_path / "events.jsonl"
    database_path = tmp_path / "projection.sqlite"
    write_journal(journal_path, complete_timeline_events())
    rebuild_projection(journal_path, database_path)

    with closing(sqlite3.connect(database_path)) as connection, connection:
        connection.execute(
            f"UPDATE events SET {column} = ? WHERE journal_record_number = 1",
            (tampered_value,),
        )

    with pytest.raises(ProjectionStateError) as exc_info:
        query_timeline(database_path, journal_path=journal_path, trace_id="trace_01")

    assert exc_info.value.code in {
        ProjectionStateCode.PROJECTION_MISMATCH,
        ProjectionStateCode.PROJECTION_STALE,
    }


def test_projection_verification_detects_unexpected_sqlite_runtime_types(
    tmp_path: Path,
) -> None:
    journal_path = tmp_path / "events.jsonl"
    database_path = tmp_path / "projection.sqlite"
    write_journal(journal_path, complete_timeline_events())
    rebuild_projection(journal_path, database_path)

    with closing(sqlite3.connect(database_path)) as connection, connection:
        connection.execute(
            "UPDATE events SET event_hash = ? WHERE journal_record_number = 1",
            (sqlite3.Binary(b"not-text"),),
        )

    with pytest.raises(ProjectionStateError) as exc_info:
        query_timeline(database_path, journal_path=journal_path, trace_id="trace_01")

    assert exc_info.value.code == ProjectionStateCode.PROJECTION_MISMATCH
    assert exc_info.value.details["type_mismatched_columns"] == ["event_hash"]


def test_projection_source_identity_allows_byte_identical_moved_journal(tmp_path: Path) -> None:
    journal_path = tmp_path / "events.jsonl"
    other_journal_path = tmp_path / "other.jsonl"
    database_path = tmp_path / "projection.sqlite"
    write_journal(journal_path, complete_timeline_events())
    write_journal(other_journal_path, complete_timeline_events())
    rebuild_projection(journal_path, database_path)

    timeline = query_timeline(database_path, journal_path=other_journal_path, trace_id="trace_01")

    assert timeline.as_dict()["event_count"] == 5
    assert timeline.verification is not None
    assert timeline.verification.journal_path == other_journal_path.resolve(strict=False)
    assert timeline.verification.source_journal_identity == (
        timeline.verification.journal_snapshot.source_identity
    )


def test_projection_source_identity_mismatch_fails_closed(tmp_path: Path) -> None:
    journal_path = tmp_path / "events.jsonl"
    other_journal_path = tmp_path / "other.jsonl"
    database_path = tmp_path / "projection.sqlite"
    write_journal(journal_path, complete_timeline_events())
    other_events = list(complete_timeline_events())
    other_events[3] = timeline_event(
        3,
        EventType.AGENT_TOOL_CALL_DENIED,
        parent_event_id="evt_2",
        payload={"reason": "different source content"},
    )
    write_journal(other_journal_path, tuple(other_events))
    rebuild_projection(journal_path, database_path)

    with pytest.raises(ProjectionStateError) as exc_info:
        query_timeline(database_path, journal_path=other_journal_path, trace_id="trace_01")

    assert exc_info.value.code == ProjectionStateCode.PROJECTION_MISMATCH


def test_projection_missing_source_identity_requires_rebuild(tmp_path: Path) -> None:
    journal_path = tmp_path / "events.jsonl"
    database_path = tmp_path / "projection.sqlite"
    write_journal(journal_path, complete_timeline_events())
    rebuild_projection(journal_path, database_path)

    with closing(sqlite3.connect(database_path)) as connection, connection:
        connection.execute("DELETE FROM projection_metadata WHERE key = 'source_journal_identity'")

    with pytest.raises(ProjectionStateError) as exc_info:
        query_timeline(database_path, journal_path=journal_path, trace_id="trace_01")

    assert exc_info.value.code == ProjectionStateCode.PROJECTION_REBUILD_REQUIRED


def test_projection_legacy_path_source_identity_requires_rebuild(tmp_path: Path) -> None:
    journal_path = tmp_path / "events.jsonl"
    database_path = tmp_path / "projection.sqlite"
    write_journal(journal_path, complete_timeline_events())
    rebuild_projection(journal_path, database_path)

    with closing(sqlite3.connect(database_path)) as connection, connection:
        connection.execute(
            """
            UPDATE projection_metadata
            SET value = 'local-file:/tmp/actionlineage-other-journal.jsonl'
            WHERE key = 'source_journal_identity'
            """
        )

    with pytest.raises(ProjectionStateError) as exc_info:
        query_timeline(database_path, journal_path=journal_path, trace_id="trace_01")

    assert exc_info.value.code == ProjectionStateCode.PROJECTION_REBUILD_REQUIRED


def test_projection_mismatched_source_journal_sha256_fails_closed(tmp_path: Path) -> None:
    journal_path = tmp_path / "events.jsonl"
    database_path = tmp_path / "projection.sqlite"
    write_journal(journal_path, complete_timeline_events())
    rebuild_projection(journal_path, database_path)

    with closing(sqlite3.connect(database_path)) as connection, connection:
        connection.execute(
            """
            UPDATE projection_metadata
            SET value = 'sha256:tampered'
            WHERE key = 'source_journal_sha256'
            """
        )

    with pytest.raises(ProjectionStateError) as exc_info:
        query_timeline(database_path, journal_path=journal_path, trace_id="trace_01")

    assert exc_info.value.code == ProjectionStateCode.PROJECTION_MISMATCH


def test_projection_moved_journal_path_keeps_stored_path_as_audit_hint(tmp_path: Path) -> None:
    journal_path = tmp_path / "events.jsonl"
    moved_journal_path = tmp_path / "moved-events.jsonl"
    database_path = tmp_path / "projection.sqlite"
    write_journal(journal_path, complete_timeline_events())
    rebuild_projection(journal_path, database_path)
    journal_path.rename(moved_journal_path)

    timeline = query_timeline(database_path, journal_path=moved_journal_path, trace_id="trace_01")

    assert timeline.verification is not None
    assert timeline.verification.journal_path == moved_journal_path.resolve(strict=False)
    assert timeline.verification.source_journal_path == str(journal_path.resolve(strict=False))
    assert timeline.as_dict()["verification"]["journal_path"] == str(
        moved_journal_path.resolve(strict=False)
    )


def test_projection_journal_path_aliases_are_normalized(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    journal_path = tmp_path / "events.jsonl"
    database_path = tmp_path / "projection.sqlite"
    write_journal(journal_path, complete_timeline_events())
    monkeypatch.chdir(tmp_path)

    rebuild_projection(Path("events.jsonl"), Path("projection.sqlite"))
    timeline = query_timeline(database_path, journal_path=journal_path, trace_id="trace_01")

    assert timeline.as_dict()["event_count"] == 5


def test_projection_journal_symlink_alias_is_normalized(tmp_path: Path) -> None:
    journal_path = tmp_path / "events.jsonl"
    journal_alias = tmp_path / "journal-alias.jsonl"
    database_path = tmp_path / "projection.sqlite"
    write_journal(journal_path, complete_timeline_events())
    journal_alias.symlink_to(journal_path)

    rebuild_projection(journal_alias, database_path)
    timeline = query_timeline(database_path, journal_path=journal_path, trace_id="trace_01")

    assert timeline.as_dict()["event_count"] == 5


def test_incident_export_is_blocked_when_projection_is_stale(tmp_path: Path) -> None:
    journal_path = tmp_path / "events.jsonl"
    database_path = tmp_path / "projection.sqlite"
    journal = write_journal(journal_path, complete_timeline_events())
    rebuild_projection(journal_path, database_path)
    journal.append(
        timeline_event(
            5,
            EventType.AGENT_RUN_COMPLETED,
            parent_event_id="evt_4",
            payload={"outcome": "late_event"},
        )
    )

    with pytest.raises(ProjectionStateError) as exc_info:
        export_incident(database_path, journal_path=journal_path, trace_id="trace_01")

    assert exc_info.value.code == ProjectionStateCode.PROJECTION_STALE


def test_timeline_selector_values_are_bound_as_data(tmp_path: Path) -> None:
    journal_path = tmp_path / "events.jsonl"
    database_path = tmp_path / "projection.sqlite"
    write_journal(journal_path, complete_timeline_events())
    rebuild_projection(journal_path, database_path)

    injection_shaped = query_timeline(
        database_path, journal_path=journal_path, trace_id="trace_01' OR 1=1 --"
    )
    normal = query_timeline(database_path, journal_path=journal_path, trace_id="trace_01")

    assert injection_shaped.events == ()
    assert normal.as_dict()["event_count"] == 5


def test_verified_projection_reader_uses_one_sqlite_snapshot(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    journal_path = tmp_path / "events.jsonl"
    database_path = tmp_path / "projection.sqlite"
    write_journal(journal_path, complete_timeline_events())
    rebuild_projection(journal_path, database_path)
    with closing(sqlite3.connect(database_path)) as connection:
        connection.execute("PRAGMA journal_mode = WAL")

    original_verify = sqlite_projection._verify_projection_state_on_connection
    tampered = False

    def tamper_after_verification(
        connection: sqlite3.Connection,
        *,
        database_path: Path,
        journal_path: Path,
    ) -> sqlite_projection.VerifiedProjectionSnapshot:
        nonlocal tampered
        verification = original_verify(
            connection,
            database_path=database_path,
            journal_path=journal_path,
        )
        with closing(sqlite3.connect(database_path)) as writer, writer:
            writer.execute("UPDATE events SET trace_id = 'other-trace' WHERE event_id = 'evt_0'")
            tampered = True
        return verification

    monkeypatch.setattr(
        sqlite_projection,
        "_verify_projection_state_on_connection",
        tamper_after_verification,
    )

    timeline = query_timeline(database_path, journal_path=journal_path, trace_id="trace_01")

    assert tampered is True
    assert timeline.as_dict()["event_count"] == 5
    with closing(sqlite3.connect(database_path)) as connection:
        changed_trace_id = connection.execute(
            "SELECT trace_id FROM events WHERE event_id = 'evt_0'"
        ).fetchone()[0]
    assert changed_trace_id == "other-trace"


def test_event_indexing_is_idempotent_for_the_same_projected_event(tmp_path: Path) -> None:
    journal_path = tmp_path / "events.jsonl"
    database_path = tmp_path / "projection.sqlite"
    journal = LocalJournal(journal_path)
    persisted_event = journal.append(
        timeline_event(0, EventType.AGENT_RUN_STARTED, parent_event_id=None)
    )

    with closing(sqlite3.connect(database_path)) as connection, connection:
        ensure_schema(connection)
        first = index_event(connection, persisted_event, journal_record_number=1)
        second = index_event(connection, persisted_event, journal_record_number=1)

    assert first is True
    assert second is False


def test_projection_schema_v1_migrates_to_verification_indexes(tmp_path: Path) -> None:
    database_path = tmp_path / "projection.sqlite"

    with closing(sqlite3.connect(database_path)) as connection, connection:
        connection.executescript(
            """
            CREATE TABLE projection_metadata (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );
            CREATE TABLE events (
                event_id TEXT PRIMARY KEY,
                spec_version TEXT NOT NULL,
                event_type TEXT NOT NULL,
                occurred_at TEXT NOT NULL,
                observed_at TEXT NOT NULL,
                trace_id TEXT NOT NULL,
                run_id TEXT NOT NULL,
                span_id TEXT,
                session_id TEXT,
                root_event_id TEXT NOT NULL,
                parent_event_id TEXT,
                sequence INTEGER NOT NULL,
                event_hash TEXT NOT NULL,
                previous_event_hash TEXT,
                journal_record_number INTEGER NOT NULL UNIQUE,
                event_json TEXT NOT NULL
            );
            PRAGMA user_version = 1;
            """
        )
        ensure_schema(connection)
        columns = {row[1] for row in connection.execute("PRAGMA table_info(events)").fetchall()}
        user_version = connection.execute("PRAGMA user_version").fetchone()

    assert {"verification_status", "evidence_subject_event_id", "evidence_event_id"} <= columns
    assert user_version == (2,)


def test_corrupt_journal_is_rejected_without_replacing_existing_projection(tmp_path: Path) -> None:
    journal_path = tmp_path / "events.jsonl"
    database_path = tmp_path / "projection.sqlite"
    write_journal(journal_path, complete_timeline_events())
    rebuild_projection(journal_path, database_path)

    lines = journal_lines(journal_path)
    lines[2] = lines[2].replace(b"demo.restricted_external", b"demo.changed_rule")
    replace_journal_lines(journal_path, lines)

    with pytest.raises(ProjectionVerificationError) as exc_info:
        rebuild_projection(journal_path, database_path)

    assert exc_info.value.verification.ok is False
    with pytest.raises(ProjectionStateError) as query_error:
        query_timeline(database_path, journal_path=journal_path, run_id="run_01")
    assert query_error.value.code == ProjectionStateCode.JOURNAL_INVALID


def test_unknown_event_type_is_preserved_in_projected_timeline(tmp_path: Path) -> None:
    journal_path = tmp_path / "events.jsonl"
    database_path = tmp_path / "projection.sqlite"
    unknown_event_type = "vendor.future.observed"
    write_journal(
        journal_path,
        (
            timeline_event(0, EventType.AGENT_RUN_STARTED, parent_event_id=None),
            timeline_event(
                1,
                unknown_event_type,
                parent_event_id="evt_0",
                payload={"meaning": "preserve only"},
            ),
        ),
    )

    rebuild_projection(journal_path, database_path)
    timeline = query_timeline(database_path, journal_path=journal_path, trace_id="trace_01")
    incident = export_incident(database_path, journal_path=journal_path, trace_id="trace_01")

    assert timeline.events[1].event_type == unknown_event_type
    assert timeline.events[1].event["event_type"] == unknown_event_type
    assert incident.as_dict()["events"][1]["event_type"] == unknown_event_type


def test_projection_result_as_dict_returns_defensive_json_copies(tmp_path: Path) -> None:
    journal_path = tmp_path / "events.jsonl"
    database_path = tmp_path / "projection.sqlite"
    write_journal(journal_path, complete_timeline_events())
    rebuild_projection(journal_path, database_path)

    timeline = query_timeline(database_path, journal_path=journal_path, trace_id="trace_01")
    exported = timeline.as_dict()
    events = exported["events"]
    assert isinstance(events, list)
    first_event = events[0]
    assert isinstance(first_event, dict)
    event_object = first_event["event"]
    assert isinstance(event_object, dict)
    payload = event_object["payload"]
    assert isinstance(payload, dict)
    payload["phase"] = "tampered"

    fresh = timeline.as_dict()
    fresh_events = fresh["events"]
    assert isinstance(fresh_events, list)
    fresh_first_event = fresh_events[0]
    assert isinstance(fresh_first_event, dict)
    fresh_event_object = fresh_first_event["event"]
    assert isinstance(fresh_event_object, dict)
    fresh_payload = fresh_event_object["payload"]
    assert isinstance(fresh_payload, dict)
    assert fresh_payload["phase"] == "started"


def test_projection_indexes_verification_status_and_evidence_links(tmp_path: Path) -> None:
    journal_path = tmp_path / "events.jsonl"
    database_path = tmp_path / "projection.sqlite"
    link = EvidenceLink(
        subject_event_id="evt_1",
        relationship=EvidenceRelationship.CORROBORATES,
        evidence_event_id="evt_2",
        corroboration_type=CorroborationType.INDEPENDENT_OBSERVER,
        observer_identity="local_receiver_fixture",
        confidence=0.95,
        verification_status=VerificationStatus.VERIFIED,
        limitations=("local deterministic fixture only",),
    )
    write_journal(
        journal_path,
        (
            timeline_event(
                0,
                EventType.AGENT_INTENT_RECORDED,
                parent_event_id=None,
                payload={"intent": "verify local receiver observation"},
            ),
            timeline_event(
                1,
                EventType.TOOL_EXECUTION_ACKNOWLEDGED,
                parent_event_id="evt_0",
                payload={"tool_identity": {"name": "safe_http.send"}},
            ),
            timeline_event(
                2,
                EventType.SIDE_EFFECT_OBSERVED,
                parent_event_id="evt_1",
                payload={"observer_identity": "local_receiver_fixture"},
            ),
            timeline_event(
                3,
                EventType.SIDE_EFFECT_VERIFIED,
                parent_event_id="evt_2",
                payload={"evidence_link": link.as_payload()},
            ),
        ),
    )

    rebuild_projection(journal_path, database_path)
    timeline = query_timeline(database_path, journal_path=journal_path, trace_id="trace_01")
    verified_event = timeline.events[3]

    assert verified_event.verification_status == "verified"
    assert verified_event.evidence_subject_event_id == "evt_1"
    assert verified_event.evidence_event_id == "evt_2"
    assert verified_event.as_dict()["verification_status"] == "verified"


def test_filtered_timeline_supports_investigation_fields(tmp_path: Path) -> None:
    journal_path = tmp_path / "events.jsonl"
    database_path = tmp_path / "projection.sqlite"
    write_journal(
        journal_path,
        (
            timeline_event(0, EventType.AGENT_INTENT_RECORDED, parent_event_id=None),
            timeline_event(
                1,
                EventType.TOOL_EXECUTION_ACKNOWLEDGED,
                parent_event_id="evt_0",
                payload={
                    "tool_identity": {
                        "name": "safe_http.send",
                        "descriptor_hash": "sha256:demo",
                    },
                    "resource": {"uri": "http://127.0.0.1/receiver"},
                },
            ),
        ),
    )
    rebuild_projection(journal_path, database_path)

    by_tool = query_filtered_timeline(
        database_path, journal_path=journal_path, tool_name="safe_http.send"
    )
    by_descriptor = query_filtered_timeline(
        database_path, journal_path=journal_path, descriptor_hash="sha256:demo"
    )
    by_resource = query_filtered_timeline(
        database_path, journal_path=journal_path, resource="http://127.0.0.1/receiver"
    )

    assert [event.event_id for event in by_tool.events] == ["evt_1"]
    assert [event.event_id for event in by_descriptor.events] == ["evt_1"]
    assert [event.event_id for event in by_resource.events] == ["evt_1"]


def test_projection_api_closes_sqlite_connections(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    journal_path = tmp_path / "events.jsonl"
    database_path = tmp_path / "projection.sqlite"
    case_dir = tmp_path / "case"
    write_journal(journal_path, complete_timeline_events())
    real_connect = sqlite3.connect
    connections: list[sqlite3.Connection] = []
    closed_connection_ids: set[int] = set()

    class TrackingConnection(sqlite3.Connection):
        def close(self) -> None:
            closed_connection_ids.add(id(self))
            super().close()

    def tracking_connect(*args: object, **kwargs: object) -> sqlite3.Connection:
        assert "factory" not in kwargs
        connection = real_connect(*args, factory=TrackingConnection, **kwargs)
        connections.append(connection)
        return connection

    monkeypatch.setattr(sqlite3, "connect", tracking_connect)

    rebuild_projection(journal_path, database_path)
    query_timeline(database_path, journal_path=journal_path, trace_id="trace_01")
    query_filtered_timeline(database_path, journal_path=journal_path, event_type="policy.decision")
    export_incident(database_path, journal_path=journal_path, run_id="run_01")
    summarize_incident(database_path, journal_path=journal_path, trace_id="trace_01")
    export_investigation_graph(database_path, journal_path=journal_path, trace_id="trace_01")
    explain_event(database_path, journal_path=journal_path, event_id="evt_2")
    export_case_bundle(
        database_path,
        case_dir,
        journal_path=journal_path,
        trace_id="trace_01",
    )

    assert connections
    assert {id(connection) for connection in connections} == closed_connection_ids


def test_incident_export_includes_investigation_summary(tmp_path: Path) -> None:
    journal_path = tmp_path / "events.jsonl"
    database_path = tmp_path / "projection.sqlite"
    link = EvidenceLink(
        subject_event_id="evt_1",
        relationship=EvidenceRelationship.CORROBORATES,
        evidence_event_id="evt_2",
        corroboration_type=CorroborationType.INDEPENDENT_OBSERVER,
        observer_identity="local_receiver_fixture",
        confidence=0.95,
        verification_status=VerificationStatus.VERIFIED,
        limitations=("local deterministic fixture only",),
    )
    write_journal(
        journal_path,
        (
            timeline_event(0, EventType.AGENT_INTENT_RECORDED, parent_event_id=None),
            timeline_event(
                1,
                EventType.TOOL_EXECUTION_ACKNOWLEDGED,
                parent_event_id="evt_0",
                payload={
                    "tool_identity": {
                        "name": "safe_http.send",
                        "descriptor_hash": "sha256:demo",
                    }
                },
            ),
            timeline_event(
                2,
                EventType.SIDE_EFFECT_OBSERVED,
                parent_event_id="evt_1",
                payload={
                    "resource": {"uri": "http://127.0.0.1/receiver"},
                    "verification_status": "observed",
                },
            ),
            timeline_event(
                3,
                EventType.SIDE_EFFECT_VERIFIED,
                parent_event_id="evt_2",
                payload={"evidence_link": link.as_payload()},
            ),
        ),
    )
    rebuild_projection(journal_path, database_path)

    incident = export_incident(
        database_path, journal_path=journal_path, trace_id="trace_01"
    ).as_dict()
    summary = incident["summary"]

    assert summary["principals"] == ["agent_demo"]
    assert "safe_http.send" in summary["tools"]
    assert "http://127.0.0.1/receiver" in summary["resources"]
    assert summary["verification_statuses"] == {"observed": 1, "verified": 1}
    assert summary["evidence_links"][0]["subject_event_id"] == "evt_1"
    assert "No observation recorded is not proof" in summary["claims_language"]


def test_incident_summary_preserves_scoped_capture_notes_for_bounded_values(
    tmp_path: Path,
) -> None:
    journal_path = tmp_path / "events.jsonl"
    database_path = tmp_path / "projection.sqlite"
    long_tool = "safe_http." + ("tool" * 32)
    long_resource = "demo://workspace/" + ("resource" * 32)
    long_limitation = "fixture limitation " + ("detail" * 32)
    link = EvidenceLink(
        subject_event_id="evt_1",
        relationship=EvidenceRelationship.CORROBORATES,
        evidence_event_id="evt_2",
        corroboration_type=CorroborationType.INDEPENDENT_OBSERVER,
        observer_identity="local_receiver_fixture",
        confidence=0.95,
        verification_status=VerificationStatus.VERIFIED,
        limitations=(long_limitation,),
    )
    write_journal(
        journal_path,
        (
            timeline_event(0, EventType.AGENT_INTENT_RECORDED, parent_event_id=None),
            timeline_event(
                1,
                EventType.TOOL_EXECUTION_ACKNOWLEDGED,
                parent_event_id="evt_0",
                payload={
                    "tool_identity": {"name": long_tool},
                    "resource": {"uri": long_resource},
                },
            ),
            timeline_event(2, EventType.SIDE_EFFECT_OBSERVED, parent_event_id="evt_1"),
            timeline_event(
                3,
                EventType.SIDE_EFFECT_VERIFIED,
                parent_event_id="evt_2",
                payload={"evidence_link": link.as_payload()},
            ),
        ),
        redaction_policy=RedactionPolicy(max_string_length=18),
    )
    rebuild_projection(journal_path, database_path)

    incident = export_incident(
        database_path, journal_path=journal_path, trace_id="trace_01"
    ).as_dict()
    summary = incident["summary"]
    summary_json = json.dumps(summary, sort_keys=True)

    for field in ("tools", "resources", "limitations"):
        values = summary[field]
        assert isinstance(values, list)
        assert len(values) == 1
        assert values[0].startswith("[TRUNCATED ")
        assert f"digest_scope={CAPTURE_DIGEST_SCOPE}" in values[0]

    assert long_tool not in summary_json
    assert long_resource not in summary_json
    assert long_limitation not in summary_json


def test_grounded_summary_is_derived_from_incident_evidence(tmp_path: Path) -> None:
    journal_path = tmp_path / "events.jsonl"
    database_path = tmp_path / "projection.sqlite"
    write_journal(journal_path, complete_timeline_events())
    rebuild_projection(journal_path, database_path)

    summary = summarize_incident(
        database_path, journal_path=journal_path, trace_id="trace_01"
    ).as_dict()

    assert summary["summary_version"] == "actionlineage.dev/grounded-summary-v0"
    assert summary["model_provider"] is None
    assert "5 events for trace_id=trace_01" in str(summary["headline"])
    assert summary["grounded_event_ids"] == ["evt_0", "evt_1", "evt_2", "evt_3", "evt_4"]
    assert any("No observation recorded is not proof" in item for item in summary["limitations"])
    assert "append-only local journal" in str(summary["canonical_source"])


def test_investigation_graph_export_links_events_and_evidence(tmp_path: Path) -> None:
    journal_path = tmp_path / "events.jsonl"
    database_path = tmp_path / "projection.sqlite"
    link = EvidenceLink(
        subject_event_id="evt_1",
        relationship=EvidenceRelationship.CORROBORATES,
        evidence_event_id="evt_2",
        corroboration_type=CorroborationType.INDEPENDENT_OBSERVER,
        observer_identity="local_receiver_fixture",
        confidence=0.95,
        verification_status=VerificationStatus.VERIFIED,
        limitations=("local deterministic fixture only",),
    )
    write_journal(
        journal_path,
        (
            timeline_event(0, EventType.AGENT_INTENT_RECORDED, parent_event_id=None),
            timeline_event(
                1,
                EventType.TOOL_EXECUTION_ACKNOWLEDGED,
                parent_event_id="evt_0",
                payload={
                    "tool_identity": {"name": "safe_http.send"},
                    "resource": {"uri": "http://127.0.0.1/receiver"},
                },
            ),
            timeline_event(2, EventType.SIDE_EFFECT_OBSERVED, parent_event_id="evt_1"),
            timeline_event(
                3,
                EventType.SIDE_EFFECT_VERIFIED,
                parent_event_id="evt_2",
                payload={"evidence_link": link.as_payload()},
            ),
        ),
    )
    rebuild_projection(journal_path, database_path)

    graph = export_investigation_graph(
        database_path, journal_path=journal_path, trace_id="trace_01"
    ).as_dict()
    nodes = {node["id"]: node for node in graph["nodes"]}
    edges = {
        (edge["source"], edge["target"], edge["relationship"]): edge for edge in graph["edges"]
    }

    assert graph["graph_version"] == "actionlineage.dev/investigation-graph-v0"
    assert nodes["event:evt_1"]["kind"] == "event"
    assert nodes["tool:safe_http.send"]["kind"] == "tool"
    assert nodes["resource:http://127.0.0.1/receiver"]["kind"] == "resource"
    assert nodes["verification_status:verified"]["kind"] == "verification_status"
    assert ("event:evt_0", "event:evt_1", "causal_parent") in edges
    evidence_edge = edges[("event:evt_2", "event:evt_1", "evidence_link:corroborates")]
    assert evidence_edge["attributes"]["observer_identity"] == "local_receiver_fixture"
    assert evidence_edge["attributes"]["verification_status"] == "verified"
    assert any("No observation recorded is not proof" in item for item in graph["limitations"])


def test_event_explanation_links_causality_and_evidence(tmp_path: Path) -> None:
    journal_path = tmp_path / "events.jsonl"
    database_path = tmp_path / "projection.sqlite"
    link = EvidenceLink(
        subject_event_id="evt_1",
        relationship=EvidenceRelationship.CORROBORATES,
        evidence_event_id="evt_2",
        corroboration_type=CorroborationType.INDEPENDENT_OBSERVER,
        observer_identity="local_receiver_fixture",
        confidence=0.95,
        verification_status=VerificationStatus.VERIFIED,
        limitations=("local deterministic fixture only",),
    )
    write_journal(
        journal_path,
        (
            timeline_event(0, EventType.AGENT_INTENT_RECORDED, parent_event_id=None),
            timeline_event(1, EventType.TOOL_EXECUTION_ACKNOWLEDGED, parent_event_id="evt_0"),
            timeline_event(2, EventType.SIDE_EFFECT_OBSERVED, parent_event_id="evt_1"),
            timeline_event(
                3,
                EventType.SIDE_EFFECT_VERIFIED,
                parent_event_id="evt_2",
                payload={"evidence_link": link.as_payload()},
            ),
        ),
    )
    rebuild_projection(journal_path, database_path)

    explanation = explain_event(
        database_path, journal_path=journal_path, event_id="evt_1"
    ).as_dict()

    assert explanation["parent_event_id"] == "evt_0"
    assert explanation["child_event_ids"] == ["evt_2"]
    assert explanation["evidence_links_as_subject"][0]["evidence_event_id"] == "evt_2"


def test_projection_cli_error_redacts_missing_event_id_canary(tmp_path: Path) -> None:
    journal_path = tmp_path / "events.jsonl"
    database_path = tmp_path / "projection.sqlite"
    raw_secret = "projectionclierrorsecretvalue123456789"
    missing_event_id = f"evt_missing Bearer {raw_secret}"
    write_journal(journal_path, complete_timeline_events())
    rebuild_projection(journal_path, database_path)

    result = runner.invoke(
        app,
        [
            "projection",
            "explain-event",
            str(database_path),
            missing_event_id,
            "--journal-path",
            str(journal_path),
        ],
    )

    assert result.exit_code == 1
    data = json.loads(result.stdout)
    assert data["ok"] is False
    assert "event does not exist in projection" in data["error"]
    assert raw_secret not in result.stdout
    assert "Bearer [REDACTED:bearer_token]" in result.stdout


def test_case_bundle_export_writes_redacted_reports_without_absence_overclaim(
    tmp_path: Path,
) -> None:
    journal_path = tmp_path / "events.jsonl"
    database_path = tmp_path / "projection.sqlite"
    bundle_dir = tmp_path / "case"
    write_journal(journal_path, complete_timeline_events())
    rebuild_projection(journal_path, database_path)

    result = export_case_bundle(
        database_path,
        bundle_dir,
        journal_path=journal_path,
        trace_id="trace_01",
    )
    markdown = result.markdown_path.read_text(encoding="utf-8")
    case_data = json.loads(result.json_path.read_text(encoding="utf-8"))
    ndjson_lines = result.ndjson_path.read_text(encoding="utf-8").splitlines()
    manifest = json.loads(result.manifest_path.read_text(encoding="utf-8"))
    files = {entry["path"]: entry for entry in manifest["files"]}

    assert result.as_dict()["ok"] is True
    assert result.as_dict()["manifest_path"] == str(result.manifest_path)
    assert case_data["event_count"] == 5
    assert len(ndjson_lines) == 5
    assert "No observation recorded is not proof" in markdown
    assert "did not happen" not in markdown
    assert manifest["manifest_version"] == CASE_BUNDLE_MANIFEST_VERSION
    assert manifest["bundle_version"] == "actionlineage.dev/case-bundle-v0"
    assert manifest["incident_export_version"] == "actionlineage.dev/incident-export-v0"
    assert manifest["canonicalization"] == CANONICALIZATION_VERSION
    assert manifest["selector"] == {"type": "trace_id", "value": "trace_01"}
    assert manifest["query"] == {"trace_id": "trace_01", "run_id": None}
    assert (
        manifest["journal"]["source_identity"]
        == case_data["verification"]["source_journal_identity"]
    )
    assert manifest["journal"]["record_count"] == 5
    assert manifest["journal"]["terminal_hash"] == case_data["verification"]["terminal_hash"]
    assert (
        manifest["journal"]["journal_sha256"]
        == case_data["verification"]["journal"]["journal_sha256"]
    )
    assert (
        manifest["projection"]["projection_identity"]
        == case_data["verification"]["projection_identity"]
    )
    assert manifest["projection"]["schema_version"] == 2
    assert manifest["external_signature"] is None
    assert manifest["external_checkpoint"] is None

    for exported_path in (result.json_path, result.ndjson_path, result.markdown_path):
        data = exported_path.read_bytes()
        entry = files[exported_path.name]
        assert entry["size_bytes"] == len(data)
        assert entry["sha256"] == sha256_digest(data)


def test_case_bundle_machine_artifacts_preserve_capture_digest_scope(
    tmp_path: Path,
) -> None:
    journal_path = tmp_path / "events.jsonl"
    database_path = tmp_path / "projection.sqlite"
    bundle_dir = tmp_path / "case"
    oversized_value = "case-bundle-sensitive-content-" * 4
    journal = LocalJournal(
        journal_path,
        redaction_policy=RedactionPolicy(max_string_length=12),
    )
    journal.append(
        timeline_event(
            0,
            EventType.AGENT_RUN_STARTED,
            parent_event_id=None,
            payload={"body": oversized_value},
        )
    )
    rebuild_projection(journal_path, database_path)

    result = export_case_bundle(
        database_path,
        bundle_dir,
        journal_path=journal_path,
        trace_id="trace_01",
    )
    case_text = result.json_path.read_text(encoding="utf-8")
    ndjson_text = result.ndjson_path.read_text(encoding="utf-8")
    report = result.markdown_path.read_text(encoding="utf-8")
    case_data = json.loads(case_text)
    ndjson_events = [json.loads(line) for line in ndjson_text.splitlines()]

    assert oversized_value not in case_text
    assert oversized_value not in ndjson_text
    assert oversized_value not in report

    case_markers = capture_markers(case_data)
    ndjson_markers = capture_markers(ndjson_events)
    assert case_markers
    assert ndjson_markers
    for marker in (*case_markers, *ndjson_markers):
        assert marker["digest"].startswith("sha256:")
        assert marker["digest_scope"] == CAPTURE_DIGEST_SCOPE
    assert CAPTURE_DIGEST_SCOPE not in report


def test_case_bundle_export_refuses_existing_artifacts(tmp_path: Path) -> None:
    journal_path = tmp_path / "events.jsonl"
    database_path = tmp_path / "projection.sqlite"
    bundle_dir = tmp_path / "case"
    write_journal(journal_path, complete_timeline_events())
    rebuild_projection(journal_path, database_path)
    existing = bundle_dir / "case.json"
    bundle_dir.mkdir()
    existing.write_text("existing\n", encoding="utf-8")

    with pytest.raises(ProjectionQueryError, match="case bundle output already exists"):
        export_case_bundle(
            database_path,
            bundle_dir,
            journal_path=journal_path,
            trace_id="trace_01",
        )

    assert existing.read_text(encoding="utf-8") == "existing\n"


def test_case_bundle_export_uses_private_permissions_under_permissive_umask(
    tmp_path: Path,
) -> None:
    if os.name != "posix":
        pytest.skip("POSIX mode-bit assertions do not apply on this platform")
    journal_path = tmp_path / "events.jsonl"
    database_path = tmp_path / "projection.sqlite"
    bundle_dir = tmp_path / "case"
    write_journal(journal_path, complete_timeline_events())
    rebuild_projection(journal_path, database_path)
    original_umask = os.umask(0)
    try:
        result = export_case_bundle(
            database_path,
            bundle_dir,
            journal_path=journal_path,
            trace_id="trace_01",
        )
    finally:
        os.umask(original_umask)

    assert result.output_dir.stat().st_mode & 0o777 == 0o700
    for path in (result.json_path, result.ndjson_path, result.markdown_path, result.manifest_path):
        assert path.stat().st_mode & 0o777 == 0o600


@pytest.mark.parametrize("failure_point", ("write", "staging_sync", "publish"))
def test_case_bundle_export_cleans_staging_after_publication_failure(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    failure_point: str,
) -> None:
    journal_path = tmp_path / "events.jsonl"
    database_path = tmp_path / "projection.sqlite"
    bundle_dir = tmp_path / "case"
    write_journal(journal_path, complete_timeline_events())
    rebuild_projection(journal_path, database_path)

    if failure_point == "write":
        original_write = sqlite_projection._write_private_case_bundle_file

        def fail_write(path: Path, data: bytes) -> None:
            if path.name == "events.ndjson":
                raise ProjectionQueryError("injected write failure")
            original_write(path, data)

        monkeypatch.setattr(sqlite_projection, "_write_private_case_bundle_file", fail_write)
    elif failure_point == "staging_sync":

        def fail_sync(path: Path) -> None:
            if path.name.startswith(".case.staging-"):
                raise OSError("injected staging sync failure")

        monkeypatch.setattr(sqlite_projection, "_fsync_directory", fail_sync)
    else:

        def fail_publish(_staging_dir: Path, _output_dir: Path) -> None:
            raise ProjectionQueryError("injected publish failure")

        monkeypatch.setattr(sqlite_projection, "_publish_case_bundle_directory", fail_publish)

    with pytest.raises((OSError, ProjectionQueryError), match=r"injected|failed to sync"):
        export_case_bundle(
            database_path,
            bundle_dir,
            journal_path=journal_path,
            trace_id="trace_01",
        )

    assert not bundle_dir.exists()
    assert list(tmp_path.glob(".case.staging-*")) == []


def test_case_bundle_export_refuses_destination_created_before_publish(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    journal_path = tmp_path / "events.jsonl"
    database_path = tmp_path / "projection.sqlite"
    bundle_dir = tmp_path / "case"
    sentinel = bundle_dir / "existing.txt"
    write_journal(journal_path, complete_timeline_events())
    rebuild_projection(journal_path, database_path)
    original_sync = sqlite_projection._fsync_directory

    def create_destination_after_staging_sync(path: Path) -> None:
        original_sync(path)
        if path.name.startswith(".case.staging-"):
            bundle_dir.mkdir()
            sentinel.write_text("existing\n", encoding="utf-8")

    monkeypatch.setattr(
        sqlite_projection,
        "_fsync_directory",
        create_destination_after_staging_sync,
    )

    with pytest.raises(ProjectionQueryError, match="case bundle output already exists"):
        export_case_bundle(
            database_path,
            bundle_dir,
            journal_path=journal_path,
            trace_id="trace_01",
        )

    assert sentinel.read_text(encoding="utf-8") == "existing\n"
    assert list(tmp_path.glob(".case.staging-*")) == []


def test_case_bundle_export_does_not_delete_existing_valid_bundle(tmp_path: Path) -> None:
    journal_path = tmp_path / "events.jsonl"
    database_path = tmp_path / "projection.sqlite"
    bundle_dir = tmp_path / "case"
    write_journal(journal_path, complete_timeline_events())
    rebuild_projection(journal_path, database_path)
    first = export_case_bundle(
        database_path,
        bundle_dir,
        journal_path=journal_path,
        trace_id="trace_01",
    )
    original_manifest = first.manifest_path.read_text(encoding="utf-8")

    with pytest.raises(ProjectionQueryError, match="case bundle output already exists"):
        export_case_bundle(
            database_path,
            bundle_dir,
            journal_path=journal_path,
            trace_id="trace_01",
        )

    assert first.manifest_path.read_text(encoding="utf-8") == original_manifest


def test_projection_cli_rebuild_timeline_and_incident_export(tmp_path: Path) -> None:
    journal_path = tmp_path / "events.jsonl"
    database_path = tmp_path / "projection.sqlite"
    write_journal(journal_path, complete_timeline_events())

    rebuild_result = runner.invoke(
        app,
        ["projection", "rebuild", str(journal_path), str(database_path)],
    )
    timeline_result = runner.invoke(
        app,
        [
            "projection",
            "timeline",
            str(database_path),
            "--journal-path",
            str(journal_path),
            "--trace-id",
            "trace_01",
        ],
    )
    export_result = runner.invoke(
        app,
        [
            "projection",
            "export-incident",
            str(database_path),
            "--journal-path",
            str(journal_path),
            "--run-id",
            "run_01",
        ],
    )

    rebuild_data = json.loads(rebuild_result.stdout)
    timeline_data = json.loads(timeline_result.stdout)
    export_data = json.loads(export_result.stdout)

    assert rebuild_result.exit_code == 0
    assert rebuild_data["records_indexed"] == 5
    assert timeline_result.exit_code == 0
    assert timeline_data["selector"] == {"type": "trace_id", "value": "trace_01"}
    assert timeline_data["event_count"] == 5
    assert [event["event_id"] for event in timeline_data["events"]] == [
        "evt_0",
        "evt_1",
        "evt_2",
        "evt_3",
        "evt_4",
    ]
    assert export_result.exit_code == 0
    assert export_data["export_version"] == "actionlineage.dev/incident-export-v0"
    assert export_data["selector"] == {"type": "run_id", "value": "run_01"}
    assert [event["event_type"] for event in export_data["events"]] == [
        "agent.run.started",
        "agent.tool.call.requested",
        "policy.decision",
        "agent.tool.call.denied",
        "agent.run.completed",
    ]


def test_projection_cli_filter_explain_and_case_export(tmp_path: Path) -> None:
    journal_path = tmp_path / "events.jsonl"
    database_path = tmp_path / "projection.sqlite"
    case_dir = tmp_path / "case"
    write_journal(journal_path, complete_timeline_events())
    rebuild_projection(journal_path, database_path)

    filter_result = runner.invoke(
        app,
        [
            "projection",
            "filter",
            str(database_path),
            "--journal-path",
            str(journal_path),
            "--event-type",
            "policy.decision",
        ],
    )
    explain_result = runner.invoke(
        app,
        [
            "projection",
            "explain-event",
            str(database_path),
            "evt_2",
            "--journal-path",
            str(journal_path),
        ],
    )
    case_result = runner.invoke(
        app,
        [
            "projection",
            "export-case",
            str(database_path),
            str(case_dir),
            "--journal-path",
            str(journal_path),
            "--trace-id",
            "trace_01",
        ],
    )

    filter_data = json.loads(filter_result.stdout)
    explain_data = json.loads(explain_result.stdout)
    case_data = json.loads(case_result.stdout)

    assert filter_result.exit_code == 0
    assert [event["event_id"] for event in filter_data["events"]] == ["evt_2"]
    assert explain_result.exit_code == 0
    assert explain_data["parent_event_id"] == "evt_1"
    assert explain_data["child_event_ids"] == ["evt_3"]
    assert case_result.exit_code == 0
    assert Path(case_data["markdown_path"]).exists()


def test_projection_cli_summarize(tmp_path: Path) -> None:
    journal_path = tmp_path / "events.jsonl"
    database_path = tmp_path / "projection.sqlite"
    write_journal(journal_path, complete_timeline_events())
    rebuild_projection(journal_path, database_path)

    result = runner.invoke(
        app,
        [
            "projection",
            "summarize",
            str(database_path),
            "--journal-path",
            str(journal_path),
            "--trace-id",
            "trace_01",
        ],
    )
    data = json.loads(result.stdout)

    assert result.exit_code == 0
    assert data["summary_version"] == "actionlineage.dev/grounded-summary-v0"
    assert data["model_provider"] is None
    assert data["grounded_event_ids"] == ["evt_0", "evt_1", "evt_2", "evt_3", "evt_4"]


def test_projection_cli_export_graph(tmp_path: Path) -> None:
    journal_path = tmp_path / "events.jsonl"
    database_path = tmp_path / "projection.sqlite"
    write_journal(journal_path, complete_timeline_events())
    rebuild_projection(journal_path, database_path)

    result = runner.invoke(
        app,
        [
            "projection",
            "export-graph",
            str(database_path),
            "--journal-path",
            str(journal_path),
            "--trace-id",
            "trace_01",
        ],
    )
    data = json.loads(result.stdout)

    assert result.exit_code == 0
    assert data["graph_version"] == "actionlineage.dev/investigation-graph-v0"
    assert data["selector"] == {"type": "trace_id", "value": "trace_01"}
    assert data["node_count"] >= 5
    edge_triples = {
        (edge["source"], edge["target"], edge["relationship"]) for edge in data["edges"]
    }
    assert ("event:evt_1", "event:evt_2", "causal_parent") in edge_triples


def test_projection_cli_rejects_corrupt_journal(tmp_path: Path) -> None:
    journal_path = tmp_path / "events.jsonl"
    database_path = tmp_path / "projection.sqlite"
    write_journal(journal_path, complete_timeline_events())
    lines = journal_lines(journal_path)
    lines[1] = lines[1].replace(b"synthetic.http_post", b"synthetic.changed")
    replace_journal_lines(journal_path, lines)

    result = runner.invoke(
        app,
        ["projection", "rebuild", str(journal_path), str(database_path)],
    )
    data = json.loads(result.stdout)

    assert result.exit_code == 1
    assert data["ok"] is False
    assert data["error"] == "journal_verification_failed"
    assert data["verification"]["issues"][0]["code"] == "event_hash_mismatch"
    assert not database_path.exists()
