"""Export profile mappings with redaction-before-sink behavior."""

from __future__ import annotations

import importlib
import json
import uuid
from contextlib import AbstractContextManager
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Protocol

from actionlineage.domain import (
    EventEnvelope,
    RedactionPolicy,
    deterministic_json_bytes,
    event_to_dict,
)
from actionlineage.domain.events import JsonObject


class ExportProfile(StrEnum):
    """Supported deterministic export profiles."""

    ACTIONLINEAGE_JSON = "actionlineage_json"
    OPENTELEMETRY = "opentelemetry"
    OCSF = "ocsf"
    ECS = "ecs"
    SPLUNK_HEC = "splunk_hec"
    SIGMA = "sigma"
    STIX = "stix"
    TAXII = "taxii"


class ExportSink(Protocol):
    """Protocol for export sinks."""

    def emit(self, record: JsonObject) -> None:
        """Emit one mapped record."""


@dataclass(frozen=True, slots=True)
class ExportResult:
    """Export attempt result."""

    ok: bool
    records_attempted: int
    records_exported: int
    error: str | None = None

    def as_dict(self) -> dict[str, object]:
        return {
            "ok": self.ok,
            "records_attempted": self.records_attempted,
            "records_exported": self.records_exported,
            "error": self.error,
            "journal_first": True,
        }


@dataclass(slots=True)
class FileSink:
    """NDJSON file sink for deterministic integration tests."""

    path: Path

    def emit(self, record: JsonObject) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("ab") as output:
            output.write(deterministic_json_bytes(record))
            output.write(b"\n")


class WebhookSender(Protocol):
    """Injectable webhook sender for tests and optional runtime adapters."""

    def send(self, payload: JsonObject) -> None:
        """Send one JSON payload."""


class TaxiiSender(Protocol):
    """Injectable TAXII sender for tests and optional runtime adapters."""

    def send(self, payload: JsonObject) -> None:
        """Send one TAXII envelope."""


@dataclass(frozen=True, slots=True)
class WebhookSink:
    """Webhook sink with injectable sender to avoid core network dependencies."""

    sender: WebhookSender

    def emit(self, record: JsonObject) -> None:
        self.sender.send(record)


@dataclass(frozen=True, slots=True)
class TaxiiHttpSink:
    """TAXII object-collection sink with lazy optional HTTP runtime."""

    collection_url: str | None = None
    bearer_token: str | None = None
    timeout_seconds: float = 30.0
    sender: TaxiiSender | None = None

    def emit(self, record: JsonObject) -> None:
        envelope = record if _is_taxii_envelope(record) else taxii_envelope_for_stix_bundle(record)
        if self.sender is not None:
            self.sender.send(envelope)
            return
        if self.collection_url is None:
            raise ValueError("TAXII collection_url is required when no sender is injected")
        _HttpxTaxiiSender(
            collection_url=self.collection_url,
            bearer_token=self.bearer_token,
            timeout_seconds=self.timeout_seconds,
        ).send(envelope)


@dataclass(frozen=True, slots=True)
class _HttpxTaxiiSender:
    collection_url: str
    bearer_token: str | None
    timeout_seconds: float

    def send(self, payload: JsonObject) -> None:
        httpx = importlib.import_module("httpx")
        headers = {
            "accept": "application/taxii+json;version=2.1",
            "content-type": "application/taxii+json;version=2.1",
        }
        if self.bearer_token is not None:
            headers["authorization"] = f"Bearer {self.bearer_token}"
        response = httpx.post(
            self.collection_url,
            headers=headers,
            json=payload,
            timeout=self.timeout_seconds,
        )
        response.raise_for_status()


class OpenTelemetrySpan(Protocol):
    """Small span protocol used to avoid importing OpenTelemetry in core paths."""

    def set_attribute(self, key: str, value: bool | int | float | str) -> None:
        """Set one span attribute."""


class OpenTelemetryTracer(Protocol):
    """Small tracer protocol for injected tests and optional runtime adapters."""

    def start_as_current_span(self, name: str) -> AbstractContextManager[OpenTelemetrySpan]:
        """Start a span context manager."""


class OpenTelemetryExporterUnavailable(RuntimeError):
    """Raised when the optional OpenTelemetry runtime dependencies are missing."""


