from __future__ import annotations

import json
from pathlib import Path

from actionlineage.demo.scenario import build_demo_events
from actionlineage.domain import RedactionPolicy
from actionlineage.exporters import (
    ExportProfile,
    FileSink,
    OpenTelemetrySpanSink,
    TaxiiHttpSink,
    WebhookSink,
    export_events,
    map_event_for_profile,
    otel_attributes_for_event,
    taxii_envelope_for_stix_bundle,
)

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_export_profiles_map_core_fields() -> None:
    event = build_demo_events()[0]

    ocsf = map_event_for_profile(event, profile=ExportProfile.OCSF)
    ecs = map_event_for_profile(event, profile=ExportProfile.ECS)
    splunk = map_event_for_profile(event, profile=ExportProfile.SPLUNK_HEC)
    sigma = map_event_for_profile(event, profile=ExportProfile.SIGMA)
    stix = map_event_for_profile(event, profile=ExportProfile.STIX)
    taxii = map_event_for_profile(event, profile=ExportProfile.TAXII)
    otel = map_event_for_profile(event, profile=ExportProfile.OPENTELEMETRY)

    assert ocsf["uid"] == event.event_id
    assert ecs["event"]["id"] == event.event_id
    assert splunk["event"]["event_id"] == event.event_id
    assert sigma["detection"]["selection"]["event_id"] == event.event_id
    assert stix["type"] == "bundle"
    assert stix["objects"][0]["x_actionlineage_event_id"] == event.event_id
    assert taxii["objects"][0]["x_actionlineage_event_id"] == event.event_id
    assert taxii["more"] is False
    assert otel["actionlineage.event_id"] == event.event_id


def test_stix_profile_uses_stable_ids_and_canonical_journal_language() -> None:
    event = build_demo_events()[0]

    first = map_event_for_profile(event, profile=ExportProfile.STIX)
    second = map_event_for_profile(event, profile=ExportProfile.STIX)

    assert first["id"] == second["id"]
    assert first["objects"][0]["id"] == second["objects"][0]["id"]
    assert str(first["id"]).startswith("bundle--")
    note = first["objects"][1]
    assert "append-only local journal remains canonical evidence" in note["content"]


def test_taxii_envelope_wraps_stix_objects() -> None:
    event = build_demo_events()[0]
    stix = map_event_for_profile(event, profile=ExportProfile.STIX)
    envelope = taxii_envelope_for_stix_bundle(stix)

    assert envelope == map_event_for_profile(event, profile=ExportProfile.TAXII)
    assert envelope["more"] is False
    assert len(envelope["objects"]) == 2


def test_export_redacts_canary_secret_from_every_profile() -> None:
    raw_secret = "Bearer exporter-secret-value-123456789"
    event = build_demo_events()[0].model_copy(
        update={"payload": {"headers": {"authorization": raw_secret}}}
    )

    for profile in ExportProfile:
        mapped = map_event_for_profile(event, profile=profile)
        assert raw_secret not in json.dumps(mapped, sort_keys=True)

    attributes = otel_attributes_for_event(event)
    assert raw_secret not in json.dumps(attributes, sort_keys=True)


def test_file_sink_writes_ndjson(tmp_path) -> None:
    output_path = tmp_path / "events.ndjson"
    events = build_demo_events()[:2]
    result = export_events(
        events,
        profile=ExportProfile.ACTIONLINEAGE_JSON,
        sink=FileSink(output_path),
    )

    lines = output_path.read_text(encoding="utf-8").splitlines()
    assert result.ok
    assert result.records_exported == 2
    assert len(lines) == 2
    assert json.loads(lines[0])["event_id"] == events[0].event_id


def test_webhook_sink_failure_does_not_claim_journal_failure() -> None:
    class FailingSender:
        def send(self, payload: dict[str, object]) -> None:
            raise RuntimeError("network unavailable")

    result = export_events(
        build_demo_events()[:2],
        profile=ExportProfile.SPLUNK_HEC,
        sink=WebhookSink(FailingSender()),
    )

    assert not result.ok
    assert result.records_exported == 0
    assert result.as_dict()["journal_first"] is True
    assert "RuntimeError" in str(result.error)


