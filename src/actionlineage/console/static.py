"""Static investigation console renderer."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from html import escape
from pathlib import Path
from typing import Any, cast

from actionlineage.domain import RedactionPolicy, deterministic_json_bytes
from actionlineage.domain.events import JsonObject
from actionlineage.projection import TimelineEvent, TimelineResult, query_timeline

DESKTOP_BUNDLE_VERSION = "actionlineage.dev/desktop-bundle-v0"
MAX_CONSOLE_CONTEXT_FILE_BYTES = 64 * 1024
MAX_CONSOLE_CONTEXT_ITEMS = 50
CONSOLE_CONTENT_SECURITY_POLICY = (
    "default-src 'none'; "
    "img-src data:; "
    "style-src 'unsafe-inline'; "
    "base-uri 'none'; "
    "form-action 'none'; "
    "frame-ancestors 'none'"
)


@dataclass(frozen=True, slots=True)
class ConsoleExport:
    """Generated static console artifact."""

    output_path: Path
    event_count: int
    note_count: int = 0
    saved_view_count: int = 0

    def as_dict(self) -> dict[str, object]:
        """Return a JSON-compatible export result."""

        return {
            "ok": True,
            "output_path": str(self.output_path),
            "event_count": self.event_count,
            "note_count": self.note_count,
            "saved_view_count": self.saved_view_count,
        }


@dataclass(frozen=True, slots=True)
class DesktopBundleExport:
    """Generated desktop-shell bundle artifacts."""

    output_dir: Path
    console_path: Path
    manifest_path: Path
    event_count: int
    bundle_version: str = DESKTOP_BUNDLE_VERSION

    def as_dict(self) -> dict[str, object]:
        """Return a JSON-compatible desktop bundle result."""

        return {
            "ok": True,
            "bundle_version": self.bundle_version,
            "output_dir": str(self.output_dir),
            "console_path": str(self.console_path),
            "manifest_path": str(self.manifest_path),
            "event_count": self.event_count,
        }


@dataclass(frozen=True, slots=True)
class ConsoleNote:
    """Sanitized analyst note rendered into a static console export."""

    title: str
    body: str
    event_id: str | None = None
    author: str | None = None


@dataclass(frozen=True, slots=True)
class ConsoleSavedView:
    """Saved filter/view metadata rendered into a static console export."""

    name: str
    query: str
    description: str = ""


class ConsoleContextError(ValueError):
    """Raised when console annotation context cannot be safely loaded."""


def load_console_context(
    path: Path,
    *,
    redaction_policy: RedactionPolicy | None = None,
    max_context_file_bytes: int = MAX_CONSOLE_CONTEXT_FILE_BYTES,
    max_context_items: int = MAX_CONSOLE_CONTEXT_ITEMS,
) -> tuple[tuple[ConsoleNote, ...], tuple[ConsoleSavedView, ...]]:
    """Load sanitized console notes and saved views from a JSON file."""

    if max_context_file_bytes < 0:
        raise ConsoleContextError("console context file byte limit must be non-negative")
    path = Path(path)
    try:
        size_bytes = path.stat().st_size
    except OSError as exc:
        raise ConsoleContextError("console context file could not be inspected") from exc
    if size_bytes > max_context_file_bytes:
        raise ConsoleContextError(
            f"console context file exceeds {max_context_file_bytes} byte limit"
        )
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ConsoleContextError("console context must be valid JSON") from exc
    return console_context_from_dict(
        data,
        redaction_policy=redaction_policy,
        max_context_items=max_context_items,
    )


def console_context_from_dict(
    data: object,
    *,
    redaction_policy: RedactionPolicy | None = None,
    max_context_items: int = MAX_CONSOLE_CONTEXT_ITEMS,
) -> tuple[tuple[ConsoleNote, ...], tuple[ConsoleSavedView, ...]]:
    """Build sanitized console notes and saved views from a mapping."""

    if not isinstance(data, dict):
        raise ConsoleContextError("console context must be an object")
    if max_context_items < 0:
        raise ConsoleContextError("console context item limit must be non-negative")
    policy = redaction_policy or RedactionPolicy()
    notes = _notes_from_context(data.get("notes", ()), policy, max_context_items)
    saved_views = _saved_views_from_context(data.get("saved_views", ()), policy, max_context_items)
    return notes, saved_views


def write_console(
    database_path: Path,
    output_path: Path,
    *,
    journal_path: Path,
    trace_id: str | None = None,
    run_id: str | None = None,
    notes: tuple[ConsoleNote, ...] = (),
    saved_views: tuple[ConsoleSavedView, ...] = (),
    redaction_policy: RedactionPolicy | None = None,
) -> ConsoleExport:
    """Write a static HTML investigation console from the projection."""

    timeline = query_timeline(
        database_path,
        journal_path=journal_path,
        trace_id=trace_id,
        run_id=run_id,
    )
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        render_console_html(
            timeline,
            notes=notes,
            saved_views=saved_views,
            redaction_policy=redaction_policy,
        ),
        encoding="utf-8",
    )
    return ConsoleExport(
        output_path=output_path,
        event_count=len(timeline.events),
        note_count=len(notes),
        saved_view_count=len(saved_views),
    )


def write_desktop_bundle(
    database_path: Path,
    output_dir: Path,
    *,
    journal_path: Path,
    trace_id: str | None = None,
    run_id: str | None = None,
    notes: tuple[ConsoleNote, ...] = (),
    saved_views: tuple[ConsoleSavedView, ...] = (),
    redaction_policy: RedactionPolicy | None = None,
) -> DesktopBundleExport:
    """Write a deterministic bundle for optional native desktop shells."""

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    console_path = output_dir / "index.html"
    manifest_path = output_dir / "actionlineage-desktop.json"
    console = write_console(
        database_path,
        console_path,
        journal_path=journal_path,
        trace_id=trace_id,
        run_id=run_id,
        notes=notes,
        saved_views=saved_views,
        redaction_policy=redaction_policy,
    )
    manifest: dict[str, Any] = {
        "bundle_version": DESKTOP_BUNDLE_VERSION,
        "entrypoint": "index.html",
        "event_count": console.event_count,
        "canonical_source": "append-only local journal",
        "runtime": "native_shell_optional",
        "required_capabilities": ["local_file_view"],
        "limitations": [
            "Desktop bundle is a rendered analyst view, not canonical evidence.",
            "No observation recorded is not proof that a side effect did not occur.",
        ],
    }
    manifest_path.write_bytes(deterministic_json_bytes(cast(JsonObject, manifest)) + b"\n")
    return DesktopBundleExport(
        output_dir=output_dir,
        console_path=console_path,
        manifest_path=manifest_path,
        event_count=console.event_count,
    )


def render_console_html(
    timeline: TimelineResult,
    *,
    title: str = "ActionLineage Console",
    notes: tuple[ConsoleNote, ...] = (),
    saved_views: tuple[ConsoleSavedView, ...] = (),
    redaction_policy: RedactionPolicy | None = None,
) -> str:
    """Render a dense, static investigation console."""

    policy = redaction_policy or RedactionPolicy()
    notes = tuple(_sanitize_note(note, policy) for note in notes)
    saved_views = tuple(_sanitize_saved_view(saved_view, policy) for saved_view in saved_views)
    rows = "\n".join(_timeline_row(event) for event in timeline.events)
    details = "\n".join(_event_detail(event) for event in timeline.events)
    verification_rows = "\n".join(_verification_row(event) for event in timeline.events)
    graph = _evidence_graph(timeline.events)
    evidence_rows = "\n".join(
        row for row in (_evidence_link_row(event) for event in timeline.events) if row
    )
    timeline_rows = rows or _empty_row(5, "No events matched this selector")
    verification_table_rows = verification_rows or _empty_row(
        4,
        "No verification states in this timeline",
    )
    detail_rows = details or '<p class="note">No event details matched this selector.</p>'
    status_counts = _status_counts(timeline.events)
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta http-equiv="Content-Security-Policy" content="{CONSOLE_CONTENT_SECURITY_POLICY}">
  <title>{escape(title)}</title>
  <style>
    :root {{
      color-scheme: light;
      font-family:
        Inter,
        ui-sans-serif,
        system-ui,
        -apple-system,
        BlinkMacSystemFont,
        "Segoe UI",
        sans-serif;
      background: #f6f8fb;
      color: #17202c;
    }}
    body {{ margin: 0; }}
    header {{
      display: flex;
      justify-content: space-between;
      align-items: center;
      gap: 24px;
      padding: 18px 24px;
      border-bottom: 1px solid #cbd5e1;
      background: #ffffff;
    }}
    h1 {{ font-size: 20px; margin: 0; font-weight: 700; }}
    h2 {{ letter-spacing: 0; }}
    main {{
      display: grid;
      grid-template-columns: minmax(220px, 280px) minmax(0, 1fr);
      min-height: calc(100vh - 65px);
    }}
    aside {{
      border-right: 1px solid #cbd5e1;
      background: #eef3f8;
      padding: 18px;
    }}
    section {{ padding: 18px 24px; }}
    .metric {{ font-size: 12px; text-transform: uppercase; color: #526274; }}
    .metric strong {{ display: block; font-size: 22px; color: #17202c; margin-top: 4px; }}
    .note {{ font-size: 13px; line-height: 1.5; color: #445468; }}
    .status-grid {{
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 8px;
      margin-top: 16px;
    }}
    .status {{ background: #ffffff; border: 1px solid #d8e0ea; padding: 8px; }}
    .status strong {{ display: block; font-size: 18px; color: #17202c; }}
    .annotation {{
      background: #ffffff;
      border: 1px solid #d8e0ea;
      padding: 10px;
      margin-top: 10px;
    }}
    .annotation strong {{ display: block; font-size: 13px; margin-bottom: 4px; }}
    .annotation p {{ margin: 0; font-size: 12px; line-height: 1.45; color: #445468; }}
    .annotation code {{ overflow-wrap: anywhere; }}
    table {{ width: 100%; border-collapse: collapse; background: #ffffff; }}
    th, td {{
      border-bottom: 1px solid #d8e0ea;
      padding: 8px 10px;
      text-align: left;
      font-size: 13px;
      vertical-align: top;
    }}
    th {{ background: #e8eef5; color: #2e3a48; font-size: 12px; text-transform: uppercase; }}
    code {{ font-family: "SFMono-Regular", Consolas, monospace; font-size: 12px; }}
    .split {{
      display: grid;
      grid-template-columns: minmax(0, 1.15fr) minmax(320px, .85fr);
      gap: 18px;
    }}
    .panel-title {{ font-size: 14px; margin: 20px 0 8px; color: #243244; }}
    .event-detail {{ border-top: 1px solid #d8e0ea; padding: 10px 0; }}
    .payload {{
      white-space: pre-wrap;
      overflow-wrap: anywhere;
      background: #f8fafc;
      padding: 10px;
      border: 1px solid #d8e0ea;
    }}
    .graph-wrap {{
      background: #ffffff;
      border: 1px solid #d8e0ea;
      overflow-x: auto;
      padding: 12px;
    }}
    .graph {{ display: block; min-width: 760px; }}
    .graph-edge {{ stroke-width: 1.7; fill: none; }}
    .edge-causal {{ stroke: #475569; }}
    .edge-evidence {{ stroke: #2563eb; stroke-dasharray: 6 4; }}
    .graph-node rect {{ fill: #f8fafc; stroke: #94a3b8; stroke-width: 1.2; }}
    .graph-node text {{ font-size: 11px; fill: #17202c; }}
    .graph-node .node-type {{ font-weight: 700; }}
    .legend {{
      display: flex;
      gap: 16px;
      flex-wrap: wrap;
      font-size: 12px;
      color: #445468;
      margin: 8px 0 0;
    }}
    .legend span::before {{
      content: "";
      display: inline-block;
      width: 22px;
      border-top: 2px solid #475569;
      margin-right: 6px;
      vertical-align: middle;
    }}
    .legend .evidence::before {{
      border-top-color: #2563eb;
      border-top-style: dashed;
    }}
    .state-verified {{ color: #166534; font-weight: 700; }}
    .state-unverified, .state-unknown {{ color: #854d0e; font-weight: 700; }}
    .state-timed_out, .state-conflicting {{ color: #991b1b; font-weight: 700; }}
    @media (max-width: 860px) {{
      main, .split {{ display: block; }}
      aside {{ border-right: 0; border-bottom: 1px solid #cbd5e1; }}
    }}
  </style>
</head>
<body>
  <header>
    <h1>ActionLineage Investigation Console</h1>
    <div class="metric">Events<strong>{len(timeline.events)}</strong></div>
  </header>
  <main>
    <aside>
      <div class="metric">Selector<strong>{escape(timeline.selector_type)}</strong></div>
      <div class="metric">Value<strong>{escape(timeline.selector_value)}</strong></div>
      <p class="note">
        Rendered from the rebuildable projection. The local journal remains canonical evidence.
      </p>
      <p class="note">Missing observation means no observation was recorded in this case bundle.</p>
      <div class="status-grid">
        {_status_card("Verified", status_counts.get("verified", 0))}
        {_status_card("Unverified", status_counts.get("unverified", 0))}
        {_status_card("Timed Out", status_counts.get("timed_out", 0))}
        {_status_card("Conflicting", status_counts.get("conflicting", 0))}
      </div>
      {_saved_views(saved_views)}
      {_case_notes(notes)}
    </aside>
    <section>
      <div class="split">
        <div>
          <h2 class="panel-title">Timeline</h2>
          <table aria-label="Timeline">
            <thead><tr><th>Seq</th><th>Time</th><th>Type</th><th>Event</th><th>Parent</th></tr></thead>
            <tbody>{timeline_rows}</tbody>
          </table>
        </div>
        <div>
          <h2 class="panel-title">Verification Matrix</h2>
          <table aria-label="Verification Matrix">
            <thead><tr><th>Event</th><th>Status</th><th>Evidence</th><th>Subject</th></tr></thead>
            <tbody>{verification_table_rows}</tbody>
          </table>
        </div>
      </div>
      <h2 class="panel-title">Evidence Graph</h2>
      {graph}
      <h2 class="panel-title">Evidence Links</h2>
      <table aria-label="Evidence Links">
        <thead><tr><th>Relationship</th><th>Subject</th><th>Evidence</th><th>Observer</th><th>Confidence</th></tr></thead>
        <tbody>{evidence_rows or _empty_row(5, "No evidence links in this timeline")}</tbody>
      </table>
      <h2 class="panel-title">Event Details</h2>
      {detail_rows}
    </section>
  </main>
</body>
</html>
"""


