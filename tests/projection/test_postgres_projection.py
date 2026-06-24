from __future__ import annotations

from pathlib import Path

import pytest

from actionlineage.demo import run_demo
from actionlineage.journal import JOURNAL_SOURCE_IDENTITY_VERSION
from actionlineage.projection import (
    POSTGRES_DEFAULT_TABLE,
    POSTGRES_PROJECTION_SCHEMA_VERSION,
    ProjectionRebuildError,
    ProjectionStateCode,
    ProjectionStateError,
    ProjectionVerificationError,
    postgres_insert_statement,
    postgres_schema_statements,
    rebuild_postgres_projection,
    verify_postgres_projection_state,
)


class RecordingExecutor:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, object] | None]] = []

    def execute(self, statement: str, parameters: dict[str, object] | None = None) -> object:
        self.calls.append((statement, parameters))
        return None

    @property
    def statements(self) -> tuple[str, ...]:
        return tuple(statement for statement, _ in self.calls)

    @property
    def parameter_sets(self) -> tuple[dict[str, object], ...]:
        return tuple(parameters for _, parameters in self.calls if parameters is not None)


class MaterializedPostgresReader:
    def __init__(self, executor: RecordingExecutor) -> None:
        self.metadata = _metadata_from_executor(executor)
        self.rows = _rows_from_executor(executor)
        self.queries: list[str] = []

    def fetch_all(
        self,
        statement: str,
        parameters: dict[str, object] | None = None,
    ) -> list[dict[str, object]]:
        assert parameters is None
        self.queries.append(statement)
        if "_metadata" in statement:
            return [{"key": key, "value": value} for key, value in self.metadata.items()]
        return [dict(row) for row in self.rows]


