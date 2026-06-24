"""SQLite projection rebuilt from verified journal events."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import sqlite3
from collections.abc import Iterable, Iterator, Mapping
from contextlib import contextmanager, suppress
from copy import deepcopy
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any, cast
from uuid import uuid4

from actionlineage.domain import (
    CANONICALIZATION_VERSION,
    EventEnvelope,
    deterministic_json_bytes,
    event_to_dict,
    serialize_event,
)
from actionlineage.domain.events import event_type_value
from actionlineage.errors import safe_error_detail
from actionlineage.journal import (
    JOURNAL_SOURCE_IDENTITY_VERSION,
    VerificationResult,
    VerifiedJournalSnapshot,
    journal_source_identity,
    verified_journal_snapshot,
)

PROJECTION_SCHEMA_VERSION = 2
INCIDENT_EXPORT_VERSION = "actionlineage.dev/incident-export-v0"
CASE_BUNDLE_VERSION = "actionlineage.dev/case-bundle-v0"
CASE_BUNDLE_MANIFEST_VERSION = "actionlineage.dev/case-bundle-manifest-v0"
GROUNDED_SUMMARY_VERSION = "actionlineage.dev/grounded-summary-v0"
INVESTIGATION_GRAPH_VERSION = "actionlineage.dev/investigation-graph-v0"
TIMELINE_ORDER_DESCRIPTION = "occurred_at, causality.sequence, journal_record_number, event_id"
CASE_BUNDLE_FILENAMES = ("case.json", "events.ndjson", "report.md")
CASE_BUNDLE_MANIFEST_FILENAME = "manifest.json"
PROJECTED_EVENT_COLUMNS = (
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
)
TIMELINE_SELECT_COLUMNS = (
    "journal_record_number",
    "event_id",
    "event_type",
    "occurred_at",
    "observed_at",
    "trace_id",
    "run_id",
    "sequence",
    "event_hash",
    "verification_status",
    "evidence_subject_event_id",
    "evidence_event_id",
    "event_json",
)


class ProjectionError(RuntimeError):
    """Base exception for projection failures."""


class ProjectionSchemaError(ProjectionError):
    """Raised when a projection database has an unsupported schema."""


class ProjectionIndexError(ProjectionError):
    """Raised when an event cannot be safely indexed."""


class ProjectionQueryError(ProjectionError):
    """Raised when a timeline query is invalid or cannot run."""


class ProjectionRebuildError(ProjectionError):
    """Raised when a projection rebuild cannot complete."""


class ProjectionVerificationError(ProjectionRebuildError):
    """Raised when the source journal fails verification before rebuild."""

    def __init__(self, journal_path: Path, verification: VerificationResult) -> None:
        super().__init__("cannot rebuild projection from a journal that fails verification")
        self.journal_path = journal_path
        self.verification = verification


class ProjectionStateCode(StrEnum):
    """Projection correspondence states used by reads and health checks."""

    HEALTHY = "healthy"
    JOURNAL_INVALID = "journal_invalid"
    PROJECTION_MISSING = "projection_missing"
    PROJECTION_UNAVAILABLE = "projection_unavailable"
    PROJECTION_STALE = "projection_stale"
    PROJECTION_MISMATCH = "projection_mismatch"
    PROJECTION_REBUILD_REQUIRED = "projection_rebuild_required"


class ProjectionStateError(ProjectionQueryError):
    """Raised when a projection is not bound to the verified journal state."""

    def __init__(
        self,
        code: ProjectionStateCode,
        message: str,
        *,
        details: dict[str, object] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.details = details or {}


@dataclass(frozen=True, slots=True)
class RebuildResult:
    """Machine-readable projection rebuild result."""

    journal_path: Path
    database_path: Path
    records_indexed: int
    last_event_hash: str | None
    schema_version: int = PROJECTION_SCHEMA_VERSION

    def as_dict(self) -> dict[str, object]:
        """Return a JSON-compatible result object."""

        return {
            "ok": True,
            "journal_path": str(self.journal_path),
            "database_path": str(self.database_path),
            "records_indexed": self.records_indexed,
            "last_event_hash": self.last_event_hash,
            "schema_version": self.schema_version,
        }


@dataclass(frozen=True, slots=True)
class VerifiedProjectionSnapshot:
    """Projection state proven to correspond to one verified journal snapshot."""

    journal_path: Path
    database_path: Path
    journal_snapshot: VerifiedJournalSnapshot
    records_indexed: int
    last_event_hash: str | None
    source_journal_path: str
    source_journal_identity: str
    source_journal_sha256: str | None
    projection_identity: str
    schema_version: int = PROJECTION_SCHEMA_VERSION
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
        """Return a JSON-compatible projection verification summary."""

        return {
            "ok": True,
            "state": self.state.value,
            "journal_path": str(self.journal_path),
            "database_path": str(self.database_path),
            "source_journal_path": self.source_journal_path,
            "source_journal_identity": self.source_journal_identity,
            "source_journal_sha256": self.source_journal_sha256,
            "projection_identity": self.projection_identity,
            "records_indexed": self.records_indexed,
            "record_count": self.record_count,
            "last_event_hash": self.last_event_hash,
            "terminal_hash": self.terminal_hash,
            "schema_version": self.schema_version,
            "journal": self.journal_snapshot.as_dict(),
        }


@dataclass(frozen=True, slots=True)
class TimelineEvent:
    """One event returned from the projection timeline."""

    journal_record_number: int
    event_id: str
    event_type: str
    occurred_at: str
    observed_at: str
    trace_id: str
    run_id: str
    sequence: int
    event_hash: str
    verification_status: str | None
    evidence_subject_event_id: str | None
    evidence_event_id: str | None
    event: dict[str, Any]

    def as_dict(self) -> dict[str, object]:
        """Return a JSON-compatible result object."""

        return {
            "journal_record_number": self.journal_record_number,
            "event_id": self.event_id,
            "event_type": self.event_type,
            "occurred_at": self.occurred_at,
            "observed_at": self.observed_at,
            "trace_id": self.trace_id,
            "run_id": self.run_id,
            "sequence": self.sequence,
            "event_hash": self.event_hash,
            "verification_status": self.verification_status,
            "evidence_subject_event_id": self.evidence_subject_event_id,
            "evidence_event_id": self.evidence_event_id,
            "event": deepcopy(self.event),
        }


@dataclass(frozen=True, slots=True)
class TimelineResult:
    """Timeline query result ordered for incident review."""

    selector_type: str
    selector_value: str
    events: tuple[TimelineEvent, ...]
    verification: VerifiedProjectionSnapshot | None = None
    order: str = TIMELINE_ORDER_DESCRIPTION

    def as_dict(self) -> dict[str, object]:
        """Return a JSON-compatible result object."""

        result: dict[str, object] = {
            "ok": True,
            "selector": {
                "type": self.selector_type,
                "value": self.selector_value,
            },
            "event_count": len(self.events),
            "order": self.order,
            "events": [event.as_dict() for event in self.events],
        }
        if self.verification is not None:
            result["verification"] = self.verification.as_dict()
        return result


@dataclass(frozen=True, slots=True)
class IncidentExport:
    """Machine-readable incident export derived from a projected timeline."""

    timeline: TimelineResult
    export_version: str = INCIDENT_EXPORT_VERSION

    def as_dict(self) -> dict[str, object]:
        """Return a JSON-compatible incident export object."""

        events = [deepcopy(event.event) for event in self.timeline.events]
        result: dict[str, object] = {
            "export_version": self.export_version,
            "selector": {
                "type": self.timeline.selector_type,
                "value": self.timeline.selector_value,
            },
            "event_count": len(self.timeline.events),
            "summary": _incident_summary(events),
            "timeline_order": self.timeline.order,
            "events": events,
        }
        if self.timeline.verification is not None:
            result["verification"] = self.timeline.verification.as_dict()
        return result


@dataclass(frozen=True, slots=True)
class EventExplanation:
    """Causal and evidence context for one projected event."""

    event_id: str
    event: dict[str, Any]
    parent_event_id: str | None
    child_event_ids: tuple[str, ...]
    evidence_links_as_subject: tuple[dict[str, Any], ...]
    evidence_links_as_evidence: tuple[dict[str, Any], ...]

    def as_dict(self) -> dict[str, object]:
        """Return a JSON-compatible event explanation."""

        return {
            "ok": True,
            "event_id": self.event_id,
            "event": deepcopy(self.event),
            "parent_event_id": self.parent_event_id,
            "child_event_ids": list(self.child_event_ids),
            "evidence_links_as_subject": deepcopy(list(self.evidence_links_as_subject)),
            "evidence_links_as_evidence": deepcopy(list(self.evidence_links_as_evidence)),
        }


@dataclass(frozen=True, slots=True)
class CaseBundleExport:
    """Files produced for one investigation case bundle."""

    output_dir: Path
    json_path: Path
    ndjson_path: Path
    markdown_path: Path
    manifest_path: Path
    incident: IncidentExport
    bundle_version: str = CASE_BUNDLE_VERSION

    def as_dict(self) -> dict[str, object]:
        """Return a JSON-compatible case export result."""

        return {
            "ok": True,
            "bundle_version": self.bundle_version,
            "output_dir": str(self.output_dir),
            "json_path": str(self.json_path),
            "ndjson_path": str(self.ndjson_path),
            "markdown_path": str(self.markdown_path),
            "manifest_path": str(self.manifest_path),
            "incident": self.incident.as_dict(),
        }


@dataclass(frozen=True, slots=True)
class GroundedInvestigationSummary:
    """Deterministic narrative derived only from projected evidence."""

    selector: dict[str, object]
    headline: str
    key_findings: tuple[str, ...]
    limitations: tuple[str, ...]
    grounded_event_ids: tuple[str, ...]
    summary_version: str = GROUNDED_SUMMARY_VERSION
    model_provider: None = None

    def as_dict(self) -> dict[str, object]:
        """Return a JSON-compatible grounded summary."""

        return {
            "summary_version": self.summary_version,
            "model_provider": self.model_provider,
            "selector": deepcopy(self.selector),
            "headline": self.headline,
            "key_findings": list(self.key_findings),
            "limitations": list(self.limitations),
            "grounded_event_ids": list(self.grounded_event_ids),
            "canonical_source": "append-only local journal",
        }


@dataclass(frozen=True, slots=True)
class InvestigationGraphNode:
    """One node in an investigation graph export."""

    node_id: str
    kind: str
    label: str
    attributes: dict[str, object]

    def as_dict(self) -> dict[str, object]:
        """Return a JSON-compatible graph node."""

        return {
            "id": self.node_id,
            "kind": self.kind,
            "label": self.label,
            "attributes": deepcopy(self.attributes),
        }


@dataclass(frozen=True, slots=True)
class InvestigationGraphEdge:
    """One edge in an investigation graph export."""

    edge_id: str
    source: str
    target: str
    relationship: str
    attributes: dict[str, object]

    def as_dict(self) -> dict[str, object]:
        """Return a JSON-compatible graph edge."""

        return {
            "id": self.edge_id,
            "source": self.source,
            "target": self.target,
            "relationship": self.relationship,
            "attributes": deepcopy(self.attributes),
        }


@dataclass(frozen=True, slots=True)
class InvestigationGraphExport:
    """Dependency-free graph representation for incident investigation."""

    selector: dict[str, object]
    nodes: tuple[InvestigationGraphNode, ...]
    edges: tuple[InvestigationGraphEdge, ...]
    graph_version: str = INVESTIGATION_GRAPH_VERSION

    def as_dict(self) -> dict[str, object]:
        """Return a JSON-compatible investigation graph."""

        return {
            "graph_version": self.graph_version,
            "selector": deepcopy(self.selector),
            "node_count": len(self.nodes),
            "edge_count": len(self.edges),
            "nodes": [node.as_dict() for node in self.nodes],
            "edges": [edge.as_dict() for edge in self.edges],
            "canonical_source": "append-only local journal",
            "limitations": [
                "Graph nodes and edges are derived from redacted projected evidence.",
                "No observation recorded is not proof that a side effect did not occur.",
            ],
        }


@dataclass(frozen=True, slots=True)
class _VerifiedProjectionReader:
    connection: sqlite3.Connection
    verification: VerifiedProjectionSnapshot


def rebuild_projection(journal_path: Path, database_path: Path) -> RebuildResult:
    """Rebuild the SQLite projection from a verified local journal."""

    journal_path = _normalize_journal_path(Path(journal_path))
    database_path = Path(database_path)
    snapshot = verified_journal_snapshot(journal_path)
    if not snapshot.ok:
        raise ProjectionVerificationError(journal_path, snapshot.verification)

    _prepare_projection_path(database_path)
    indexed_count = 0

    try:
        with _connect(database_path) as connection:
            ensure_schema(connection)
            connection.execute("DELETE FROM events")
            for record_number, event in enumerate(snapshot.events, start=1):
                index_event(connection, event, journal_record_number=record_number)
                indexed_count += 1

            if indexed_count != snapshot.record_count:
                raise ProjectionRebuildError(
                    "indexed record count does not match verified journal snapshot"
                )

            _set_metadata(
                connection,
                {
                    "schema_version": str(PROJECTION_SCHEMA_VERSION),
                    "source_journal_path": str(journal_path),
                    "source_journal_identity": journal_source_identity(snapshot),
                    "source_journal_identity_version": JOURNAL_SOURCE_IDENTITY_VERSION,
                    "source_journal_sha256": snapshot.journal_sha256 or "",
                    "projection_identity": _projection_identity(database_path),
                    "records_indexed": str(indexed_count),
                    "last_event_hash": snapshot.terminal_hash or "",
                },
            )
    except sqlite3.Error as exc:
        raise ProjectionRebuildError("sqlite projection rebuild failed") from exc

    return RebuildResult(
        journal_path=journal_path,
        database_path=database_path,
        records_indexed=indexed_count,
        last_event_hash=snapshot.terminal_hash,
    )


def verify_projection_state(
    database_path: Path,
    *,
    journal_path: Path,
) -> VerifiedProjectionSnapshot:
    """Verify that a projection exactly matches a verified journal snapshot."""

    database_path = Path(database_path)
    if not database_path.exists():
        raise ProjectionStateError(
            ProjectionStateCode.PROJECTION_MISSING,
            f"projection database does not exist: {database_path}",
        )

    with _verified_projection_reader(database_path, journal_path=journal_path) as reader:
        return reader.verification


def index_event(
    connection: sqlite3.Connection,
    event: EventEnvelope,
    *,
    journal_record_number: int,
) -> bool:
    """Idempotently index one verified journal event.

    Returns true when a new row was inserted and false when the same event was
    already present. A duplicate event ID with different projected bytes fails
    visibly instead of overwriting earlier evidence.
    """

    if event.integrity.event_hash is None:
        raise ProjectionIndexError("cannot index event without integrity.event_hash")

    values = _event_projection_values(event, journal_record_number=journal_record_number)
    existing = connection.execute(
        "SELECT journal_record_number, event_json FROM events WHERE event_id = ?",
        (event.event_id,),
    ).fetchone()

    if existing is not None:
        existing_record_number = cast(int, existing[0])
        existing_event_json = cast(str, existing[1])
        if existing_record_number == journal_record_number and existing_event_json == values[-1]:
            return False
        raise ProjectionIndexError(
            f"event_id already indexed with different content: {event.event_id}"
        )

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
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        values,
    )
    return True


def query_timeline(
    database_path: Path,
    *,
    journal_path: Path,
    trace_id: str | None = None,
    run_id: str | None = None,
) -> TimelineResult:
    """Query a timeline by trace ID or run ID."""

    selector_type, selector_value = _require_one_selector(trace_id=trace_id, run_id=run_id)
    database_path = Path(database_path)

    try:
        with _verified_projection_reader(database_path, journal_path=journal_path) as reader:
            if selector_type == "trace_id":
                rows = reader.connection.execute(
                    """
                    SELECT journal_record_number, event_id, event_type, occurred_at,
                           observed_at, trace_id, run_id, sequence, event_hash,
                           verification_status, evidence_subject_event_id,
                           evidence_event_id, event_json
                    FROM events
                    WHERE trace_id = ?
                    ORDER BY occurred_at ASC,
                             sequence ASC,
                             journal_record_number ASC,
                             event_id ASC
                    """,
                    (selector_value,),
                ).fetchall()
            else:
                rows = reader.connection.execute(
                    """
                    SELECT journal_record_number, event_id, event_type, occurred_at,
                           observed_at, trace_id, run_id, sequence, event_hash,
                           verification_status, evidence_subject_event_id,
                           evidence_event_id, event_json
                    FROM events
                    WHERE run_id = ?
                    ORDER BY occurred_at ASC,
                             sequence ASC,
                             journal_record_number ASC,
                             event_id ASC
                    """,
                    (selector_value,),
                ).fetchall()
            events = tuple(_timeline_event_from_row(row) for row in rows)
    except sqlite3.Error as exc:
        raise ProjectionQueryError("sqlite projection query failed") from exc

    return TimelineResult(
        selector_type=selector_type,
        selector_value=selector_value,
        events=events,
        verification=reader.verification,
    )


def query_filtered_timeline(
    database_path: Path,
    *,
    journal_path: Path,
    trace_id: str | None = None,
    run_id: str | None = None,
    event_type: str | None = None,
    principal_id: str | None = None,
    tool_name: str | None = None,
    resource: str | None = None,
    verification_status: str | None = None,
    sensitivity: str | None = None,
    trust: str | None = None,
    descriptor_hash: str | None = None,
) -> TimelineResult:
    """Query projected events with investigation filters."""

    database_path = Path(database_path)

    try:
        with _verified_projection_reader(database_path, journal_path=journal_path) as reader:
            rows = reader.connection.execute(
                """
                SELECT journal_record_number, event_id, event_type, occurred_at,
                       observed_at, trace_id, run_id, sequence, event_hash,
                       verification_status, evidence_subject_event_id,
                       evidence_event_id, event_json
                FROM events
                ORDER BY occurred_at ASC,
                         sequence ASC,
                         journal_record_number ASC,
                         event_id ASC
                """
            ).fetchall()
            verification = reader.verification
    except sqlite3.Error as exc:
        raise ProjectionQueryError("sqlite projection query failed") from exc

    filters = {
        "descriptor_hash": descriptor_hash,
        "event_type": event_type,
        "principal_id": principal_id,
        "resource": resource,
        "run_id": run_id,
        "sensitivity": sensitivity,
        "tool_name": tool_name,
        "trace_id": trace_id,
        "trust": trust,
        "verification_status": verification_status,
    }
    events = tuple(
        event
        for event in (_timeline_event_from_row(row) for row in rows)
        if _timeline_event_matches(event, filters)
    )
    selector_value = json.dumps(
        {key: value for key, value in filters.items() if value is not None},
        sort_keys=True,
    )
    return TimelineResult(
        selector_type="filters",
        selector_value=selector_value,
        events=events,
        verification=verification,
    )


def export_incident(
    database_path: Path,
    *,
    journal_path: Path,
    trace_id: str | None = None,
    run_id: str | None = None,
) -> IncidentExport:
    """Export a projected timeline as machine-readable incident JSON."""

    return IncidentExport(
        timeline=query_timeline(
            database_path,
            journal_path=journal_path,
            trace_id=trace_id,
            run_id=run_id,
        )
    )


def summarize_incident(
    database_path: Path,
    *,
    journal_path: Path,
    trace_id: str | None = None,
    run_id: str | None = None,
) -> GroundedInvestigationSummary:
    """Generate a deterministic summary grounded in a projected incident export."""

    return grounded_summary_from_incident(
        export_incident(
            database_path,
            journal_path=journal_path,
            trace_id=trace_id,
            run_id=run_id,
        )
    )


def export_investigation_graph(
    database_path: Path,
    *,
    journal_path: Path,
    trace_id: str | None = None,
    run_id: str | None = None,
) -> InvestigationGraphExport:
    """Export a dependency-free graph derived from a projected incident."""

    return investigation_graph_from_incident(
        export_incident(
            database_path,
            journal_path=journal_path,
            trace_id=trace_id,
            run_id=run_id,
        )
    )


def investigation_graph_from_incident(incident: IncidentExport) -> InvestigationGraphExport:
    """Build an investigation graph from an incident export object."""

    incident_data = incident.as_dict()
    selector = cast(dict[str, object], incident_data["selector"])
    events = cast(list[dict[str, Any]], incident_data["events"])
    event_ids = {cast(str, event["event_id"]) for event in events}
    nodes: dict[str, InvestigationGraphNode] = {}
    edges: dict[str, InvestigationGraphEdge] = {}

    for event in events:
        event_id = cast(str, event["event_id"])
        event_node_id = _event_node_id(event_id)
        payload_status = _verification_status(event)
        event_attributes: dict[str, object] = {
            "event_id": event_id,
            "event_type": cast(str, event["event_type"]),
            "occurred_at": cast(str, event["occurred_at"]),
            "sequence": cast(dict[str, object], event["causality"])["sequence"],
        }
        if payload_status is not None:
            event_attributes["verification_status"] = payload_status
        nodes[event_node_id] = InvestigationGraphNode(
            node_id=event_node_id,
            kind="event",
            label=cast(str, event["event_type"]),
            attributes=event_attributes,
        )

        parent_event_id = _parent_event_id(event)
        if parent_event_id is not None:
            _ensure_event_reference_node(nodes, parent_event_id, event_ids=event_ids)
            _add_edge(
                edges,
                source=_event_node_id(parent_event_id),
                target=event_node_id,
                relationship="causal_parent",
                attributes={},
            )

        principal_id = _principal_id(event)
        if principal_id is not None:
            principal_node_id = _entity_node_id("principal", principal_id)
            nodes.setdefault(
                principal_node_id,
                InvestigationGraphNode(
                    node_id=principal_node_id,
                    kind="principal",
                    label=principal_id,
                    attributes={"principal_id": principal_id},
                ),
            )
            _add_edge(
                edges,
                source=event_node_id,
                target=principal_node_id,
                relationship="performed_by",
                attributes={},
            )

        for tool_name in _tool_names(event):
            tool_node_id = _entity_node_id("tool", tool_name)
            nodes.setdefault(
                tool_node_id,
                InvestigationGraphNode(
                    node_id=tool_node_id,
                    kind="tool",
                    label=tool_name,
                    attributes={"name": tool_name},
                ),
            )
            _add_edge(
                edges,
                source=event_node_id,
                target=tool_node_id,
                relationship="uses_tool",
                attributes={},
            )

        for resource in _resource_identifiers(event):
            resource_node_id = _entity_node_id("resource", resource)
            nodes.setdefault(
                resource_node_id,
                InvestigationGraphNode(
                    node_id=resource_node_id,
                    kind="resource",
                    label=resource,
                    attributes={"identifier": resource},
                ),
            )
            _add_edge(
                edges,
                source=event_node_id,
                target=resource_node_id,
                relationship="references_resource",
                attributes={},
            )

        if payload_status is not None:
            status_node_id = _entity_node_id("verification_status", payload_status)
            nodes.setdefault(
                status_node_id,
                InvestigationGraphNode(
                    node_id=status_node_id,
                    kind="verification_status",
                    label=payload_status,
                    attributes={"status": payload_status},
                ),
            )
            _add_edge(
                edges,
                source=event_node_id,
                target=status_node_id,
                relationship="has_verification_status",
                attributes={},
            )

    for link in _evidence_links_from_event_objects(events):
        subject_event_id = _string_or_none(link.get("subject_event_id"))
        evidence_event_id = _string_or_none(link.get("evidence_event_id"))
        if subject_event_id is None or evidence_event_id is None:
            continue
        _ensure_event_reference_node(nodes, subject_event_id, event_ids=event_ids)
        _ensure_event_reference_node(nodes, evidence_event_id, event_ids=event_ids)
        relationship = _string_or_none(link.get("relationship")) or "evidence_link"
        _add_edge(
            edges,
            source=_event_node_id(evidence_event_id),
            target=_event_node_id(subject_event_id),
            relationship=f"evidence_link:{relationship}",
            attributes=_evidence_edge_attributes(link),
        )

    return InvestigationGraphExport(
        selector=selector,
        nodes=tuple(nodes[key] for key in sorted(nodes)),
        edges=tuple(edges[key] for key in sorted(edges)),
    )


def grounded_summary_from_incident(
    incident: IncidentExport,
) -> GroundedInvestigationSummary:
    """Generate a deterministic summary from an incident export object."""

    incident_data = incident.as_dict()
    selector = cast(dict[str, object], incident_data["selector"])
    summary = cast(dict[str, object], incident_data["summary"])
    events = cast(list[dict[str, Any]], incident_data["events"])
    event_count = cast(int, incident_data["event_count"])
    statuses = cast(dict[str, int], summary["verification_statuses"])
    evidence_links = cast(list[dict[str, Any]], summary["evidence_links"])
    conflicts = cast(list[str], summary["conflicting_event_ids"])

    verified_count = statuses.get("verified", 0)
    uncertain_count = sum(
        statuses.get(status, 0) for status in ("unknown", "unverified", "timed_out", "conflicting")
    )
    headline = (
        f"{event_count} events for {selector['type']}={selector['value']}; "
        f"{verified_count} verified and {uncertain_count} uncertain outcomes recorded."
    )
    findings = (
        _finding("Principals", cast(list[str], summary["principals"])),
        _finding("Tools", cast(list[str], summary["tools"])),
        _finding("Resources", cast(list[str], summary["resources"])),
        f"Verification statuses: {_format_counts(statuses)}",
        f"Evidence links: {len(evidence_links)}",
        f"Conflicting events: {', '.join(conflicts) if conflicts else 'none recorded'}",
    )
    limitations = (
        *cast(list[str], summary["limitations"]),
        cast(str, summary["claims_language"]),
        "This deterministic summary is derived from projected evidence; "
        "verify against the append-only local journal.",
    )
    return GroundedInvestigationSummary(
        selector=selector,
        headline=headline,
        key_findings=findings,
        limitations=limitations,
        grounded_event_ids=tuple(cast(str, event["event_id"]) for event in events),
    )


def explain_event(
    database_path: Path,
    *,
    event_id: str,
    journal_path: Path,
) -> EventExplanation:
    """Explain one event with causal and evidence-link context."""

    timeline = query_filtered_timeline(database_path, journal_path=journal_path)
    events_by_id = {event.event_id: event.event for event in timeline.events}
    if event_id not in events_by_id:
        raise ProjectionQueryError(f"event does not exist in projection: {event_id}")

    child_event_ids = tuple(
        event.event_id
        for event in timeline.events
        if event.event.get("causality", {}).get("parent_event_id") == event_id
    )
    evidence_links = tuple(_evidence_links(timeline.events))
    parent_event_id = events_by_id[event_id].get("causality", {}).get("parent_event_id")
    return EventExplanation(
        event_id=event_id,
        event=events_by_id[event_id],
        parent_event_id=cast(str | None, parent_event_id),
        child_event_ids=child_event_ids,
        evidence_links_as_subject=tuple(
            link for link in evidence_links if link.get("subject_event_id") == event_id
        ),
        evidence_links_as_evidence=tuple(
            link for link in evidence_links if link.get("evidence_event_id") == event_id
        ),
    )


def export_case_bundle(
    database_path: Path,
    output_dir: Path,
    *,
    journal_path: Path,
    trace_id: str | None = None,
    run_id: str | None = None,
) -> CaseBundleExport:
    """Export JSON, NDJSON, and Markdown case files for one timeline."""

    incident = export_incident(
        database_path,
        journal_path=journal_path,
        trace_id=trace_id,
        run_id=run_id,
    )
    output_dir, staging_dir = _create_case_bundle_staging_dir(Path(output_dir))
    json_path, ndjson_path, markdown_path = _case_bundle_paths(output_dir)
    manifest_path = output_dir / CASE_BUNDLE_MANIFEST_FILENAME

    incident_data = incident.as_dict()
    event_objects = cast(list[object], incident_data["events"])
    artifact_payloads = {
        "case.json": deterministic_json_bytes(cast(dict[str, Any], incident_data)) + b"\n",
        "events.ndjson": b"".join(
            deterministic_json_bytes(cast(dict[str, Any], event)) + b"\n" for event in event_objects
        ),
        "report.md": _case_markdown(incident_data).encode("utf-8"),
    }
    manifest = _case_bundle_manifest(
        incident_data,
        artifact_payloads=artifact_payloads,
        database_path=database_path,
        journal_path=journal_path,
        trace_id=trace_id,
        run_id=run_id,
    )
    all_payloads = {
        **artifact_payloads,
        CASE_BUNDLE_MANIFEST_FILENAME: deterministic_json_bytes(manifest) + b"\n",
    }
    try:
        for filename, payload in all_payloads.items():
            _write_private_case_bundle_file(staging_dir / filename, payload)
        try:
            _fsync_directory(staging_dir)
        except OSError as exc:
            raise ProjectionQueryError("failed to sync case bundle staging directory") from exc
        _publish_case_bundle_directory(staging_dir, output_dir)
    except Exception:
        _cleanup_case_bundle_staging(staging_dir)
        raise

    return CaseBundleExport(
        output_dir=output_dir,
        json_path=json_path,
        ndjson_path=ndjson_path,
        markdown_path=markdown_path,
        manifest_path=manifest_path,
        incident=incident,
    )


def ensure_schema(connection: sqlite3.Connection) -> None:
    """Create or validate the pre-release projection schema."""

    version = _user_version(connection)
    if version == 0:
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS projection_metadata (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS events (
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
                verification_status TEXT,
                evidence_subject_event_id TEXT,
                evidence_event_id TEXT,
                journal_record_number INTEGER NOT NULL UNIQUE,
                event_json TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_events_trace_timeline
                ON events(trace_id, occurred_at, sequence, journal_record_number, event_id);
            CREATE INDEX IF NOT EXISTS idx_events_run_timeline
                ON events(run_id, occurred_at, sequence, journal_record_number, event_id);

            """
        )
        _set_user_version(connection, PROJECTION_SCHEMA_VERSION)
        _set_metadata(connection, {"schema_version": str(PROJECTION_SCHEMA_VERSION)})
        return

    if version == 1:
        _migrate_v1_to_v2(connection)
        return

    if version != PROJECTION_SCHEMA_VERSION:
        raise ProjectionSchemaError(
            f"unsupported projection schema version {version}; expected {PROJECTION_SCHEMA_VERSION}"
        )