def _notes_from_context(
    value: object,
    policy: RedactionPolicy,
    max_context_items: int,
) -> tuple[ConsoleNote, ...]:
    if value in (None, ()):
        return ()
    if not isinstance(value, list):
        raise ConsoleContextError("console context notes must be an array")
    _check_context_item_count("notes", len(value), max_context_items)
    return tuple(_note_from_context(item, policy) for item in value)


def _note_from_context(value: object, policy: RedactionPolicy) -> ConsoleNote:
    if not isinstance(value, dict):
        raise ConsoleContextError("console note must be an object")
    item = cast(dict[object, object], value)
    return ConsoleNote(
        title=_required_context_text(item, "title", policy),
        body=_required_context_text(item, "body", policy),
        event_id=_optional_context_text(item, "event_id", policy),
        author=_optional_context_text(item, "author", policy),
    )


def _saved_views_from_context(
    value: object,
    policy: RedactionPolicy,
    max_context_items: int,
) -> tuple[ConsoleSavedView, ...]:
    if value in (None, ()):
        return ()
    if not isinstance(value, list):
        raise ConsoleContextError("console context saved_views must be an array")
    _check_context_item_count("saved_views", len(value), max_context_items)
    return tuple(_saved_view_from_context(item, policy) for item in value)


def _check_context_item_count(field: str, count: int, max_context_items: int) -> None:
    if count > max_context_items:
        raise ConsoleContextError(f"console context {field} exceeds {max_context_items} item limit")