@dataclass(slots=True)
class OpenTelemetrySpanSink:
    """OpenTelemetry span sink with lazy optional SDK imports."""

    tracer: OpenTelemetryTracer | None = None
    endpoint: str | None = None
    service_name: str = "actionlineage"
    tracer_name: str = "actionlineage.exporter"
    _provider: object | None = None

    def emit(self, record: JsonObject) -> None:
        tracer = self._ensure_tracer()
        event_type = str(record.get("actionlineage.event_type", "event"))
        with tracer.start_as_current_span(f"ActionLineage {event_type}") as span:
            for key, value in sorted(record.items()):
                span.set_attribute(key, _otel_attribute_value(value))

    def shutdown(self) -> None:
        """Flush and shut down an SDK provider created by this sink."""

        shutdown = getattr(self._provider, "shutdown", None)
        if callable(shutdown):
            shutdown()

    def _ensure_tracer(self) -> OpenTelemetryTracer:
        if self.tracer is not None:
            return self.tracer
        tracer, provider = _build_otel_tracer(
            endpoint=self.endpoint,
            service_name=self.service_name,
            tracer_name=self.tracer_name,
        )
        self.tracer = tracer
        self._provider = provider
        return tracer


def export_events(
    events: tuple[EventEnvelope, ...],
    *,
    profile: ExportProfile,
    sink: ExportSink,
    redaction_policy: RedactionPolicy | None = None,
) -> ExportResult:
    """Export events to a sink after redaction and mapping."""

    exported = 0
    for event in events:
        try:
            sink.emit(
                map_event_for_profile(
                    event,
                    profile=profile,
                    redaction_policy=redaction_policy,
                )
            )
        except Exception as exc:
            return ExportResult(
                ok=False,
                records_attempted=len(events),
                records_exported=exported,
                error=f"export sink failed after journal persistence: {type(exc).__name__}",
            )
        exported += 1
    return ExportResult(ok=True, records_attempted=len(events), records_exported=exported)


def map_event_for_profile(
    event: EventEnvelope,
    *,
    profile: ExportProfile,
    redaction_policy: RedactionPolicy | None = None,
) -> JsonObject:
    """Map one event into a supported export profile."""

    redacted = _redacted_event(event, redaction_policy=redaction_policy)
    if profile == ExportProfile.ACTIONLINEAGE_JSON:
        return redacted
    if profile == ExportProfile.OPENTELEMETRY:
        return otel_attributes_for_redacted_event(redacted)
    if profile == ExportProfile.OCSF:
        return _ocsf_record(redacted)
    if profile == ExportProfile.ECS:
        return _ecs_record(redacted)
    if profile == ExportProfile.SPLUNK_HEC:
        return _splunk_record(redacted)
    if profile == ExportProfile.SIGMA:
        return _sigma_record(redacted)
    if profile == ExportProfile.STIX:
        return _stix_record(redacted)
    if profile == ExportProfile.TAXII:
        return _taxii_record(redacted)
    raise ValueError(f"unsupported export profile: {profile}")


def otel_attributes_for_event(
    event: EventEnvelope,
    *,
    redaction_policy: RedactionPolicy | None = None,
) -> JsonObject:
    """Return redacted OpenTelemetry-style attributes without importing OTel."""

    redacted = _redacted_event(event, redaction_policy=redaction_policy)
    return otel_attributes_for_redacted_event(redacted)


def otel_attributes_for_redacted_event(redacted: JsonObject) -> JsonObject:
    """Return OpenTelemetry-style attributes from an already redacted event."""

    payload = redacted.get("payload")
    correlation = _object_field(redacted, "correlation")
    source = _object_field(redacted, "source")
    return {
        "actionlineage.event_id": redacted["event_id"],
        "actionlineage.event_type": redacted["event_type"],
        "actionlineage.spec_version": redacted["spec_version"],
        "actionlineage.trace_id": correlation["trace_id"],
        "actionlineage.run_id": correlation["run_id"],
        "actionlineage.source.component": source["component"],
        "actionlineage.payload_json": json.dumps(payload, sort_keys=True),
    }


def _redacted_event(
    event: EventEnvelope,
    *,
    redaction_policy: RedactionPolicy | None,
) -> JsonObject:
    policy = redaction_policy or RedactionPolicy()
    redacted = policy.apply(event_to_dict(event))
    if not isinstance(redacted, dict):
        raise ValueError("redaction policy must return an event object")
    return redacted


def _otel_attribute_value(value: object) -> bool | int | float | str:
    if isinstance(value, bool | int | float | str):
        return value
    return json.dumps(value, sort_keys=True)


