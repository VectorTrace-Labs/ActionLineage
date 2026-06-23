from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from actionlineage.cli import app
from actionlineage.console import (
    ConsoleContextError,
    ConsoleNote,
    ConsoleSavedView,
    console_context_from_dict,
    load_console_context,
    render_console_html,
    write_console,
    write_desktop_bundle,
)
from actionlineage.demo import run_demo
from actionlineage.domain import RedactionPolicy
from actionlineage.projection import TimelineEvent, TimelineResult

runner = CliRunner()


def test_write_console_renders_demo_timeline_and_verification_matrix(tmp_path: Path) -> None:
    demo = run_demo(tmp_path / "demo")
    output_path = tmp_path / "console" / "index.html"

    export = write_console(demo.database_path, output_path, trace_id=demo.trace_id)
    html = output_path.read_text(encoding="utf-8")

    assert export.output_path == output_path
    assert export.event_count == demo.verification.records_verified
    assert "ActionLineage Investigation Console" in html
    assert "Verification Matrix" in html
    assert "Evidence Graph" in html
    assert "Evidence Links" in html
    assert "edge-causal" in html
    assert "edge-evidence" in html
    assert "evidence:corroborates: evt_demo_05 -&gt; evt_demo_06" in html
    assert "evt_demo_07" in html
    assert "verified" in html
    assert "unverified" in html
    assert "conflicting" in html
    assert "Content-Security-Policy" in html
    assert "default-src 'none'" in html
    assert "<script" not in html.lower()
    assert "acknowledgement is not side-effect verification" in html
    assert "proof " + "of absence" not in html.lower()


def test_console_cli_exports_static_html(tmp_path: Path) -> None:
    demo = run_demo(tmp_path / "demo")
    output_path = tmp_path / "console.html"

    result = runner.invoke(
        app,
        [
            "projection",
            "export-console",
            str(demo.database_path),
            str(output_path),
            "--trace-id",
            demo.trace_id,
        ],
    )
    payload = json.loads(result.stdout)

    assert result.exit_code == 0
    assert payload["ok"] is True
    assert payload["event_count"] == demo.verification.records_verified
    assert output_path.exists()


def test_console_cli_exports_static_html_by_run_id(tmp_path: Path) -> None:
    demo = run_demo(tmp_path / "demo")
    output_path = tmp_path / "run-console.html"

    result = runner.invoke(
        app,
        [
            "projection",
            "export-console",
            str(demo.database_path),
            str(output_path),
            "--run-id",
            demo.run_id,
        ],
    )
    payload = json.loads(result.stdout)
    html = output_path.read_text(encoding="utf-8")

    assert result.exit_code == 0
    assert payload["ok"] is True
    assert payload["event_count"] == demo.verification.records_verified
    assert output_path.exists()
    assert "Selector<strong>run_id</strong>" in html
    assert f"Value<strong>{demo.run_id}</strong>" in html
    assert "evidence:corroborates: evt_demo_05 -&gt; evt_demo_06" in html
    assert "verified" in html
    assert "unverified" in html
    assert "conflicting" in html
    assert "Content-Security-Policy" in html
    assert "proof " + "of absence" not in html.lower()


def test_console_cli_rejects_ambiguous_selectors_without_writing_html(
    tmp_path: Path,
) -> None:
    demo = run_demo(tmp_path / "demo")
    output_path = tmp_path / "ambiguous-console.html"

    result = runner.invoke(
        app,
        [
            "projection",
            "export-console",
            str(demo.database_path),
            str(output_path),
            "--trace-id",
            demo.trace_id,
            "--run-id",
            demo.run_id,
        ],
    )
    payload = json.loads(result.stdout)

    assert result.exit_code == 1
    assert payload == {"error": "provide exactly one of trace_id or run_id", "ok": False}
    assert not output_path.exists()