def validate_schema(connection: sqlite3.Connection) -> None:
    """Validate the projection schema without mutating database state."""

    version = _user_version(connection)
    if version == 0:
        raise ProjectionSchemaError("projection schema is missing; rebuild required")
    if version != PROJECTION_SCHEMA_VERSION:
        raise ProjectionSchemaError(
            f"unsupported projection schema version {version}; expected {PROJECTION_SCHEMA_VERSION}"
        )

    metadata_columns = {
        cast(str, row[1]) for row in connection.execute("PRAGMA table_info(projection_metadata)")
    }
    if {"key", "value"} - metadata_columns:
        raise ProjectionSchemaError("projection metadata table is missing required columns")

    event_columns = {cast(str, row[1]) for row in connection.execute("PRAGMA table_info(events)")}
    missing_event_columns = set(PROJECTED_EVENT_COLUMNS) - event_columns
    if missing_event_columns:
        missing = ", ".join(sorted(missing_event_columns))
        raise ProjectionSchemaError(f"projection events table is missing columns: {missing}")


@contextmanager
def _verified_projection_reader(
    database_path: Path,
    *,
    journal_path: Path,
) -> Iterator[_VerifiedProjectionReader]:
    database_path = Path(database_path)
    if not database_path.exists():
        raise ProjectionStateError(
            ProjectionStateCode.PROJECTION_MISSING,
            f"projection database does not exist: {database_path}",
        )

    normalized_journal_path = _normalize_journal_path(Path(journal_path))
    with _connect_readonly(database_path) as connection:
        try:
            connection.execute("BEGIN")
            verification = _verify_projection_state_on_connection(
                connection,
                database_path=database_path,
                journal_path=normalized_journal_path,
            )
        except ProjectionStateError:
            raise
        except sqlite3.Error as exc:
            raise ProjectionStateError(
                ProjectionStateCode.PROJECTION_UNAVAILABLE,
                "sqlite projection could not be verified",
                details={"error_type": type(exc).__name__},
            ) from exc
        except ProjectionSchemaError as exc:
            raise ProjectionStateError(
                ProjectionStateCode.PROJECTION_REBUILD_REQUIRED,
                "projection schema is unsupported or incomplete",
                details={"error": safe_error_detail(exc)},
            ) from exc
        except (OSError, ValueError) as exc:
            raise ProjectionStateError(
                ProjectionStateCode.PROJECTION_REBUILD_REQUIRED,
                "projection metadata is incomplete or invalid",
                details={"error": safe_error_detail(exc)},
            ) from exc

        try:
            yield _VerifiedProjectionReader(connection=connection, verification=verification)
        finally:
            with suppress(sqlite3.Error):
                connection.execute("ROLLBACK")

        _recheck_terminal_journal_state(normalized_journal_path, verification)