def _build_otel_tracer(
    *,
    endpoint: str | None,
    service_name: str,
    tracer_name: str,
) -> tuple[OpenTelemetryTracer, object]:
    try:
        exporter_module = importlib.import_module(
            "opentelemetry.exporter.otlp.proto.http.trace_exporter"
        )
        resource_module = importlib.import_module("opentelemetry.sdk.resources")
        trace_module = importlib.import_module("opentelemetry.sdk.trace")
        trace_export_module = importlib.import_module("opentelemetry.sdk.trace.export")
    except ImportError as exc:
        raise OpenTelemetryExporterUnavailable(
            "install actionlineage[adapters] to use the OpenTelemetry span sink"
        ) from exc

    exporter_cls = exporter_module.OTLPSpanExporter
    resource_cls = resource_module.Resource
    provider_cls = trace_module.TracerProvider
    processor_cls = trace_export_module.SimpleSpanProcessor
    exporter = exporter_cls(endpoint=endpoint) if endpoint else exporter_cls()
    provider = provider_cls(
        resource=resource_cls.create(
            {
                "service.name": service_name,
                "actionlineage.export.canonical_source": "local_journal",
            }
        )
    )
    provider.add_span_processor(processor_cls(exporter))
    return provider.get_tracer(tracer_name), provider


def _ocsf_record(event: JsonObject) -> JsonObject:
    source = _object_field(event, "source")
    return {
        "metadata": {
            "product": {"name": "ActionLineage"},
            "version": event["spec_version"],
        },
        "class_name": "Agent Activity",
        "activity_name": event["event_type"],
        "time": event["occurred_at"],
        "uid": event["event_id"],
        "actor": event["principal"],
        "device": {"uid": source["instance_id"]},
        "raw_data": event,
    }


def _ecs_record(event: JsonObject) -> JsonObject:
    correlation = _object_field(event, "correlation")
    source = _object_field(event, "source")
    return {
        "@timestamp": event["occurred_at"],
        "event": {
            "id": event["event_id"],
            "kind": "event",
            "category": ["process"],
            "type": [event["event_type"]],
        },
        "trace": {"id": correlation["trace_id"]},
        "agent": {"name": source["component"]},
        "actionlineage": event,
    }


def _splunk_record(event: JsonObject) -> JsonObject:
    return {
        "time": event["occurred_at"],
        "source": "actionlineage",
        "sourcetype": "actionlineage:evidence",
        "event": event,
    }


def _sigma_record(event: JsonObject) -> JsonObject:
    return {
        "title": f"ActionLineage {event['event_type']}",
        "logsource": {"product": "actionlineage"},
        "detection": {
            "selection": {
                "event_type": event["event_type"],
                "event_id": event["event_id"],
            },
            "condition": "selection",
        },
        "fields": ["event_id", "event_type", "correlation.trace_id"],
    }


def _stix_record(event: JsonObject) -> JsonObject:
    correlation = _object_field(event, "correlation")
    observed_id = _stix_id("observed-data", str(event["event_id"]))
    note_id = _stix_id("note", str(event["event_id"]))
    bundle_id = _stix_id("bundle", str(event["event_id"]))
    return {
        "type": "bundle",
        "id": bundle_id,
        "spec_version": "2.1",
        "objects": [
            {
                "type": "observed-data",
                "id": observed_id,
                "created": event["occurred_at"],
                "modified": event["observed_at"],
                "first_observed": event["occurred_at"],
                "last_observed": event["observed_at"],
                "number_observed": 1,
                "object_refs": [],
                "x_actionlineage_event_id": event["event_id"],
                "x_actionlineage_event_type": event["event_type"],
                "x_actionlineage_trace_id": correlation["trace_id"],
                "x_actionlineage_run_id": correlation["run_id"],
                "x_actionlineage_redacted_event": event,
            },
            {
                "type": "note",
                "id": note_id,
                "created": event["observed_at"],
                "modified": event["observed_at"],
                "abstract": f"ActionLineage {event['event_type']}",
                "content": (
                    "ActionLineage exported this redacted event for sharing. "
                    "The append-only local journal remains canonical evidence."
                ),
                "object_refs": [observed_id],
            },
        ],
    }


def _taxii_record(event: JsonObject) -> JsonObject:
    return taxii_envelope_for_stix_bundle(_stix_record(event))


def taxii_envelope_for_stix_bundle(bundle: JsonObject) -> JsonObject:
    """Return a deterministic TAXII envelope for one STIX bundle."""

    objects = bundle.get("objects")
    if bundle.get("type") != "bundle" or not isinstance(objects, list):
        raise ValueError("TAXII export requires a STIX bundle with objects")
    return {
        "more": False,
        "objects": objects,
    }


def _is_taxii_envelope(record: JsonObject) -> bool:
    return isinstance(record.get("objects"), list) and isinstance(record.get("more"), bool)


def _stix_id(object_type: str, event_id: str) -> str:
    stable_id = uuid.uuid5(uuid.NAMESPACE_URL, f"actionlineage:{object_type}:{event_id}")
    return f"{object_type}--{stable_id}"


def _object_field(event: JsonObject, field: str) -> JsonObject:
    value = event.get(field)
    if not isinstance(value, dict):
        raise ValueError(f"event field must be an object: {field}")
    return value