def _saved_view_from_context(value: object, policy: RedactionPolicy) -> ConsoleSavedView:
    if not isinstance(value, dict):
        raise ConsoleContextError("console saved view must be an object")
    item = cast(dict[object, object], value)
    return ConsoleSavedView(
        name=_required_context_text(item, "name", policy),
        query=_required_context_text(item, "query", policy),
        description=_optional_context_text(item, "description", policy) or "",
    )


def _required_context_text(
    item: dict[object, object],
    field: str,
    policy: RedactionPolicy,
) -> str:
    value = item.get(field)
    if not isinstance(value, str) or not value:
        raise ConsoleContextError(f"console context field is required: {field}")
    return _redacted_context_text(value, policy)


def _optional_context_text(
    item: dict[object, object],
    field: str,
    policy: RedactionPolicy,
) -> str | None:
    value = item.get(field)
    if value is None:
        return None
    if not isinstance(value, str) or not value:
        raise ConsoleContextError(f"console context field must be text: {field}")
    return _redacted_context_text(value, policy)


def _redacted_context_text(value: str, policy: RedactionPolicy) -> str:
    redacted = policy.apply(value)
    if isinstance(redacted, str):
        return redacted
    if isinstance(redacted, dict) and redacted.get("marker") == "actionlineage.capture.v1":
        captured = redacted.get("value")
        prefix = captured if isinstance(captured, str) else ""
        separator = " " if prefix else ""
        return f"{prefix}{separator}{_capture_limit_note(redacted)}"
    return json.dumps(redacted, sort_keys=True)