@contextmanager
def _connect(database_path: Path) -> Iterator[sqlite3.Connection]:
    connection = sqlite3.connect(database_path)
    try:
        connection.execute("PRAGMA foreign_keys = ON")
        with connection:
            yield connection
    finally:
        connection.close()


@contextmanager
def _connect_readonly(database_path: Path) -> Iterator[sqlite3.Connection]:
    uri = f"{Path(database_path).resolve(strict=False).as_uri()}?mode=ro"
    connection = sqlite3.connect(uri, uri=True)
    try:
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA query_only = ON")
        yield connection
    finally:
        connection.close()


def _prepare_projection_path(database_path: Path) -> None:
    database_path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    if os.name != "posix":
        return
    parent_mode = database_path.parent.stat().st_mode & 0o777
    if parent_mode & 0o077:
        raise ProjectionRebuildError(
            f"projection directory is not private: {database_path.parent}; "
            "expected mode 0700 or stricter"
        )
    fd = os.open(
        database_path,
        os.O_RDWR | os.O_CREAT | getattr(os, "O_CLOEXEC", 0),
        0o600,
    )
    try:
        mode = os.fstat(fd).st_mode & 0o777
        if mode & 0o077:
            raise ProjectionRebuildError(
                f"projection file is not private: {database_path}; expected mode 0600 or stricter"
            )
    finally:
        os.close(fd)


