#!/usr/bin/env python3
"""Generate a deterministic SVG map from the local demo incident export."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from html import escape
from pathlib import Path
from typing import Any, cast

EVIDENCE_MAP_FORMAT = "actionlineage.dev/demo-evidence-map-v0"
STATUS_ORDER = ("verified", "observed", "unverified", "conflicting", "not_dispatched")
STATUS_COLORS = {
    "verified": "#15803d",
    "observed": "#2563eb",
    "unverified": "#a16207",
    "conflicting": "#be123c",
    "not_dispatched": "#475569",
}
FONT = 'font-family="Arial, sans-serif"'


def build_evidence_map(incident_path: Path) -> dict[str, Any]:
    """Build a deterministic evidence-map summary from a demo incident export."""

    incident_path = Path(incident_path)
    incident = _load_incident(incident_path)
    events = _object_list(incident.get("events"), field="events")
    summary = _object(incident.get("summary"), field="summary")
    selector = _object(incident.get("selector"), field="selector")

    event_type_counts = Counter(_string(event.get("event_type")) for event in events)
    status_counts = _verification_status_counts(summary)
    not_dispatched_ids = tuple(
        _string(event.get("event_id"))
        for event in events
        if event.get("event_type") == "tool.execution.not_dispatched"
    )
    acknowledged_ids = tuple(
        _string(event.get("event_id"))
        for event in events
        if event.get("event_type") == "tool.execution.acknowledged"
    )
    status_counts["not_dispatched"] = len(not_dispatched_ids)
    evidence_links = _object_list(summary.get("evidence_links", ()), field="summary.evidence_links")
    evidence_status_counts = Counter(
        _string(link.get("verification_status")) for link in evidence_links
    )
    checks = {
        "has_acknowledged_tool_execution": bool(acknowledged_ids),
        "has_verified_evidence_link": evidence_status_counts["verified"] > 0,
        "has_unverified_evidence_link": evidence_status_counts["unverified"] > 0,
        "has_conflicting_evidence_link": evidence_status_counts["conflicting"] > 0,
        "has_not_dispatched_event": bool(not_dispatched_ids),
        "has_named_limitations": bool(summary.get("limitations")),
        "keeps_acknowledgement_distinct": bool(
            acknowledged_ids and evidence_status_counts["unverified"] > 0
        ),
    }
    missing_checks = tuple(name for name, ok in checks.items() if not ok)
    first_event = events[0] if events else {}
    correlation = _object(first_event.get("correlation", {}), field="events[0].correlation")

    return {
        "map_format": EVIDENCE_MAP_FORMAT,
        "ok": not missing_checks,
        "source": {
            "artifact": "incident.json",
            "sha256": _sha256_file(incident_path),
        },
        "selector": selector,
        "trace_id": correlation.get("trace_id"),
        "run_id": correlation.get("run_id"),
        "event_count": int(incident.get("event_count", len(events))),
        "event_type_counts": dict(sorted(event_type_counts.items())),
        "verification_status_counts": {
            status: status_counts.get(status, 0) for status in STATUS_ORDER
        },
        "evidence_link_counts": dict(sorted(evidence_status_counts.items())),
        "key_event_ids": {
            "acknowledged": list(acknowledged_ids),
            "not_dispatched": list(not_dispatched_ids),
            "conflicting": list(_string_list(summary.get("conflicting_event_ids", ()))),
            "unknown": list(_string_list(summary.get("unknown_event_ids", ()))),
        },
        "principals": list(_string_list(summary.get("principals", ()))),
        "tools": list(_string_list(summary.get("tools", ()))),
        "resources": list(_string_list(summary.get("resources", ()))),
        "limitations": list(_string_list(summary.get("limitations", ()))),
        "claims_language": _string(summary.get("claims_language")),
        "checks": checks,
        "missing_checks": list(missing_checks),
    }


def render_svg(evidence_map: dict[str, Any]) -> str:
    """Render a deterministic, dependency-free SVG from an evidence map."""

    status_counts = cast(dict[str, int], evidence_map["verification_status_counts"])
    event_type_counts = cast(dict[str, int], evidence_map["event_type_counts"])
    tools = cast(list[str], evidence_map["tools"])
    limitations = cast(list[str], evidence_map["limitations"])
    cards = "\n".join(
        _status_card(status, status_counts.get(status, 0), index)
        for index, status in enumerate(STATUS_ORDER)
    )
    lifecycle = "\n".join(
        _lifecycle_node(label, event_type_counts.get(event_type, 0), index)
        for index, (label, event_type) in enumerate(
            (
                ("Intent", "agent.intent.recorded"),
                ("Requested", "tool.execution.requested"),
                ("Dispatched", "tool.execution.dispatched"),
                ("Acknowledged", "tool.execution.acknowledged"),
                ("Observed", "side_effect.observed"),
                ("Verified", "side_effect.verified"),
            )
        )
    )
    arrows = "\n".join(_arrow(128 + index * 172, 350) for index in range(5))
    not_dispatched = event_type_counts.get("tool.execution.not_dispatched", 0)
    trace_id = _string(evidence_map.get("trace_id"))
    event_count = int(evidence_map.get("event_count", 0))
    ok_label = "complete" if evidence_map.get("ok") else "incomplete"
    tool_line = ", ".join(tools[:4]) if tools else "none recorded"
    limitation_line = limitations[0] if limitations else "No limitations recorded."
    svg_open = (
        '<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="720" '
        'viewBox="0 0 1200 720" role="img" aria-labelledby="title desc">'
    )
    lines = [
        svg_open,
        '  <title id="title">ActionLineage demo evidence map</title>',
        (
            '  <desc id="desc">Deterministic visual summary generated from the local '
            "demo incident export.</desc>"
        ),
        _rect(0, 0, 1200, 720, fill="#f8fafc"),
        _rect(32, 28, 1136, 664, fill="#ffffff", stroke="#cbd5e1"),
        _text(64, 78, 30, "#0f172a", "ActionLineage demo evidence map", weight="700"),
        _text(
            64,
            108,
            15,
            "#475569",
            "Generated from incident.json; canonical evidence remains evidence.jsonl.",
        ),
        _text(64, 138, 13, "#64748b", f"trace={trace_id} | events={event_count}"),
        _text(64, 160, 13, "#64748b", f"checks={ok_label}"),
        cards,
        _text(64, 288, 18, "#0f172a", "Lifecycle path", weight="700"),
        arrows,
        lifecycle,
        _rect(930, 316, 174, 82, fill="#f8fafc", stroke="#94a3b8"),
        _text(950, 346, 15, "#0f172a", "Not dispatched", weight="700"),
        _text(950, 374, 24, "#475569", str(not_dispatched), weight="700"),
        _text(64, 500, 18, "#0f172a", "Review cues", weight="700"),
        _text(64, 532, 15, "#334155", "Tool acknowledgement is not side-effect evidence."),
        _text(64, 560, 15, "#334155", f"Tools: {tool_line}"),
        _text(64, 588, 15, "#334155", f"Limitation: {limitation_line}"),
        _text(
            64,
            650,
            12,
            "#64748b",
            "This SVG is an onboarding aid, not a canonical evidence store.",
        ),
        "</svg>",
    ]
    return "\n".join(lines) + "\n"


def write_evidence_map(
    incident_path: Path, output_path: Path, summary_path: Path
) -> dict[str, Any]:
    """Write the SVG and JSON evidence-map artifacts."""

    evidence_map = build_evidence_map(incident_path)
    svg = render_svg(evidence_map)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(svg, encoding="utf-8")
    summary_path.write_text(
        json.dumps(evidence_map, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return evidence_map


def check_evidence_map(incident_path: Path, output_path: Path, summary_path: Path) -> list[str]:
    """Return mismatch labels for stale or missing evidence-map artifacts."""

    evidence_map = build_evidence_map(incident_path)
    expected_svg = render_svg(evidence_map)
    expected_summary = json.dumps(evidence_map, indent=2, sort_keys=True) + "\n"
    mismatches: list[str] = []
    if not output_path.exists():
        mismatches.append("svg_missing")
    elif output_path.read_text(encoding="utf-8") != expected_svg:
        mismatches.append("svg_stale")
    if not summary_path.exists():
        mismatches.append("summary_missing")
    elif summary_path.read_text(encoding="utf-8") != expected_summary:
        mismatches.append("summary_stale")
    if evidence_map["missing_checks"]:
        mismatches.append("demo_evidence_incomplete")
    return mismatches


def main() -> int:
    """Run the evidence-map generator."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--demo-dir", type=Path, default=Path("build/actionlineage-demo"))
    parser.add_argument("--incident", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--summary-output", type=Path)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()

    incident_path = args.incident or args.demo_dir / "incident.json"
    output_path = args.output or args.demo_dir / "demo-evidence-map.svg"
    summary_path = args.summary_output or args.demo_dir / "demo-evidence-map.json"
    if args.check:
        mismatches = check_evidence_map(incident_path, output_path, summary_path)
        print(
            json.dumps(
                {
                    "ok": not mismatches,
                    "incident": str(incident_path),
                    "output": str(output_path),
                    "summary_output": str(summary_path),
                    "mismatches": mismatches,
                },
                sort_keys=True,
            )
        )
        return 0 if not mismatches else 1

    evidence_map = write_evidence_map(incident_path, output_path, summary_path)
    print(
        json.dumps(
            {
                "ok": evidence_map["ok"],
                "incident": str(incident_path),
                "output": str(output_path),
                "summary_output": str(summary_path),
                "event_count": evidence_map["event_count"],
                "missing_checks": evidence_map["missing_checks"],
            },
            sort_keys=True,
        )
    )
    return 0 if evidence_map["ok"] else 1


def _status_card(status: str, count: int, index: int) -> str:
    x = 64 + index * 216
    color = STATUS_COLORS[status]
    label = status.replace("_", " ").title()
    return "\n".join(
        (
            _rect(x, 176, 178, 74, fill="#f8fafc", stroke=color, stroke_width=2),
            _text(x + 18, 207, 14, color, label, weight="700"),
            _text(x + 18, 234, 25, "#0f172a", str(count), weight="700"),
        )
    )


def _lifecycle_node(label: str, count: int, index: int) -> str:
    x = 64 + index * 172
    return "\n".join(
        (
            _rect(x, 322, 128, 70, fill="#eef2ff", stroke="#6366f1"),
            _text(x + 16, 352, 14, "#312e81", label, weight="700"),
            _text(x + 16, 376, 22, "#0f172a", str(count), weight="700"),
        )
    )


def _arrow(x: int, y: int) -> str:
    return f"""  <line x1="{x}" y1="{y}" x2="{x + 44}" y2="{y}" stroke="#94a3b8" stroke-width="2"/>
  <path d="M {x + 44} {y} l -8 -5 v 10 z" fill="#94a3b8"/>"""


def _rect(
    x: int,
    y: int,
    width: int,
    height: int,
    *,
    fill: str,
    stroke: str | None = None,
    stroke_width: int = 1,
) -> str:
    stroke_attrs = "" if stroke is None else f' stroke="{stroke}" stroke-width="{stroke_width}"'
    return (
        f'  <rect x="{x}" y="{y}" width="{width}" height="{height}" '
        f'rx="8" fill="{fill}"{stroke_attrs}/>'
    )


def _text(
    x: int,
    y: int,
    size: int,
    fill: str,
    content: str,
    *,
    weight: str | None = None,
) -> str:
    weight_attr = "" if weight is None else f' font-weight="{weight}"'
    return (
        f'  <text x="{x}" y="{y}" {FONT} font-size="{size}"'
        f'{weight_attr} fill="{fill}">{escape(content)}</text>'
    )


def _load_incident(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"incident export is not valid JSON: {path}") from exc
    return _object(data, field="incident")


def _object(value: object, *, field: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{field} must be an object")
    return cast(dict[str, Any], value)


def _object_list(value: object, *, field: str) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        raise ValueError(f"{field} must be a list")
    result: list[dict[str, Any]] = []
    for index, item in enumerate(value):
        result.append(_object(item, field=f"{field}[{index}]"))
    return result


def _verification_status_counts(summary: dict[str, Any]) -> dict[str, int]:
    raw_counts = summary.get("verification_statuses", {})
    if not isinstance(raw_counts, dict):
        raise ValueError("summary.verification_statuses must be an object")
    return {str(status): int(count) for status, count in raw_counts.items()}


def _string(value: object) -> str:
    return value if isinstance(value, str) else ""


def _string_list(value: object) -> tuple[str, ...]:
    if not isinstance(value, list):
        return ()
    return tuple(item for item in value if isinstance(item, str))


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return f"sha256:{digest.hexdigest()}"


if __name__ == "__main__":
    raise SystemExit(main())