def _capture_limit_note(metadata: Mapping[str, object]) -> str:
    original_length = metadata.get("original_length", "unknown")
    digest = metadata.get("digest", "unknown")
    digest_scope = metadata.get("digest_scope", "unknown")
    return (
        f"[TRUNCATED original_length={original_length} digest={digest} digest_scope={digest_scope}]"
    )


def _sanitize_note(note: ConsoleNote, policy: RedactionPolicy) -> ConsoleNote:
    return ConsoleNote(
        title=_redacted_context_text(note.title, policy),
        body=_redacted_context_text(note.body, policy),
        event_id=_redacted_context_text(note.event_id, policy) if note.event_id else None,
        author=_redacted_context_text(note.author, policy) if note.author else None,
    )


def _sanitize_saved_view(
    saved_view: ConsoleSavedView,
    policy: RedactionPolicy,
) -> ConsoleSavedView:
    return ConsoleSavedView(
        name=_redacted_context_text(saved_view.name, policy),
        query=_redacted_context_text(saved_view.query, policy),
        description=_redacted_context_text(saved_view.description, policy)
        if saved_view.description
        else "",
    )


def _saved_views(saved_views: tuple[ConsoleSavedView, ...]) -> str:
    if not saved_views:
        return ""
    items = "\n".join(_saved_view_item(saved_view) for saved_view in saved_views)
    return f"""
      <h2 class="panel-title">Saved Views</h2>
      <p class="note">Saved views are static filter hints for this export.</p>
      {items}
    """