def _verify_projection_state_on_connection(
    connection: sqlite3.Connection,
    *,
    database_path: Path,
    journal_path: Path,
) -> VerifiedProjectionSnapshot:
    validate_schema(connection)
    metadata = _get_metadata(connection)
    source_journal_path = _projection_source_path_hint(metadata)

    expected_projection_identity = _projection_identity(database_path)
    stored_projection_identity = metadata.get("projection_identity")
    if not stored_projection_identity:
        raise ValueError("projection metadata is missing projection_identity")
    if stored_projection_identity != expected_projection_identity:
        raise ProjectionStateError(
            ProjectionStateCode.PROJECTION_MISMATCH,
            "projection identity metadata does not match the database being verified",
            details={
                "projection_identity": stored_projection_identity,
                "expected_projection_identity": expected_projection_identity,
            },
        )

    snapshot = verified_journal_snapshot(journal_path)
    if not snapshot.ok:
        raise ProjectionStateError(
            ProjectionStateCode.JOURNAL_INVALID,
            "source journal verification failed",
            details={"verification": snapshot.verification.as_dict()},
        )

    records_indexed = _metadata_int(metadata, "records_indexed")
    last_event_hash = _metadata_hash(metadata, "last_event_hash")
    expected_identity = journal_source_identity(snapshot)
    stored_identity = metadata.get("source_journal_identity")
    if not stored_identity:
        raise ValueError("projection metadata is missing source_journal_identity")
    if stored_identity.startswith("local-file:"):
        raise ProjectionStateError(
            ProjectionStateCode.PROJECTION_REBUILD_REQUIRED,
            "projection uses legacy path-based source journal identity; rebuild required",
            details={
                "source_journal_identity": stored_identity,
                "expected_source_journal_identity": expected_identity,
            },
        )
    stored_identity_version = metadata.get("source_journal_identity_version")
    if stored_identity_version is None:
        raise ValueError("projection metadata is missing source_journal_identity_version")
    if stored_identity_version != JOURNAL_SOURCE_IDENTITY_VERSION:
        raise ProjectionStateError(
            ProjectionStateCode.PROJECTION_REBUILD_REQUIRED,
            "projection source journal identity version is unsupported; rebuild required",
            details={
                "source_journal_identity_version": stored_identity_version,
                "expected_source_journal_identity_version": JOURNAL_SOURCE_IDENTITY_VERSION,
            },
        )
    if stored_identity != expected_identity:
        if _projection_matches_verified_journal_prefix(
            connection,
            snapshot,
            records_indexed=records_indexed,
            last_event_hash=last_event_hash,
        ):
            raise ProjectionStateError(
                ProjectionStateCode.PROJECTION_STALE,
                "projection matches a verified prefix of the source journal; rebuild required",
                details={
                    "records_indexed": records_indexed,
                    "record_count": snapshot.record_count,
                    "last_event_hash": last_event_hash,
                    "terminal_hash": snapshot.terminal_hash,
                },
            )
        raise ProjectionStateError(
            ProjectionStateCode.PROJECTION_MISMATCH,
            "projection source journal identity does not match the verified journal",
            details={
                "source_journal_identity": stored_identity,
                "expected_source_journal_identity": expected_identity,
            },
        )
    stored_journal_sha256 = metadata.get("source_journal_sha256")
    expected_journal_sha256 = snapshot.journal_sha256 or ""
    if stored_journal_sha256 is None:
        raise ValueError("projection metadata is missing source_journal_sha256")
    if stored_journal_sha256 != expected_journal_sha256:
        raise ProjectionStateError(
            ProjectionStateCode.PROJECTION_MISMATCH,
            "projection source journal byte digest does not match the verified journal",
            details={
                "source_journal_sha256": stored_journal_sha256,
                "expected_source_journal_sha256": expected_journal_sha256,
            },
        )

    projection_metadata_matches = (
        records_indexed == snapshot.record_count and last_event_hash == snapshot.terminal_hash
    )
    if not projection_metadata_matches:
        code = (
            ProjectionStateCode.PROJECTION_STALE
            if records_indexed <= snapshot.record_count
            else ProjectionStateCode.PROJECTION_MISMATCH
        )
        raise ProjectionStateError(
            code,
            "projection metadata does not match the verified journal",
            details={
                "records_indexed": records_indexed,
                "record_count": snapshot.record_count,
                "last_event_hash": last_event_hash,
                "terminal_hash": snapshot.terminal_hash,
            },
        )

    _verify_projected_rows(connection, snapshot)
    return VerifiedProjectionSnapshot(
        journal_path=journal_path,
        database_path=database_path,
        journal_snapshot=snapshot,
        records_indexed=records_indexed,
        last_event_hash=last_event_hash,
        source_journal_path=source_journal_path,
        source_journal_identity=stored_identity,
        source_journal_sha256=stored_journal_sha256 or None,
        projection_identity=stored_projection_identity,
    )