def test_taxii_sink_uses_injected_sender() -> None:
    class RecordingSender:
        def __init__(self) -> None:
            self.payloads: list[dict[str, object]] = []

        def send(self, payload: dict[str, object]) -> None:
            self.payloads.append(payload)

    sender = RecordingSender()
    result = export_events(
        build_demo_events()[:1],
        profile=ExportProfile.TAXII,
        sink=TaxiiHttpSink(sender=sender),
    )

    assert result.ok
    assert len(sender.payloads) == 1
    assert sender.payloads[0]["more"] is False
    assert "objects" in sender.payloads[0]


def test_taxii_sink_failure_remains_journal_first() -> None:
    class FailingSender:
        def send(self, payload: dict[str, object]) -> None:
            raise RuntimeError("taxii unavailable")

    result = export_events(
        build_demo_events()[:1],
        profile=ExportProfile.TAXII,
        sink=TaxiiHttpSink(sender=FailingSender()),
    )

    assert not result.ok
    assert result.records_exported == 0
    assert result.as_dict()["journal_first"] is True
    assert "RuntimeError" in str(result.error)


def test_otel_attributes_are_redacted_and_bounded() -> None:
    event = build_demo_events()[0].model_copy(update={"payload": {"body": "x" * 80}})
    attributes = otel_attributes_for_event(
        event,
        redaction_policy=RedactionPolicy(max_string_length=12),
    )
    payload = json.loads(str(attributes["actionlineage.payload_json"]))

    assert attributes["actionlineage.event_id"] == event.event_id
    assert payload["body"]["marker"] == "actionlineage.capture.v1"
    assert payload["body"]["value"] == "x" * 12


def test_opentelemetry_semconv_proposal_matches_exporter_keys() -> None:
    proposal_path = REPO_ROOT / "integrations" / "opentelemetry" / "actionlineage-semconv-v0.json"
    proposal = json.loads(proposal_path.read_text(encoding="utf-8"))
    event = build_demo_events()[0]
    attributes = otel_attributes_for_event(event)

    proposal_keys = {attribute["name"] for attribute in proposal["attributes"]}

    assert proposal["status"] == "proposal"
    assert proposal_keys == set(attributes)
    assert "upstream OpenTelemetry standardization" in proposal["not_claimed"]
    assert "No observation recorded is not proof" in proposal["event_semantics"]["absence"]


def test_opentelemetry_span_sink_uses_injected_tracer() -> None:
    event = build_demo_events()[0]
    tracer = RecordingTracer()
    result = export_events(
        (event,),
        profile=ExportProfile.OPENTELEMETRY,
        sink=OpenTelemetrySpanSink(tracer=tracer),
    )

    assert result.ok
    assert len(tracer.spans) == 1
    span = tracer.spans[0]
    assert span.name == f"ActionLineage {event.event_type}"
    assert span.attributes["actionlineage.event_id"] == event.event_id
    assert span.attributes["actionlineage.payload_json"]


def test_opentelemetry_span_sink_failure_remains_journal_first() -> None:
    class FailingTracer:
        def start_as_current_span(self, name: str) -> RecordingSpan:
            raise RuntimeError("collector unavailable")

    result = export_events(
        build_demo_events()[:1],
        profile=ExportProfile.OPENTELEMETRY,
        sink=OpenTelemetrySpanSink(tracer=FailingTracer()),
    )

    assert not result.ok
    assert result.records_exported == 0
    assert result.as_dict()["journal_first"] is True
    assert "RuntimeError" in str(result.error)


class RecordingSpan:
    def __init__(self, name: str) -> None:
        self.name = name
        self.attributes: dict[str, bool | int | float | str] = {}

    def __enter__(self) -> RecordingSpan:
        return self

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        return None

    def set_attribute(self, key: str, value: bool | int | float | str) -> None:
        self.attributes[key] = value


class RecordingTracer:
    def __init__(self) -> None:
        self.spans: list[RecordingSpan] = []

    def start_as_current_span(self, name: str) -> RecordingSpan:
        span = RecordingSpan(name)
        self.spans.append(span)
        return span