def _saved_view_item(saved_view: ConsoleSavedView) -> str:
    description = f"<p>{escape(saved_view.description)}</p>" if saved_view.description else ""
    return (
        '<div class="annotation">'
        f"<strong>{escape(saved_view.name)}</strong>"
        f"<p><code>{escape(saved_view.query)}</code></p>"
        f"{description}"
        "</div>"
    )


def _case_notes(notes: tuple[ConsoleNote, ...]) -> str:
    if not notes:
        return ""
    items = "\n".join(_case_note_item(note) for note in notes)
    return f"""
      <h2 class="panel-title">Case Notes</h2>
      <p class="note">
        Analyst annotations are not journal evidence and do not change verification status.
      </p>
      {items}
    """


def _case_note_item(note: ConsoleNote) -> str:
    event = f"<p>Event: <code>{escape(note.event_id)}</code></p>" if note.event_id else ""
    author = f"<p>Author: {escape(note.author)}</p>" if note.author else ""
    body = escape(note.body).replace("\n", "<br>")
    return (
        '<div class="annotation">'
        f"<strong>{escape(note.title)}</strong>"
        f"<p>{body}</p>"
        f"{event}"
        f"{author}"
        "</div>"
    )


def _timeline_row(event: TimelineEvent) -> str:
    event_id = escape(event.event_id)
    parent = escape(_parent_event_id(event) or "root")
    return (
        "<tr>"
        f"<td>{event.sequence}</td>"
        f"<td>{escape(event.occurred_at)}</td>"
        f"<td>{escape(event.event_type)}</td>"
        f"<td><code>{event_id}</code></td>"
        f"<td><code>{parent}</code></td>"
        "</tr>"
    )


