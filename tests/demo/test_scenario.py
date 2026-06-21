from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from actionlineage.cli import app
from actionlineage.demo import DEMO_TRACE_ID, run_demo
from actionlineage.demo.scenario import build_demo_events
from actionlineage.domain import EventType
from actionlineage.journal import verify_journal
from actionlineage.projection import query_timeline

runner = CliRunner()


def test_demo_events_cover_verified_unverified_conflicting_and_not_dispatched_outcomes() -> None:
    events = build_demo_events()
    event_types = [event.event_type for event in events]
    status_values = json.dumps([event.payload for event in events], sort_keys=True)

    assert EventType.TOOL_EXECUTION_REQUESTED in event_types
    assert EventType.TOOL_EXECUTION_AUTHORIZED in event_types
    assert EventType.TOOL_EXECUTION_DISPATCHED in event_types
    assert EventType.TOOL_EXECUTION_ACKNOWLEDGED in event_types
    assert EventType.SIDE_EFFECT_OBSERVED in event_types
    assert EventType.SIDE_EFFECT_VERIFIED in event_types
    assert EventType.SIDE_EFFECT_UNVERIFIED in event_types
    assert EventType.SIDE_EFFECT_CONFLICT_DETECTED in event_types
    assert EventType.TOOL_EXECUTION_NOT_DISPATCHED in event_types
    assert '"verified"' in status_values
    assert '"unverified"' in status_values
    assert '"conflicting"' in status_values
    assert '"downstream_forwarded": false' in status_values


def test_run_demo_writes_verified_journal_projection_and_incident_export(tmp_path: Path) -> None:
    result = run_demo(tmp_path / "demo")
    timeline = query_timeline(result.database_path, trace_id=DEMO_TRACE_ID)
    incident = json.loads(result.incident_path.read_text(encoding="utf-8"))

    assert result.verification.ok
    assert verify_journal(
        result.journal_path,
        expected_record_count=result.verification.records_verified,
        expected_last_event_hash=result.verification.last_event_hash,
    ).ok
    assert result.projection.records_indexed == result.verification.records_verified
    assert timeline.as_dict()["event_count"] == result.verification.records_verified
    assert incident["event_count"] == result.verification.records_verified
    assert result.as_dict()["statuses"] == {
        "conflicting": 1,
        "observed": 1,
        "unverified": 2,
        "verified": 1,
    }


def test_demo_cli_outputs_investigation_commands(tmp_path: Path) -> None:
    result = runner.invoke(
        app,
        ["demo", "run", "--output-dir", str(tmp_path / "demo")],
    )
    data = json.loads(result.stdout)

    assert result.exit_code == 0
    assert data["ok"] is True
    assert data["trace_id"] == DEMO_TRACE_ID
    assert "journal verify" in data["commands"]["verify"]
    assert "projection timeline" in data["commands"]["timeline"]
    assert "projection export-console" in data["commands"]["console"]
    assert Path(data["incident_path"]).exists()