def test_console_cli_exports_empty_selector_html_without_absence_claims(
    tmp_path: Path,
) -> None:
    demo = run_demo(tmp_path / "demo")
    output_path = tmp_path / "empty-console.html"

    result = runner.invoke(
        app,
        [
            "projection",
            "export-console",
            str(demo.database_path),
            str(output_path),
            "--trace-id",
            "trace_not_present",
        ],
    )
    payload = json.loads(result.stdout)
    html = output_path.read_text(encoding="utf-8")

    assert result.exit_code == 0
    assert payload["ok"] is True
    assert payload["event_count"] == 0
    assert output_path.exists()
    assert "Events<strong>0</strong>" in html
    assert "No events matched this selector" in html
    assert "No verification states in this timeline" in html
    assert "No events in this timeline" in html
    assert "No evidence links in this timeline" in html
    assert "No event details matched this selector." in html
    assert html.count("<strong>0</strong>") == 5
    assert "Missing observation means no observation was recorded" in html
    assert "proof " + "of absence" not in html.lower()
    assert "Content-Security-Policy" in html


def test_write_desktop_bundle_creates_manifest_and_console(tmp_path: Path) -> None:
    demo = run_demo(tmp_path / "demo")
    output_dir = tmp_path / "desktop"

    export = write_desktop_bundle(demo.database_path, output_dir, trace_id=demo.trace_id)
    manifest = json.loads(export.manifest_path.read_text(encoding="utf-8"))
    html = export.console_path.read_text(encoding="utf-8")

    assert export.output_dir == output_dir
    assert export.console_path == output_dir / "index.html"
    assert export.event_count == demo.verification.records_verified
    assert manifest["bundle_version"] == "actionlineage.dev/desktop-bundle-v0"
    assert manifest["entrypoint"] == "index.html"
    assert manifest["canonical_source"] == "append-only local journal"
    assert any("No observation recorded is not proof" in item for item in manifest["limitations"])
    assert "ActionLineage Investigation Console" in html


def test_desktop_bundle_cli_exports_manifest_and_console(tmp_path: Path) -> None:
    demo = run_demo(tmp_path / "demo")
    output_dir = tmp_path / "desktop"

    result = runner.invoke(
        app,
        [
            "projection",
            "export-desktop-bundle",
            str(demo.database_path),
            str(output_dir),
            "--trace-id",
            demo.trace_id,
        ],
    )
    payload = json.loads(result.stdout)

    assert result.exit_code == 0
    assert payload["ok"] is True
    assert payload["bundle_version"] == "actionlineage.dev/desktop-bundle-v0"
    assert Path(payload["console_path"]).exists()
    assert Path(payload["manifest_path"]).exists()


def test_write_console_renders_sanitized_notes_and_saved_views(tmp_path: Path) -> None:
    demo = run_demo(tmp_path / "demo")
    output_path = tmp_path / "console" / "annotated.html"
    note = ConsoleNote(
        title="Triage <note>",
        body="Token=supersecretvalue should be redacted",
        event_id="evt_demo_07",
        author="analyst@example.invalid",
    )
    saved_view = ConsoleSavedView(
        name="Verified only",
        query="verification_status:verified",
        description="Focus on corroborated outcomes",
    )

    export = write_console(
        demo.database_path,
        output_path,
        trace_id=demo.trace_id,
        notes=(note,),
        saved_views=(saved_view,),
    )
    html = output_path.read_text(encoding="utf-8")

    assert export.note_count == 1
    assert export.saved_view_count == 1
    assert "Case Notes" in html
    assert "Saved Views" in html
    assert "Analyst annotations are not journal evidence" in html
    assert "Triage &lt;note&gt;" in html
    assert "supersecretvalue" not in html
    assert "Token=[REDACTED:secret]" in html