def _event_detail(event: TimelineEvent) -> str:
    payload = escape(json.dumps(event.event, indent=2, sort_keys=True))
    return (
        '<div class="event-detail">'
        f"<strong><code>{escape(event.event_id)}</code></strong> "
        f"{escape(event.event_type)}"
        f'<pre class="payload">{payload}</pre>'
        "</div>"
    )


def _verification_row(event: TimelineEvent) -> str:
    status = _verification_status(event)
    evidence = event.evidence_event_id or "-"
    subject = event.evidence_subject_event_id or "-"
    return (
        "<tr>"
        f"<td><code>{escape(event.event_id)}</code></td>"
        f'<td class="state-{escape(status)}">{escape(status)}</td>'
        f"<td><code>{escape(evidence)}</code></td>"
        f"<td><code>{escape(subject)}</code></td>"
        "</tr>"
    )


def _evidence_link_row(event: TimelineEvent) -> str:
    link = _evidence_link(event)
    if link is None:
        return ""
    return (
        "<tr>"
        f"<td>{escape(str(link.get('relationship', '-')))}</td>"
        f"<td><code>{escape(str(link.get('subject_event_id', '-')))}</code></td>"
        f"<td><code>{escape(str(link.get('evidence_event_id', '-')))}</code></td>"
        f"<td>{escape(str(link.get('observer_identity', '-')))}</td>"
        f"<td>{escape(str(link.get('confidence', '-')))}</td>"
        "</tr>"
    )


def _status_card(label: str, count: int) -> str:
    return f'<div class="status">{escape(label)}<strong>{count}</strong></div>'


def _empty_row(columns: int, label: str) -> str:
    return f'<tr><td colspan="{columns}">{escape(label)}</td></tr>'


def _evidence_graph(events: tuple[TimelineEvent, ...]) -> str:
    if not events:
        return '<div class="graph-wrap">No events in this timeline</div>'

    positions = _graph_positions(events)
    width = max(760, 170 * len(events) + 80)
    height = 280
    causal_edges = "\n".join(_causal_edge(event, positions) for event in events)
    evidence_edges = "\n".join(_evidence_edge(event, positions) for event in events)
    nodes = "\n".join(_graph_node(event, positions[event.event_id]) for event in events)
    return f"""
      <div class="graph-wrap">
        <svg class="graph" role="img" aria-label="Evidence Graph" viewBox="0 0 {width} {height}">
          <defs>
            <marker id="arrow-causal" viewBox="0 0 10 10" refX="9" refY="5"
              markerWidth="6" markerHeight="6" orient="auto-start-reverse">
              <path d="M 0 0 L 10 5 L 0 10 z" fill="#475569"></path>
            </marker>
            <marker id="arrow-evidence" viewBox="0 0 10 10" refX="9" refY="5"
              markerWidth="6" markerHeight="6" orient="auto-start-reverse">
              <path d="M 0 0 L 10 5 L 0 10 z" fill="#2563eb"></path>
            </marker>
          </defs>
          {causal_edges}
          {evidence_edges}
          {nodes}
        </svg>
        <div class="legend">
          <span>Causal parent to child</span>
          <span class="evidence">Evidence link subject to evidence</span>
        </div>
      </div>
    """