def _recheck_terminal_journal_state(
    journal_path: Path,
    verification: VerifiedProjectionSnapshot,
) -> None:
    snapshot = verified_journal_snapshot(
        journal_path,
        expected_record_count=verification.record_count,
        expected_last_event_hash=verification.terminal_hash,
    )
    if snapshot.ok:
        return
    issue_codes = {issue.code for issue in snapshot.verification.issues}
    expected_mismatch_codes = {
        "expected_record_count_mismatch",
        "expected_last_hash_mismatch",
    }
    if issue_codes and issue_codes <= expected_mismatch_codes:
        raise ProjectionStateError(
            ProjectionStateCode.PROJECTION_STALE,
            "source journal changed while the projection read was in progress",
            details={"verification": snapshot.verification.as_dict()},
        )
    raise ProjectionStateError(
        ProjectionStateCode.JOURNAL_INVALID,
        "source journal verification failed after projection read",
        details={"verification": snapshot.verification.as_dict()},
    )


def _user_version(connection: sqlite3.Connection) -> int:
    row = connection.execute("PRAGMA user_version").fetchone()
    if row is None:
        raise ProjectionSchemaError("could not read sqlite user_version")
    return cast(int, row[0])


def _set_metadata(connection: sqlite3.Connection, values: dict[str, str]) -> None:
    connection.executemany(
        """
        INSERT INTO projection_metadata(key, value)
        VALUES (?, ?)
        ON CONFLICT(key) DO UPDATE SET value = excluded.value
        """,
        values.items(),
    )