def test_write_console_escapes_hostile_context_fields_and_redacts_canaries(
    tmp_path: Path,
) -> None:
    demo = run_demo(tmp_path / "demo")
    output_path = tmp_path / "console" / "hostile-context.html"
    bearer_canary = "Bearer fake12345"
    token_canary = "contextcanarytoken"
    note = ConsoleNote(
        title='"><script>alert("note")</script>',
        body=(
            "../../case<script>.html\n"
            f"<img src=x onerror=alert(1)> {bearer_canary} token={token_canary}"
        ),
        event_id='evt_demo_07"><img src=x onerror=alert(1)>',
        author='analyst <a href="javascript:alert(1)">link</a>',
    )
    saved_view = ConsoleSavedView(
        name="<svg onload=alert(1)> reviewer view",
        query='verification_status:verified"><script>alert(1)</script>',
        description="file=../../evil<script>.html; javascript:alert(1); api_key=HOSTILEKEY123",
    )

    export = write_console(
        demo.database_path,
        output_path,
        trace_id=demo.trace_id,
        notes=(note,),
        saved_views=(saved_view,),
    )
    html = output_path.read_text(encoding="utf-8")
    lowercase_html = html.lower()

    assert export.event_count == demo.verification.records_verified
    assert export.note_count == 1
    assert export.saved_view_count == 1
    assert "Analyst annotations are not journal evidence" in html
    assert "<script" not in lowercase_html
    assert "<img" not in lowercase_html
    assert "<svg onload" not in lowercase_html
    assert "<a href" not in lowercase_html
    assert 'href="javascript:' not in lowercase_html
    assert "&lt;script&gt;alert" in html
    assert "&lt;svg onload=alert(1)&gt;" in html
    assert "&lt;img src=x onerror=alert(1)&gt;" in html
    assert "evt_demo_07&quot;&gt;&lt;img src=x onerror=alert(1)&gt;" in html
    assert "fake12345" not in html
    assert "contextcanarytoken" not in html
    assert "HOSTILEKEY123" not in html
    assert "Bearer [REDACTED:bearer_token]" in html
    assert "token=[REDACTED:secret]" in html
    assert "api_key=[REDACTED:secret]" in html


def test_render_console_html_shows_empty_timeline_without_absence_claims() -> None:
    timeline = TimelineResult(
        selector_type="trace_id",
        selector_value="trace_empty",
        events=(),
    )

    html = render_console_html(timeline)

    assert "ActionLineage Investigation Console" in html
    assert "Events<strong>0</strong>" in html
    assert "No events matched this selector" in html
    assert "No verification states in this timeline" in html
    assert "No events in this timeline" in html
    assert "No evidence links in this timeline" in html
    assert "No event details matched this selector." in html
    assert html.count("<strong>0</strong>") == 5
    assert "Missing observation means no observation was recorded" in html
    assert "proof " + "of absence" not in html.lower()
    assert "Content-Security-Policy" in html