def _graph_positions(events: tuple[TimelineEvent, ...]) -> dict[str, tuple[int, int]]:
    positions: dict[str, tuple[int, int]] = {}
    for index, event in enumerate(events):
        positions[event.event_id] = (90 + index * 170, 90 + (index % 2) * 90)
    return positions


def _causal_edge(event: TimelineEvent, positions: dict[str, tuple[int, int]]) -> str:
    parent_id = _parent_event_id(event)
    if parent_id is None or parent_id not in positions:
        return ""
    start = positions[parent_id]
    end = positions[event.event_id]
    title = f"causal: {parent_id} -> {event.event_id}"
    return _graph_edge(start, end, title=title, css_class="edge-causal", marker="arrow-causal")


def _evidence_edge(event: TimelineEvent, positions: dict[str, tuple[int, int]]) -> str:
    link = _evidence_link(event)
    if link is None:
        return ""
    subject = link.get("subject_event_id")
    evidence = link.get("evidence_event_id")
    if not isinstance(subject, str) or not isinstance(evidence, str):
        return ""
    if subject not in positions or evidence not in positions:
        return ""
    relationship = str(link.get("relationship", "evidence"))
    title = f"evidence:{relationship}: {subject} -> {evidence}"
    return _graph_edge(
        positions[subject],
        positions[evidence],
        title=title,
        css_class="edge-evidence",
        marker="arrow-evidence",
    )


def _graph_edge(
    start: tuple[int, int],
    end: tuple[int, int],
    *,
    title: str,
    css_class: str,
    marker: str,
) -> str:
    x1, y1 = start
    x2, y2 = end
    return (
        f'<line class="graph-edge {css_class}" x1="{x1}" y1="{y1}" '
        f'x2="{x2}" y2="{y2}" marker-end="url(#{marker})">'
        f"<title>{escape(title)}</title>"
        "</line>"
    )


def _graph_node(event: TimelineEvent, position: tuple[int, int]) -> str:
    x, y = position
    status = _verification_status(event)
    label = _short_event_type(event.event_type)
    event_id = _short_event_id(event.event_id)
    transform = f"translate({x - 62},{y - 28})"
    return f"""
      <g class="graph-node state-{escape(_css_token(status))}" transform="{transform}">
        <title>{escape(event.event_id)} {escape(event.event_type)} {escape(status)}</title>
        <rect width="124" height="56" rx="6"></rect>
        <text class="node-type" x="10" y="20">{escape(label)}</text>
        <text x="10" y="38">{escape(event_id)}</text>
        <text x="86" y="38">{escape(status)}</text>
      </g>
    """


def _short_event_type(event_type: str) -> str:
    tail = event_type.rsplit(".", maxsplit=1)[-1]
    return tail[:18]


def _short_event_id(event_id: str) -> str:
    if len(event_id) <= 16:
        return event_id
    return f"{event_id[:8]}...{event_id[-5:]}"


def _css_token(value: str) -> str:
    return "".join(
        character if character.isalnum() or character in {"_", "-"} else "_" for character in value
    )


def _parent_event_id(event: TimelineEvent) -> str | None:
    causality = event.event.get("causality")
    if not isinstance(causality, dict):
        return None
    parent = causality.get("parent_event_id")
    return parent if isinstance(parent, str) else None


def _payload(event: TimelineEvent) -> dict[str, Any]:
    payload = event.event.get("payload")
    return payload if isinstance(payload, dict) else {}


def _evidence_link(event: TimelineEvent) -> dict[str, Any] | None:
    link = _payload(event).get("evidence_link")
    if not isinstance(link, dict):
        return None
    return cast(dict[str, Any], link)


def _verification_status(event: TimelineEvent) -> str:
    if event.verification_status:
        return event.verification_status
    link = _evidence_link(event)
    if link is not None and isinstance(link.get("verification_status"), str):
        return cast(str, link["verification_status"])
    payload = _payload(event)
    status = payload.get("verification_status")
    return status if isinstance(status, str) else "unknown"


def _status_counts(events: tuple[TimelineEvent, ...]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for event in events:
        status = _verification_status(event)
        counts[status] = counts.get(status, 0) + 1
    return counts