def _get_metadata(connection: sqlite3.Connection) -> dict[str, str]:
    rows = connection.execute("SELECT key, value FROM projection_metadata").fetchall()
    return {cast(str, key): cast(str, value) for key, value in rows}


def _projection_source_path_hint(metadata: dict[str, str]) -> str:
    stored_path = metadata.get("source_journal_path")
    if not stored_path:
        raise ValueError("projection metadata is missing source_journal_path")

    return str(_normalize_journal_path(Path(stored_path)))


def _metadata_int(metadata: dict[str, str], key: str) -> int:
    value = metadata.get(key)
    if value is None:
        raise ValueError(f"projection metadata is missing {key}")
    try:
        parsed = int(value)
    except ValueError as exc:
        raise ValueError(f"projection metadata {key} is not an integer") from exc
    if parsed < 0:
        raise ValueError(f"projection metadata {key} cannot be negative")
    return parsed


def _metadata_hash(metadata: dict[str, str], key: str) -> str | None:
    value = metadata.get(key)
    if value is None:
        raise ValueError(f"projection metadata is missing {key}")
    return value or None


def _verify_projected_rows(
    connection: sqlite3.Connection,
    snapshot: VerifiedJournalSnapshot,
) -> None:
    rows = _projected_row_values_and_types(connection)
    _verify_projected_row_values(rows, snapshot)