def test_console_cli_loads_case_context_file(tmp_path: Path) -> None:
    demo = run_demo(tmp_path / "demo")
    output_path = tmp_path / "console.html"
    context_path = tmp_path / "context.json"
    context_path.write_text(
        json.dumps(
            {
                "notes": [{"title": "Reviewer", "body": "acknowledged is not verified"}],
                "saved_views": [
                    {
                        "name": "Open questions",
                        "query": "verification_status:unknown",
                        "description": "Events needing analyst follow-up",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    result = runner.invoke(
        app,
        [
            "projection",
            "export-console",
            str(demo.database_path),
            str(output_path),
            "--trace-id",
            demo.trace_id,
            "--case-context",
            str(context_path),
        ],
    )
    payload = json.loads(result.stdout)
    html = output_path.read_text(encoding="utf-8")

    assert result.exit_code == 0
    assert payload["note_count"] == 1
    assert payload["saved_view_count"] == 1
    assert "Reviewer" in html
    assert "Open questions" in html


def test_load_console_context_rejects_secret_values_without_leaking(tmp_path: Path) -> None:
    path = tmp_path / "context.json"
    path.write_text(
        json.dumps(
            {
                "notes": [
                    {
                        "title": "Secret test",
                        "body": "Bearer abcdefghijklmnop",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    notes, saved_views = load_console_context(path)

    assert saved_views == ()
    assert "abcdefghijklmnop" not in notes[0].body
    assert notes[0].body == "Bearer [REDACTED:bearer_token]"


def test_load_console_context_rejects_oversized_file_without_leaking(tmp_path: Path) -> None:
    path = tmp_path / "context.json"
    secret = "Bearer " + "oversized-context-secret-value"
    path.write_text(
        json.dumps({"notes": [{"title": "Oversized", "body": "A" * 128 + secret}]}),
        encoding="utf-8",
    )

    with pytest.raises(ConsoleContextError) as error:
        load_console_context(path, max_context_file_bytes=32)

    assert "console context file exceeds 32 byte limit" in str(error.value)
    assert secret not in str(error.value)


def test_console_context_rejects_excessive_annotation_counts() -> None:
    notes = [{"title": f"Note {index}", "body": "bounded"} for index in range(3)]
    saved_views = [
        {"name": f"View {index}", "query": "verification_status:unknown"} for index in range(3)
    ]

    with pytest.raises(ConsoleContextError) as notes_error:
        console_context_from_dict({"notes": notes}, max_context_items=2)
    with pytest.raises(ConsoleContextError) as views_error:
        console_context_from_dict({"saved_views": saved_views}, max_context_items=2)

    assert str(notes_error.value) == "console context notes exceeds 2 item limit"
    assert str(views_error.value) == "console context saved_views exceeds 2 item limit"


def test_console_context_marks_truncated_annotation_text() -> None:
    notes, _ = console_context_from_dict(
        {"notes": [{"title": "Long body", "body": "abcdefghijk"}]},
        redaction_policy=RedactionPolicy(max_string_length=4),
    )

    assert notes[0].body.startswith("abcd [TRUNCATED original_length=11 digest=sha256:")
    assert "efghijk" not in notes[0].body


def test_render_console_html_escapes_selector_and_payload() -> None:
    event = TimelineEvent(
        journal_record_number=1,
        event_id="evt_escape",
        event_type="agent.intent.recorded",
        occurred_at="2026-06-21T18:42:12Z",
        observed_at="2026-06-21T18:42:12Z",
        trace_id="<trace>",
        run_id="run_escape",
        sequence=1,
        event_hash="sha256:escape",
        verification_status=None,
        evidence_subject_event_id=None,
        evidence_event_id=None,
        event={
            "causality": {"parent_event_id": None},
            "payload": {"body": "<script>alert('x')</script>"},
        },
    )
    timeline = TimelineResult(
        selector_type="trace_id",
        selector_value="<trace>",
        events=(event,),
    )

    html = render_console_html(timeline, title="<Console>")

    assert "<script>alert" not in html
    assert "<script" not in html.lower()
    assert "&lt;script&gt;alert" in html
    assert "&lt;trace&gt;" in html
    assert "<title>&lt;Console&gt;</title>" in html


def test_render_console_graph_escapes_event_identifiers() -> None:
    parent = TimelineEvent(
        journal_record_number=1,
        event_id="evt_<parent>",
        event_type="agent.intent.recorded",
        occurred_at="2026-06-21T18:42:12Z",
        observed_at="2026-06-21T18:42:12Z",
        trace_id="trace_graph",
        run_id="run_graph",
        sequence=0,
        event_hash="sha256:parent",
        verification_status=None,
        evidence_subject_event_id=None,
        evidence_event_id=None,
        event={
            "causality": {"parent_event_id": None},
            "payload": {"body": "root"},
        },
    )
    child = TimelineEvent(
        journal_record_number=2,
        event_id="evt_<child>",
        event_type="side_effect.verified",
        occurred_at="2026-06-21T18:42:13Z",
        observed_at="2026-06-21T18:42:13Z",
        trace_id="trace_graph",
        run_id="run_graph",
        sequence=1,
        event_hash="sha256:child",
        verification_status="verified",
        evidence_subject_event_id="evt_<parent>",
        evidence_event_id="evt_<child>",
        event={
            "causality": {"parent_event_id": "evt_<parent>"},
            "payload": {
                "evidence_link": {
                    "relationship": "corroborates",
                    "subject_event_id": "evt_<parent>",
                    "evidence_event_id": "evt_<child>",
                    "observer_identity": "observer_<x>",
                    "confidence": 0.9,
                    "verification_status": "verified",
                }
            },
        },
    )
    timeline = TimelineResult(
        selector_type="trace_id",
        selector_value="trace_graph",
        events=(parent, child),
    )

    html = render_console_html(timeline)

    assert "Evidence Graph" in html
    assert "evt_<parent>" not in html
    assert "evt_&lt;parent&gt;" in html
    assert "causal: evt_&lt;parent&gt; -&gt; evt_&lt;child&gt;" in html
    assert "evidence:corroborates: evt_&lt;parent&gt; -&gt; evt_&lt;child&gt;" in html