POSTGRES_VERIFIED_COLUMNS = (
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


def _metadata_from_executor(executor: RecordingExecutor) -> dict[str, str]:
    metadata_parameters = next(
        parameters
        for statement, parameters in executor.calls
        if "INSERT INTO actionlineage_events_metadata" in statement and parameters is not None
    )
    return {str(key): str(value) for key, value in metadata_parameters.items()}


def _rows_from_executor(executor: RecordingExecutor) -> list[dict[str, object]]:
    return [
        dict(parameters)
        for statement, parameters in executor.calls
        if "INSERT INTO actionlineage_events (" in statement and parameters is not None
    ]


def _tampered_value(column: str, value: object) -> object:
    if column in {"sequence", "journal_record_number"}:
        assert isinstance(value, int)
        return value + 1000
    if column == "event_json":
        assert isinstance(value, str)
        return value.replace('"event_id"', '"tampered_event_id"', 1)
    if value is None:
        return "unexpected"
    if column == "event_json_sha256":
        return "sha256:" + "0" * 64
    return f"tampered-{value}"


def test_postgres_schema_uses_rebuildable_projection_shape() -> None:
    ddl = "\n".join(postgres_schema_statements())
    insert = postgres_insert_statement()

    assert f"CREATE TABLE IF NOT EXISTS {POSTGRES_DEFAULT_TABLE}" in ddl
    assert "event_json JSONB NOT NULL" in ddl
    assert "event_json_sha256 TEXT NOT NULL" in ddl
    assert "verification_status" in ddl
    assert "evidence_subject_event_id" in ddl
    assert "journal_record_number INTEGER NOT NULL UNIQUE" in ddl
    assert "%(event_json_sha256)s" in insert
    assert "%(event_json)s::jsonb" in insert


def test_postgres_projection_rebuilds_from_verified_journal(tmp_path: Path) -> None:
    demo = run_demo(tmp_path / "demo")
    executor = RecordingExecutor()

    result = rebuild_postgres_projection(demo.journal_path, executor)

    assert result.records_indexed == demo.verification.records_verified
    assert result.last_event_hash == demo.verification.last_event_hash
    assert executor.statements[0] == "BEGIN"
    assert executor.statements[-1] == "COMMIT"
    inserted = [
        parameters
        for statement, parameters in executor.calls
        if "INSERT INTO actionlineage_events (" in statement and parameters is not None
    ]
    assert len(inserted) == demo.verification.records_verified
    verified = [
        parameters for parameters in inserted if parameters["verification_status"] == "verified"
    ]
    assert verified
    assert all(isinstance(parameters["event_json"], str) for parameters in inserted)
    metadata_parameters = next(
        parameters
        for statement, parameters in executor.calls
        if "INSERT INTO actionlineage_events_metadata" in statement and parameters is not None
    )
    assert str(metadata_parameters["source_journal_identity"]).startswith(
        f"{JOURNAL_SOURCE_IDENTITY_VERSION}:sha256:"
    )
    assert metadata_parameters["source_journal_identity_version"] == JOURNAL_SOURCE_IDENTITY_VERSION
    assert str(metadata_parameters["source_journal_sha256"]).startswith("sha256:")
    assert metadata_parameters["schema_version"] == str(POSTGRES_PROJECTION_SCHEMA_VERSION)
    assert all(
        str(parameters["event_json_sha256"]).startswith("sha256:") for parameters in inserted
    )


def test_postgres_projection_state_verifies_rebuilt_projection(tmp_path: Path) -> None:
    demo = run_demo(tmp_path / "demo")
    executor = RecordingExecutor()
    rebuild_postgres_projection(demo.journal_path, executor)
    reader = MaterializedPostgresReader(executor)

    snapshot = verify_postgres_projection_state(demo.journal_path, reader)

    assert snapshot.record_count == demo.verification.records_verified
    assert snapshot.terminal_hash == demo.verification.last_event_hash
    assert snapshot.table_name == POSTGRES_DEFAULT_TABLE
    assert snapshot.state == ProjectionStateCode.HEALTHY
    assert any("event_json_sha256" in query for query in reader.queries)


@pytest.mark.parametrize("column", POSTGRES_VERIFIED_COLUMNS)
def test_postgres_projection_state_rejects_tampered_projected_columns(
    tmp_path: Path,
    column: str,
) -> None:
    demo = run_demo(tmp_path / "demo")
    executor = RecordingExecutor()
    rebuild_postgres_projection(demo.journal_path, executor)
    reader = MaterializedPostgresReader(executor)
    reader.rows[0][column] = _tampered_value(column, reader.rows[0].get(column))

    with pytest.raises(ProjectionStateError) as exc_info:
        verify_postgres_projection_state(demo.journal_path, reader)

    assert exc_info.value.code == ProjectionStateCode.PROJECTION_MISMATCH
    assert column in exc_info.value.details["mismatched_columns"]


def test_postgres_projection_state_rejects_stale_metadata(tmp_path: Path) -> None:
    demo = run_demo(tmp_path / "demo")
    executor = RecordingExecutor()
    rebuild_postgres_projection(demo.journal_path, executor)
    reader = MaterializedPostgresReader(executor)
    reader.metadata["records_indexed"] = "1"

    with pytest.raises(ProjectionStateError) as exc_info:
        verify_postgres_projection_state(demo.journal_path, reader)

    assert exc_info.value.code == ProjectionStateCode.PROJECTION_STALE


def test_postgres_projection_state_rejects_unsupported_schema_metadata(tmp_path: Path) -> None:
    demo = run_demo(tmp_path / "demo")
    executor = RecordingExecutor()
    rebuild_postgres_projection(demo.journal_path, executor)
    reader = MaterializedPostgresReader(executor)
    reader.metadata["schema_version"] = "1"

    with pytest.raises(ProjectionStateError) as exc_info:
        verify_postgres_projection_state(demo.journal_path, reader)

    assert exc_info.value.code == ProjectionStateCode.PROJECTION_REBUILD_REQUIRED


def test_postgres_projection_state_rejects_corrupt_journal(tmp_path: Path) -> None:
    demo = run_demo(tmp_path / "demo")
    executor = RecordingExecutor()
    rebuild_postgres_projection(demo.journal_path, executor)
    reader = MaterializedPostgresReader(executor)
    lines = demo.journal_path.read_bytes().splitlines()
    lines[0] = lines[0].replace(b"agent.intent.recorded", b"agent.intent.modified")
    demo.journal_path.write_bytes(b"\n".join(lines) + b"\n")

    with pytest.raises(ProjectionStateError) as exc_info:
        verify_postgres_projection_state(demo.journal_path, reader)

    assert exc_info.value.code == ProjectionStateCode.JOURNAL_INVALID


def test_postgres_projection_rejects_corrupt_journal_before_writing(tmp_path: Path) -> None:
    demo = run_demo(tmp_path / "demo")
    lines = demo.journal_path.read_bytes().splitlines()
    lines[0] = lines[0].replace(b"agent.intent.recorded", b"agent.intent.modified")
    demo.journal_path.write_bytes(b"\n".join(lines) + b"\n")
    executor = RecordingExecutor()

    with pytest.raises(ProjectionVerificationError):
        rebuild_postgres_projection(demo.journal_path, executor)

    assert executor.calls == []


def test_postgres_projection_rolls_back_executor_failures(tmp_path: Path) -> None:
    demo = run_demo(tmp_path / "demo")

    class FailingExecutor(RecordingExecutor):
        def execute(self, statement: str, parameters: dict[str, object] | None = None) -> object:
            if "DELETE FROM" in statement:
                raise RuntimeError("database unavailable")
            return super().execute(statement, parameters)

    executor = FailingExecutor()

    with pytest.raises(ProjectionRebuildError, match="postgres projection rebuild failed"):
        rebuild_postgres_projection(demo.journal_path, executor)

    assert executor.statements[-1] == "ROLLBACK"


def test_postgres_projection_rejects_unsafe_table_names(tmp_path: Path) -> None:
    demo = run_demo(tmp_path / "demo")

    with pytest.raises(ProjectionRebuildError, match="unsupported PostgreSQL identifier"):
        rebuild_postgres_projection(
            demo.journal_path,
            RecordingExecutor(),
            table_name="events;drop",
        )
