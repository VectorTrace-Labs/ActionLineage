from __future__ import annotations

from pathlib import Path

import pytest

from actionlineage.demo import run_demo
from actionlineage.journal import JOURNAL_SOURCE_IDENTITY_VERSION
from actionlineage.projection import (
    POSTGRES_DEFAULT_TABLE,
    ProjectionRebuildError,
    ProjectionVerificationError,
    postgres_insert_statement,
    postgres_schema_statements,
    rebuild_postgres_projection,
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


def test_postgres_schema_uses_rebuildable_projection_shape() -> None:
    ddl = "\n".join(postgres_schema_statements())
    insert = postgres_insert_statement()

    assert f"CREATE TABLE IF NOT EXISTS {POSTGRES_DEFAULT_TABLE}" in ddl
    assert "event_json JSONB NOT NULL" in ddl
    assert "verification_status" in ddl
    assert "evidence_subject_event_id" in ddl
    assert "journal_record_number INTEGER NOT NULL UNIQUE" in ddl
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