def _projection_matches_verified_journal_prefix(
    connection: sqlite3.Connection,
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
    if last_event_hash != expected_last_hash:
        return False
    rows = _projected_row_values_and_types(connection)
    if len(rows) != records_indexed:
        return False
    try:
        _verify_projected_row_values(rows, snapshot, expected_count=records_indexed)
    except ProjectionStateError:
        return False
    return True


def _projected_row_values_and_types(connection: sqlite3.Connection) -> list[tuple[object, ...]]:
    select_values = ", ".join(PROJECTED_EVENT_COLUMNS)
    select_types = ", ".join(f"typeof({column})" for column in PROJECTED_EVENT_COLUMNS)
    return [
        tuple(row)
        for row in connection.execute(
            f"""
            SELECT {select_values}, {select_types}
            FROM events
            ORDER BY journal_record_number ASC
            """
        ).fetchall()
    ]


def _verify_projected_row_values(
    rows: list[tuple[object, ...]],
    snapshot: VerifiedJournalSnapshot,
    *,
    expected_count: int | None = None,
) -> None:
    record_count = snapshot.record_count if expected_count is None else expected_count
    if len(rows) != record_count:
        code = (
            ProjectionStateCode.PROJECTION_STALE
            if len(rows) < record_count
            else ProjectionStateCode.PROJECTION_MISMATCH
        )
        raise ProjectionStateError(
            code,
            "projection row count does not match the verified journal",
            details={"rows": len(rows), "record_count": record_count},
        )

    for record_number, event in enumerate(snapshot.events[:record_count], start=1):
        row = rows[record_number - 1]
        actual_values = tuple(row[: len(PROJECTED_EVENT_COLUMNS)])
        actual_types = tuple(cast(str, value) for value in row[len(PROJECTED_EVENT_COLUMNS) :])
        expected_values = _event_projection_values(event, journal_record_number=record_number)
        expected_types = tuple(_expected_sqlite_type(value) for value in expected_values)
        if actual_values != expected_values or actual_types != expected_types:
            mismatched_columns = [
                column
                for column, actual, expected in zip(
                    PROJECTED_EVENT_COLUMNS,
                    actual_values,
                    expected_values,
                    strict=True,
                )
                if actual != expected
            ]
            type_mismatched_columns = [
                column
                for column, actual, expected in zip(
                    PROJECTED_EVENT_COLUMNS,
                    actual_types,
                    expected_types,
                    strict=True,
                )
                if actual != expected
            ]
            raise ProjectionStateError(
                ProjectionStateCode.PROJECTION_MISMATCH,
                "projection row content does not match the verified journal",
                details={
                    "record_number": record_number,
                    "event_id": actual_values[0],
                    "expected_event_id": event.event_id,
                    "mismatched_columns": mismatched_columns,
                    "type_mismatched_columns": type_mismatched_columns,
                },
            )


def _projection_identity(database_path: Path) -> str:
    return f"sqlite-file:{Path(database_path).resolve(strict=False)}"


def _normalize_journal_path(journal_path: Path) -> Path:
    return Path(journal_path).resolve(strict=False)


def _expected_sqlite_type(value: object) -> str:
    if value is None:
        return "null"
    if isinstance(value, int) and not isinstance(value, bool):
        return "integer"
    if isinstance(value, str):
        return "text"
    raise ProjectionStateError(
        ProjectionStateCode.PROJECTION_MISMATCH,
        "projection expected value has unsupported SQLite type",
        details={"value_type": type(value).__name__},
    )


def _migrate_v1_to_v2(connection: sqlite3.Connection) -> None:
    connection.executescript(
        """
        ALTER TABLE events ADD COLUMN verification_status TEXT;
        ALTER TABLE events ADD COLUMN evidence_subject_event_id TEXT;
        ALTER TABLE events ADD COLUMN evidence_event_id TEXT;
        """
    )
    _set_user_version(connection, PROJECTION_SCHEMA_VERSION)
    _set_metadata(connection, {"schema_version": str(PROJECTION_SCHEMA_VERSION)})


def _set_user_version(connection: sqlite3.Connection, version: int) -> None:
    connection.execute(f"PRAGMA user_version = {version}")


def _event_projection_values(
    event: EventEnvelope,
    *,
    journal_record_number: int,
) -> tuple[
    str,
    str,
    str,
    str,
    str,
    str,
    str,
    str | None,
    str | None,
    str,
    str | None,
    int,
    str,
    str | None,
    str | None,
    str | None,
    str | None,
    int,
    str,
]:
    event_object = event_to_dict(event)
    verification_status, evidence_subject_event_id, evidence_event_id = _evidence_projection_values(
        event_object
    )
    return (
        event.event_id,
        event.spec_version,
        event_type_value(event.event_type),
        cast(str, event_object["occurred_at"]),
        cast(str, event_object["observed_at"]),
        event.correlation.trace_id,
        event.correlation.run_id,
        event.correlation.span_id,
        event.correlation.session_id,
        event.causality.root_event_id,
        event.causality.parent_event_id,
        event.causality.sequence,
        cast(str, event.integrity.event_hash),
        event.integrity.previous_event_hash,
        verification_status,
        evidence_subject_event_id,
        evidence_event_id,
        journal_record_number,
        serialize_event(event).decode("utf-8"),
    )


def _timeline_event_from_row(row: Iterable[Any]) -> TimelineEvent:
    values = tuple(row)
    event_data = json.loads(cast(str, values[12]))
    if not isinstance(event_data, dict):
        raise ProjectionQueryError("projected event_json is not a JSON object")

    return TimelineEvent(
        journal_record_number=cast(int, values[0]),
        event_id=cast(str, values[1]),
        event_type=cast(str, values[2]),
        occurred_at=cast(str, values[3]),
        observed_at=cast(str, values[4]),
        trace_id=cast(str, values[5]),
        run_id=cast(str, values[6]),
        sequence=cast(int, values[7]),
        event_hash=cast(str, values[8]),
        verification_status=cast(str | None, values[9]),
        evidence_subject_event_id=cast(str | None, values[10]),
        evidence_event_id=cast(str | None, values[11]),
        event=cast(dict[str, Any], event_data),
    )


def _require_one_selector(
    *,
    trace_id: str | None,
    run_id: str | None,
) -> tuple[str, str]:
    if trace_id is None and run_id is None:
        raise ProjectionQueryError("provide exactly one of trace_id or run_id")
    if trace_id is not None and run_id is not None:
        raise ProjectionQueryError("provide exactly one of trace_id or run_id")
    if trace_id is not None:
        return "trace_id", trace_id
    assert run_id is not None
    return "run_id", run_id


def _case_bundle_manifest(
    incident_data: dict[str, object],
    *,
    artifact_payloads: dict[str, bytes],
    database_path: Path,
    journal_path: Path,
    trace_id: str | None,
    run_id: str | None,
) -> dict[str, Any]:
    verification = incident_data.get("verification")
    if not isinstance(verification, dict):
        raise ProjectionQueryError("case bundle export requires verified projection binding")
    journal = verification.get("journal")
    if not isinstance(journal, dict):
        raise ProjectionQueryError("case bundle export requires verified journal binding")

    return {
        "manifest_version": CASE_BUNDLE_MANIFEST_VERSION,
        "bundle_version": CASE_BUNDLE_VERSION,
        "incident_export_version": incident_data.get("export_version"),
        "canonicalization": CANONICALIZATION_VERSION,
        "selector": deepcopy(incident_data.get("selector")),
        "query": {
            "trace_id": trace_id,
            "run_id": run_id,
        },
        "journal": {
            "path": str(journal_path),
            "source_identity": verification.get("source_journal_identity"),
            "record_count": journal.get("record_count"),
            "terminal_hash": journal.get("terminal_hash"),
            "journal_sha256": journal.get("journal_sha256"),
            "verification": deepcopy(journal.get("verification")),
        },
        "projection": {
            "database_path": str(database_path),
            "schema_version": verification.get("schema_version"),
            "state": verification.get("state"),
            "projection_identity": verification.get("projection_identity"),
            "records_indexed": verification.get("records_indexed"),
            "source_journal_identity": verification.get("source_journal_identity"),
            "source_journal_sha256": verification.get("source_journal_sha256"),
        },
        "files": [
            _case_bundle_file_manifest(filename, artifact_payloads[filename])
            for filename in CASE_BUNDLE_FILENAMES
        ],
        "external_signature": None,
        "external_checkpoint": None,
    }


def _case_bundle_file_manifest(filename: str, data: bytes) -> dict[str, object]:
    return {
        "path": filename,
        "size_bytes": len(data),
        "sha256": f"sha256:{hashlib.sha256(data).hexdigest()}",
    }


def _case_bundle_paths(output_dir: Path) -> tuple[Path, Path, Path]:
    paths = tuple(output_dir / filename for filename in CASE_BUNDLE_FILENAMES)
    if any(path.parent != output_dir for path in paths):
        raise ProjectionQueryError("case bundle output path escaped output directory")
    return cast(tuple[Path, Path, Path], paths)


def _create_case_bundle_staging_dir(output_dir: Path) -> tuple[Path, Path]:
    final_dir = Path(output_dir).resolve(strict=False)
    if final_dir == final_dir.parent:
        raise ProjectionQueryError("case bundle output directory must be below a parent directory")
    if final_dir.exists() or final_dir.is_symlink():
        raise ProjectionQueryError(f"case bundle output already exists: {final_dir.name}")

    parent = final_dir.parent
    try:
        parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    except OSError as exc:
        raise ProjectionQueryError("failed to prepare case bundle parent directory") from exc

    for _ in range(10):
        staging_dir = parent / f".{final_dir.name}.staging-{uuid4().hex}"
        try:
            os.mkdir(staging_dir, 0o700)
            _ensure_private_case_bundle_directory(staging_dir)
            return final_dir, staging_dir
        except FileExistsError:
            continue
        except OSError as exc:
            raise ProjectionQueryError("failed to create case bundle staging directory") from exc
    raise ProjectionQueryError("failed to allocate unique case bundle staging directory")


def _ensure_private_case_bundle_directory(path: Path) -> None:
    if os.name != "posix":
        return
    mode = path.stat().st_mode & 0o777
    if mode & 0o077:
        os.chmod(path, 0o700)
    mode = path.stat().st_mode & 0o777
    if mode & 0o077:
        raise ProjectionQueryError(
            f"case bundle directory is not private: {path}; expected mode 0700 or stricter"
        )


def _write_private_case_bundle_file(path: Path, data: bytes) -> None:
    flags = (
        os.O_WRONLY
        | os.O_CREAT
        | os.O_EXCL
        | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_NOFOLLOW", 0)
    )
    try:
        fd = os.open(path, flags, 0o600)
    except FileExistsError as exc:
        raise ProjectionQueryError(f"case bundle output already exists: {path.name}") from exc
    except OSError as exc:
        raise ProjectionQueryError(f"failed to write case bundle output: {path.name}") from exc

    try:
        if os.name == "posix":
            os.fchmod(fd, 0o600)
        with os.fdopen(fd, "wb") as handle:
            fd = -1
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
    except OSError as exc:
        raise ProjectionQueryError(f"failed to write case bundle output: {path.name}") from exc
    finally:
        if fd >= 0:
            os.close(fd)


def _publish_case_bundle_directory(staging_dir: Path, output_dir: Path) -> None:
    if output_dir.exists() or output_dir.is_symlink():
        raise ProjectionQueryError(f"case bundle output already exists: {output_dir.name}")
    try:
        os.replace(staging_dir, output_dir)
    except FileExistsError as exc:
        raise ProjectionQueryError(f"case bundle output already exists: {output_dir.name}") from exc
    except OSError as exc:
        raise ProjectionQueryError("failed to publish completed case bundle") from exc
    try:
        _fsync_directory(output_dir.parent)
    except OSError as exc:
        raise ProjectionQueryError("failed to sync case bundle parent directory") from exc


def _fsync_directory(path: Path) -> None:
    if os.name != "posix":
        return
    fd = os.open(
        path,
        os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_CLOEXEC", 0),
    )
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _cleanup_case_bundle_staging(staging_dir: Path) -> None:
    shutil.rmtree(staging_dir, ignore_errors=True)


def _evidence_projection_values(
    event_object: dict[str, Any],
) -> tuple[str | None, str | None, str | None]:
    payload = event_object.get("payload")
    if not isinstance(payload, dict):
        return None, None, None

    evidence_link = payload.get("evidence_link")
    if isinstance(evidence_link, dict):
        return (
            _string_or_none(evidence_link.get("verification_status")),
            _string_or_none(evidence_link.get("subject_event_id")),
            _string_or_none(evidence_link.get("evidence_event_id")),
        )

    return (
        _string_or_none(payload.get("verification_status")),
        _string_or_none(payload.get("subject_event_id")),
        _string_or_none(payload.get("evidence_event_id")),
    )


def _string_or_none(value: object) -> str | None:
    if isinstance(value, str) and value:
        return value
    return None


def _timeline_event_matches(event: TimelineEvent, filters: dict[str, str | None]) -> bool:
    event_object = event.event
    if filters["trace_id"] is not None and event.trace_id != filters["trace_id"]:
        return False
    if filters["run_id"] is not None and event.run_id != filters["run_id"]:
        return False
    if filters["event_type"] is not None and event.event_type != filters["event_type"]:
        return False
    if (
        filters["verification_status"] is not None
        and event.verification_status != filters["verification_status"]
    ):
        return False

    principal = event_object.get("principal")
    if filters["principal_id"] is not None and not (
        isinstance(principal, dict) and principal.get("principal_id") == filters["principal_id"]
    ):
        return False

    classification = event_object.get("classification")
    if filters["sensitivity"] is not None and not (
        isinstance(classification, dict)
        and classification.get("sensitivity") == filters["sensitivity"]
    ):
        return False
    if filters["trust"] is not None and not (
        isinstance(classification, dict) and classification.get("trust") == filters["trust"]
    ):
        return False

    payload = event_object.get("payload")
    if filters["tool_name"] is not None and filters["tool_name"] not in _payload_values_for_keys(
        payload, {"name", "tool", "tool_name"}
    ):
        return False
    if filters["descriptor_hash"] is not None and filters[
        "descriptor_hash"
    ] not in _payload_values_for_keys(payload, {"descriptor_hash"}):
        return False
    return not (
        filters["resource"] is not None and filters["resource"] not in _string_values(payload)
    )


def _incident_summary(events: list[dict[str, Any]]) -> dict[str, object]:
    verification_statuses: dict[str, int] = {}
    for event in events:
        status = _verification_status(event)
        if status is not None:
            verification_statuses[status] = verification_statuses.get(status, 0) + 1

    return {
        "principals": sorted(
            {principal_id for event in events if (principal_id := _principal_id(event)) is not None}
        ),
        "tools": sorted({value for event in events for value in _tool_names(event)}),
        "resources": sorted({value for event in events for value in _resource_identifiers(event)}),
        "verification_statuses": verification_statuses,
        "evidence_links": list(_evidence_links_from_event_objects(events)),
        "conflicting_event_ids": [
            cast(str, event["event_id"])
            for event in events
            if event.get("event_type") == "side_effect.conflict_detected"
        ],
        "unknown_event_ids": [
            cast(str, event["event_id"])
            for event in events
            if _verification_status(event) == "unknown"
        ],
        "limitations": sorted(
            {limitation for event in events for limitation in _evidence_limitations(event)}
        ),
        "detection_hit_event_ids": [
            cast(str, event["event_id"])
            for event in events
            if event.get("event_type") == "lineage.alert.created"
        ],
        "claims_language": "No observation recorded is not proof that a side effect did not occur.",
    }


def _case_markdown(incident_data: dict[str, object]) -> str:
    selector = cast(dict[str, object], incident_data["selector"])
    summary = cast(dict[str, object], incident_data["summary"])
    return "\n".join(
        [
            "# ActionLineage Case Report",
            "",
            f"- Selector: `{selector['type']}={selector['value']}`",
            f"- Event count: {incident_data['event_count']}",
            f"- Timeline order: {incident_data['timeline_order']}",
            f"- Principals: {', '.join(cast(list[str], summary['principals'])) or 'none recorded'}",
            f"- Tools: {', '.join(cast(list[str], summary['tools'])) or 'none recorded'}",
            f"- Resources: {', '.join(cast(list[str], summary['resources'])) or 'none recorded'}",
            "",
            "## Verification",
            "",
            "No observation recorded is not proof that a side effect did not occur.",
            f"Verification statuses: {summary['verification_statuses']}",
            "",
        ]
    )


def _finding(label: str, values: list[str]) -> str:
    return f"{label}: {', '.join(values) if values else 'none recorded'}"


def _format_counts(counts: dict[str, int]) -> str:
    if not counts:
        return "none recorded"
    return ", ".join(f"{key}={counts[key]}" for key in sorted(counts))


def _event_node_id(event_id: str) -> str:
    return f"event:{event_id}"


def _entity_node_id(kind: str, value: str) -> str:
    return f"{kind}:{value}"


def _edge_id(source: str, target: str, relationship: str) -> str:
    return f"edge:{relationship}:{source}:{target}"


def _add_edge(
    edges: dict[str, InvestigationGraphEdge],
    *,
    source: str,
    target: str,
    relationship: str,
    attributes: dict[str, object],
) -> None:
    edge_id = _edge_id(source, target, relationship)
    edges.setdefault(
        edge_id,
        InvestigationGraphEdge(
            edge_id=edge_id,
            source=source,
            target=target,
            relationship=relationship,
            attributes=attributes,
        ),
    )


def _ensure_event_reference_node(
    nodes: dict[str, InvestigationGraphNode],
    event_id: str,
    *,
    event_ids: set[str],
) -> None:
    node_id = _event_node_id(event_id)
    if node_id in nodes:
        return
    kind = "event_reference" if event_id not in event_ids else "event"
    nodes[node_id] = InvestigationGraphNode(
        node_id=node_id,
        kind=kind,
        label=event_id,
        attributes={"event_id": event_id, "in_selected_timeline": event_id in event_ids},
    )


def _parent_event_id(event: dict[str, Any]) -> str | None:
    causality = event.get("causality")
    if isinstance(causality, dict):
        return _string_or_none(causality.get("parent_event_id"))
    return None


def _evidence_edge_attributes(link: dict[str, Any]) -> dict[str, object]:
    attributes: dict[str, object] = {}
    for key in (
        "corroboration_type",
        "observer_identity",
        "confidence",
        "verification_status",
        "limitations",
    ):
        value = link.get(key)
        if isinstance(value, str | int | float | bool):
            attributes[key] = value
        elif isinstance(value, list):
            safe_list = [item for item in value if isinstance(item, str | int | float | bool)]
            if safe_list:
                attributes[key] = safe_list
    return attributes


def _evidence_links(events: Iterable[TimelineEvent]) -> Iterator[dict[str, Any]]:
    for event in events:
        yield from _evidence_links_from_event_objects((event.event,))


def _evidence_links_from_event_objects(
    events: Iterable[dict[str, Any]],
) -> Iterator[dict[str, Any]]:
    for event in events:
        payload = event.get("payload")
        if not isinstance(payload, dict):
            continue
        evidence_link = payload.get("evidence_link")
        if isinstance(evidence_link, dict):
            yield cast(dict[str, Any], evidence_link)


def _principal_id(event: dict[str, Any]) -> str | None:
    principal = event.get("principal")
    if isinstance(principal, dict):
        return _string_or_none(principal.get("principal_id"))
    return None


def _verification_status(event: dict[str, Any]) -> str | None:
    payload = event.get("payload")
    if not isinstance(payload, dict):
        return None
    evidence_link = payload.get("evidence_link")
    if isinstance(evidence_link, dict):
        return _string_or_none(evidence_link.get("verification_status"))
    return _string_or_none(payload.get("verification_status"))


def _evidence_limitations(event: dict[str, Any]) -> tuple[str, ...]:
    payload = event.get("payload")
    if not isinstance(payload, dict):
        return ()
    evidence_link = payload.get("evidence_link")
    if not isinstance(evidence_link, dict):
        return ()
    limitations = evidence_link.get("limitations")
    if not isinstance(limitations, list):
        return ()
    return tuple(
        summary_text for value in limitations if (summary_text := _summary_text(value)) is not None
    )


def _tool_names(event: dict[str, Any]) -> tuple[str, ...]:
    return tuple(
        _payload_summary_values_for_keys(event.get("payload"), {"name", "tool", "tool_name"})
    )


def _resource_identifiers(event: dict[str, Any]) -> tuple[str, ...]:
    payload = event.get("payload")
    return tuple(_payload_summary_values_for_keys(payload, {"identifier", "path", "uri", "url"}))


def _payload_summary_values_for_keys(value: object, keys: set[str]) -> tuple[str, ...]:
    matches: set[str] = set()
    if isinstance(value, Mapping):
        if _is_capture_marker(value):
            return ()
        for key, child in value.items():
            if key in keys and (summary_text := _summary_text(child)) is not None:
                matches.add(summary_text)
            matches.update(_payload_summary_values_for_keys(child, keys))
    elif isinstance(value, list):
        for child in value:
            matches.update(_payload_summary_values_for_keys(child, keys))
    return tuple(sorted(matches))


def _payload_values_for_keys(value: object, keys: set[str]) -> set[str]:
    matches: set[str] = set()
    if isinstance(value, dict):
        for key, child in value.items():
            if key in keys and isinstance(child, str):
                matches.add(child)
            matches.update(_payload_values_for_keys(child, keys))
    elif isinstance(value, list):
        for child in value:
            matches.update(_payload_values_for_keys(child, keys))
    return matches


def _string_values(value: object) -> set[str]:
    values: set[str] = set()
    if isinstance(value, str):
        values.add(value)
    elif isinstance(value, dict):
        for child in value.values():
            values.update(_string_values(child))
    elif isinstance(value, list):
        for child in value:
            values.update(_string_values(child))
    return values


def _summary_text(value: object) -> str | None:
    if isinstance(value, str):
        return value
    if _is_capture_marker(value):
        return _capture_marker_summary(cast(Mapping[str, object], value))
    return None


def _is_capture_marker(value: object) -> bool:
    return isinstance(value, Mapping) and value.get("marker") == "actionlineage.capture.v1"


def _capture_marker_summary(metadata: Mapping[str, object]) -> str:
    original_length = metadata.get("original_length", "unknown")
    digest = metadata.get("digest", "unknown")
    digest_scope = metadata.get("digest_scope", "unknown")
    return (
        f"[TRUNCATED original_length={original_length} digest={digest} digest_scope={digest_scope}]"
    )
