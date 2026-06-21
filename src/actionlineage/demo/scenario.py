"""Deterministic evidence-plane demo scenario."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import cast

from actionlineage.domain import (
    Classification,
    Correlation,
    CorroborationType,
    EventEnvelope,
    EventType,
    EvidenceLink,
    EvidenceRelationship,
    FixedClock,
    FixedIdGenerator,
    Principal,
    PrincipalType,
    Sensitivity,
    Source,
    TrustLevel,
    VerificationStatus,
    deterministic_json_bytes,
)
from actionlineage.domain.events import JsonObject
from actionlineage.evidence import EvidenceNormalizer
from actionlineage.journal import LocalJournal, VerificationResult
from actionlineage.projection import (
    IncidentExport,
    RebuildResult,
    export_incident,
    rebuild_projection,
)

DEMO_TRACE_ID = "trace_demo_evidence_plane"
DEMO_RUN_ID = "run_demo_evidence_plane"
DEMO_TIME = datetime(2026, 6, 21, 18, 42, 12, tzinfo=UTC)
DEMO_EVENT_IDS = tuple(f"evt_demo_{index:02d}" for index in range(16))


@dataclass(frozen=True, slots=True)
class DemoResult:
    """Paths and evidence summary produced by the deterministic demo."""

    output_dir: Path
    journal_path: Path
    database_path: Path
    timeline_path: Path
    incident_path: Path
    trace_id: str
    run_id: str
    verification: VerificationResult
    projection: RebuildResult
    incident: IncidentExport

    def as_dict(self) -> dict[str, object]:
        """Return a JSON-compatible result summary."""

        return {
            "ok": self.verification.ok,
            "output_dir": str(self.output_dir),
            "journal_path": str(self.journal_path),
            "database_path": str(self.database_path),
            "timeline_path": str(self.timeline_path),
            "incident_path": str(self.incident_path),
            "trace_id": self.trace_id,
            "run_id": self.run_id,
            "records_verified": self.verification.records_verified,
            "last_event_hash": self.verification.last_event_hash,
            "projection_records_indexed": self.projection.records_indexed,
            "event_count": self.incident.as_dict()["event_count"],
            "statuses": _status_counts(self.incident),
            "commands": {
                "verify": (
                    f"uv run actionlineage journal verify {self.journal_path} "
                    f"--expected-record-count {self.verification.records_verified} "
                    f"--expected-last-event-hash {self.verification.last_event_hash}"
                ),
                "timeline": (
                    f"uv run actionlineage projection timeline {self.database_path} "
                    f"--trace-id {self.trace_id}"
                ),
                "incident": (
                    f"uv run actionlineage projection export-incident {self.database_path} "
                    f"--trace-id {self.trace_id}"
                ),
                "console": (
                    f"uv run actionlineage projection export-console {self.database_path} "
                    f"{self.output_dir / 'console.html'} --trace-id {self.trace_id}"
                ),
            },
        }


def run_demo(output_dir: Path) -> DemoResult:
    """Run the deterministic local demo and write journal/projection artifacts."""

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    journal_path = output_dir / "evidence.jsonl"
    database_path = output_dir / "projection.sqlite"
    timeline_path = output_dir / "timeline.json"
    incident_path = output_dir / "incident.json"
    for path in (journal_path, database_path, timeline_path, incident_path):
        path.unlink(missing_ok=True)

    events = build_demo_events()
    journal = LocalJournal(journal_path)
    for event in events:
        journal.append(event)

    verification = journal.verify(expected_record_count=len(events))
    projection = rebuild_projection(journal_path, database_path)
    incident = export_incident(database_path, trace_id=DEMO_TRACE_ID)

    timeline_path.write_bytes(
        deterministic_json_bytes(
            cast(
                JsonObject,
                {
                    "trace_id": DEMO_TRACE_ID,
                    "run_id": DEMO_RUN_ID,
                    "events": [event.event_id for event in incident.timeline.events],
                },
            )
        )
    )
    incident_path.write_bytes(deterministic_json_bytes(_json_object(incident.as_dict())))

    return DemoResult(
        output_dir=output_dir,
        journal_path=journal_path,
        database_path=database_path,
        timeline_path=timeline_path,
        incident_path=incident_path,
        trace_id=DEMO_TRACE_ID,
        run_id=DEMO_RUN_ID,
        verification=verification,
        projection=projection,
        incident=incident,
    )


def build_demo_events() -> tuple[EventEnvelope, ...]:
    """Build the deterministic event timeline without writing files."""

    normalizer = EvidenceNormalizer(
        correlation=Correlation(trace_id=DEMO_TRACE_ID, run_id=DEMO_RUN_ID),
        source=Source(component="local_tool_adapter", instance_id="demo_adapter", version="0.1.0"),
        principal=Principal(
            principal_id="agent_demo",
            principal_type=PrincipalType.AGENT,
            on_behalf_of="user_demo",
            credential_id="none",
        ),
        classification=Classification(sensitivity=Sensitivity.INTERNAL, trust=TrustLevel.LOCAL),
        clock=FixedClock(DEMO_TIME),
        id_generator=FixedIdGenerator(DEMO_EVENT_IDS),
    )
    verifier_source = Source(
        component="evidence_verifier",
        instance_id="demo_verifier",
        version="0.1.0",
    )
    observer_source = Source(
        component="filesystem_observer",
        instance_id="demo_filesystem",
        version="0.1.0",
    )
    policy_source = Source(component="policy_adapter", instance_id="demo_policy", version="0.1.0")

    events: list[EventEnvelope] = []
    events.append(
        normalizer.record(
            EventType.AGENT_INTENT_RECORDED,
            {
                "intent": {
                    "summary": "inspect local workspace evidence",
                    "initiating_principal": "user_demo",
                }
            },
            principal=Principal(principal_id="user_demo", principal_type=PrincipalType.HUMAN),
        )
    )
    events.append(
        normalizer.record(
            EventType.AGENT_RUN_STARTED,
            {"run": {"mode": "deterministic_demo", "model_provider": "none"}},
        )
    )

    read_ack = _record_tool_lifecycle(
        normalizer,
        events,
        tool_name="safe_files.read",
        descriptor_hash="sha256:demo_safe_files_read",
        arguments_digest="sha256:demo_read_quarterly_plan",
        authorized_by="local_demo_policy",
    )
    observation = normalizer.record(
        EventType.SIDE_EFFECT_OBSERVED,
        {
            "observer_identity": "filesystem_observer",
            "observed_resource": {
                "type": "file",
                "path": "demo://workspace/docs/quarterly-plan.txt",
                "sensitivity": "restricted",
            },
            "observation": {"status": "observed", "content_captured": False},
            "verification_status": VerificationStatus.OBSERVED.value,
        },
        source=observer_source,
        classification=Classification(sensitivity=Sensitivity.RESTRICTED, trust=TrustLevel.LOCAL),
    )
    events.append(observation)
    events.append(
        normalizer.record(
            EventType.SIDE_EFFECT_VERIFIED,
            {
                "evidence_link": EvidenceLink(
                    subject_event_id=read_ack.event_id,
                    relationship=EvidenceRelationship.CORROBORATES,
                    evidence_event_id=observation.event_id,
                    corroboration_type=CorroborationType.INDEPENDENT_OBSERVER,
                    observer_identity="filesystem_observer",
                    confidence=0.95,
                    verification_status=VerificationStatus.VERIFIED,
                    limitations=("local deterministic filesystem fixture",),
                ).as_payload()
            },
            source=verifier_source,
            parent_event_id=observation.event_id,
        )
    )

    send_ack = _record_tool_lifecycle(
        normalizer,
        events,
        tool_name="safe_http.send",
        descriptor_hash="sha256:demo_safe_http_send",
        arguments_digest="sha256:demo_http_send",
        authorized_by="local_demo_policy",
    )
    events.append(
        normalizer.record(
            EventType.SIDE_EFFECT_UNVERIFIED,
            {
                "evidence_link": EvidenceLink(
                    subject_event_id=send_ack.event_id,
                    relationship=EvidenceRelationship.LIMITS,
                    evidence_event_id=send_ack.event_id,
                    corroboration_type=CorroborationType.SELF_REPORTED,
                    observer_identity="safe_http.send",
                    confidence=0.2,
                    verification_status=VerificationStatus.UNVERIFIED,
                    limitations=("tool acknowledgement only; no independent receiver observation",),
                ).as_payload()
            },
            source=verifier_source,
            parent_event_id=send_ack.event_id,
        )
    )

    blocked_request = normalizer.record(
        EventType.TOOL_EXECUTION_REQUESTED,
        {
            "tool_identity": {
                "name": "unsafe_shell.delete",
                "descriptor_hash": "sha256:demo_unsafe_shell_delete",
            },
            "arguments_digest": "sha256:demo_blocked_delete",
            "requested_state": "requested",
        },
    )
    events.append(blocked_request)
    policy_decision = normalizer.record(
        EventType.POLICY_DECISION,
        {
            "outcome": "deny",
            "policy_bundle_version": "demo-policy@2026-06-21",
            "rule_id": "demo.no_shell_delete",
            "reason": "destructive shell operation is outside the deterministic demo boundary",
            "input_digest": "sha256:demo_blocked_delete",
        },
        source=policy_source,
        parent_event_id=blocked_request.event_id,
    )
    events.append(policy_decision)
    events.append(
        normalizer.record(
            EventType.TOOL_EXECUTION_NOT_DISPATCHED,
            {
                "tool_identity": {
                    "name": "unsafe_shell.delete",
                    "descriptor_hash": "sha256:demo_unsafe_shell_delete",
                },
                "not_dispatched": {
                    "reason": "policy_denied",
                    "downstream_forwarded": False,
                    "policy_decision_event_id": policy_decision.event_id,
                },
                "verification_status": VerificationStatus.UNVERIFIED.value,
            },
            parent_event_id=policy_decision.event_id,
        )
    )

    return tuple(events)


def _record_tool_lifecycle(
    normalizer: EvidenceNormalizer,
    events: list[EventEnvelope],
    *,
    tool_name: str,
    descriptor_hash: str,
    arguments_digest: str,
    authorized_by: str,
) -> EventEnvelope:
    requested = normalizer.record(
        EventType.TOOL_EXECUTION_REQUESTED,
        {
            "tool_identity": {"name": tool_name, "descriptor_hash": descriptor_hash},
            "arguments_digest": arguments_digest,
            "requested_state": "requested",
        },
    )
    events.append(requested)
    authorized = normalizer.record(
        EventType.TOOL_EXECUTION_AUTHORIZED,
        {
            "tool_identity": {"name": tool_name, "descriptor_hash": descriptor_hash},
            "authorization": {
                "outcome": "authorized",
                "authorized_by": authorized_by,
                "policy_enforced": False,
            },
        },
        parent_event_id=requested.event_id,
    )
    events.append(authorized)
    dispatched = normalizer.record(
        EventType.TOOL_EXECUTION_DISPATCHED,
        {
            "tool_identity": {"name": tool_name, "descriptor_hash": descriptor_hash},
            "dispatch": {"state": "dispatched", "adapter": "local_tool_adapter"},
        },
        parent_event_id=authorized.event_id,
    )
    events.append(dispatched)
    acknowledged = normalizer.record(
        EventType.TOOL_EXECUTION_ACKNOWLEDGED,
        {
            "tool_identity": {"name": tool_name, "descriptor_hash": descriptor_hash},
            "acknowledgement": {
                "status": "succeeded",
                "side_effect_status": VerificationStatus.UNVERIFIED.value,
                "note": "acknowledgement is not side-effect verification",
            },
        },
        parent_event_id=dispatched.event_id,
    )
    events.append(acknowledged)
    return acknowledged


def _status_counts(incident: IncidentExport) -> dict[str, int]:
    counts: dict[str, int] = {}
    events = incident.as_dict()["events"]
    if not isinstance(events, list):
        return counts
    for event in events:
        if not isinstance(event, dict):
            continue
        payload = event.get("payload")
        if not isinstance(payload, dict):
            continue
        status = _payload_status(payload)
        if status is None:
            continue
        counts[status] = counts.get(status, 0) + 1
    return dict(sorted(counts.items()))


def _payload_status(payload: dict[object, object]) -> str | None:
    evidence_link = payload.get("evidence_link")
    if isinstance(evidence_link, dict):
        status = evidence_link.get("verification_status")
        if isinstance(status, str):
            return status
    status = payload.get("verification_status")
    if isinstance(status, str):
        return status
    return None


def _json_object(value: dict[str, object]) -> JsonObject:
    json.dumps(value, allow_nan=False)
    return cast(JsonObject, value)
