from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest
from typer.testing import CliRunner

from actionlineage.cli import app
from actionlineage.domain import (
    CorroborationType,
    EventEnvelope,
    EventType,
    EvidenceLink,
    EvidenceRelationship,
    VerificationStatus,
)
from actionlineage.journal import LocalJournal
from actionlineage.projection import (
    ProjectionQueryError,
    ProjectionVerificationError,
    explain_event,
    export_case_bundle,
    export_incident,
    export_investigation_graph,
    query_filtered_timeline,
    query_timeline,
    rebuild_projection,
    summarize_incident,
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


def write_journal(path: Path, events: tuple[EventEnvelope, ...]) -> LocalJournal:
    journal = LocalJournal(path)
    for event in events:
        journal.append(event)
    return journal


def journal_lines(path: Path) -> list[bytes]:
    return path.read_bytes().splitlines()


def replace_journal_lines(path: Path, lines: list[bytes]) -> None:
    path.write_bytes(b"\n".join(lines) + b"\n")


def test_projection_rebuild_is_repeatable_and_rebuilds_after_delete(tmp_path: Path) -> None:
    journal_path = tmp_path / "events.jsonl"
    database_path = tmp_path / "projection.sqlite"
    write_journal(journal_path, complete_timeline_events())

    first = rebuild_projection(journal_path, database_path)
    second = rebuild_projection(journal_path, database_path)
    database_path.unlink()
    rebuilt = rebuild_projection(journal_path, database_path)
    timeline = query_timeline(database_path, trace_id="trace_01")

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


def test_timeline_selector_values_are_bound_as_data(tmp_path: Path) -> None:
    journal_path = tmp_path / "events.jsonl"
    database_path = tmp_path / "projection.sqlite"
    write_journal(journal_path, complete_timeline_events())
    rebuild_projection(journal_path, database_path)

    injection_shaped = query_timeline(database_path, trace_id="trace_01' OR 1=1 --")
    normal = query_timeline(database_path, trace_id="trace_01")

    assert injection_shaped.events == ()
    assert normal.as_dict()["event_count"] == 5


def test_event_indexing_is_idempotent_for_the_same_projected_event(tmp_path: Path) -> None:
    journal_path = tmp_path / "events.jsonl"
    database_path = tmp_path / "projection.sqlite"
    journal = LocalJournal(journal_path)
    persisted_event = journal.append(
        timeline_event(0, EventType.AGENT_RUN_STARTED, parent_event_id=None)
    )

    with sqlite3.connect(database_path) as connection:
        ensure_schema(connection)
        first = index_event(connection, persisted_event, journal_record_number=1)
        second = index_event(connection, persisted_event, journal_record_number=1)

    assert first is True
    assert second is False


def test_projection_schema_v1_migrates_to_verification_indexes(tmp_path: Path) -> None:
    database_path = tmp_path / "projection.sqlite"

    with sqlite3.connect(database_path) as connection:
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

    timeline = query_timeline(database_path, run_id="run_01")

    assert exc_info.value.verification.ok is False
    assert timeline.as_dict()["event_count"] == 5
    assert timeline.events[2].event["payload"]["rule_id"] == "demo.restricted_external"


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
    timeline = query_timeline(database_path, trace_id="trace_01")
    incident = export_incident(database_path, trace_id="trace_01")

    assert timeline.events[1].event_type == unknown_event_type
    assert timeline.events[1].event["event_type"] == unknown_event_type
    assert incident.as_dict()["events"][1]["event_type"] == unknown_event_type


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
    timeline = query_timeline(database_path, trace_id="trace_01")
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

    by_tool = query_filtered_timeline(database_path, tool_name="safe_http.send")
    by_descriptor = query_filtered_timeline(database_path, descriptor_hash="sha256:demo")
    by_resource = query_filtered_timeline(database_path, resource="http://127.0.0.1/receiver")

    assert [event.event_id for event in by_tool.events] == ["evt_1"]
    assert [event.event_id for event in by_descriptor.events] == ["evt_1"]
    assert [event.event_id for event in by_resource.events] == ["evt_1"]


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

    incident = export_incident(database_path, trace_id="trace_01").as_dict()
    summary = incident["summary"]

    assert summary["principals"] == ["agent_demo"]
    assert "safe_http.send" in summary["tools"]
    assert "http://127.0.0.1/receiver" in summary["resources"]
    assert summary["verification_statuses"] == {"observed": 1, "verified": 1}
    assert summary["evidence_links"][0]["subject_event_id"] == "evt_1"
    assert "No observation recorded is not proof" in summary["claims_language"]


def test_grounded_summary_is_derived_from_incident_evidence(tmp_path: Path) -> None:
    journal_path = tmp_path / "events.jsonl"
    database_path = tmp_path / "projection.sqlite"
    write_journal(journal_path, complete_timeline_events())
    rebuild_projection(journal_path, database_path)

    summary = summarize_incident(database_path, trace_id="trace_01").as_dict()

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

    graph = export_investigation_graph(database_path, trace_id="trace_01").as_dict()
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

    explanation = explain_event(database_path, event_id="evt_1").as_dict()

    assert explanation["parent_event_id"] == "evt_0"
    assert explanation["child_event_ids"] == ["evt_2"]
    assert explanation["evidence_links_as_subject"][0]["evidence_event_id"] == "evt_2"


def test_case_bundle_export_writes_redacted_reports_without_absence_overclaim(
    tmp_path: Path,
) -> None:
    journal_path = tmp_path / "events.jsonl"
    database_path = tmp_path / "projection.sqlite"
    bundle_dir = tmp_path / "case"
    write_journal(journal_path, complete_timeline_events())
    rebuild_projection(journal_path, database_path)

    result = export_case_bundle(database_path, bundle_dir, trace_id="trace_01")
    markdown = result.markdown_path.read_text(encoding="utf-8")
    case_data = json.loads(result.json_path.read_text(encoding="utf-8"))
    ndjson_lines = result.ndjson_path.read_text(encoding="utf-8").splitlines()

    assert result.as_dict()["ok"] is True
    assert case_data["event_count"] == 5
    assert len(ndjson_lines) == 5
    assert "No observation recorded is not proof" in markdown
    assert "did not happen" not in markdown


def test_case_bundle_export_refuses_existing_artifacts(tmp_path: Path) -> None:
    journal_path = tmp_path / "events.jsonl"
    database_path = tmp_path / "projection.sqlite"
    bundle_dir = tmp_path / "case"
    write_journal(journal_path, complete_timeline_events())
    rebuild_projection(journal_path, database_path)
    bundle_dir.mkdir()
    existing = bundle_dir / "case.json"
    existing.write_text("existing\n", encoding="utf-8")

    with pytest.raises(ProjectionQueryError, match="already exists"):
        export_case_bundle(database_path, bundle_dir, trace_id="trace_01")

    assert existing.read_text(encoding="utf-8") == "existing\n"


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
        ["projection", "timeline", str(database_path), "--trace-id", "trace_01"],
    )
    export_result = runner.invoke(
        app,
        ["projection", "export-incident", str(database_path), "--run-id", "run_01"],
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
        ["projection", "filter", str(database_path), "--event-type", "policy.decision"],
    )
    explain_result = runner.invoke(
        app,
        ["projection", "explain-event", str(database_path), "evt_2"],
    )
    case_result = runner.invoke(
        app,
        ["projection", "export-case", str(database_path), str(case_dir), "--trace-id", "trace_01"],
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
        ["projection", "summarize", str(database_path), "--trace-id", "trace_01"],
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
        ["projection", "export-graph", str(database_path), "--trace-id", "trace_01"],
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
