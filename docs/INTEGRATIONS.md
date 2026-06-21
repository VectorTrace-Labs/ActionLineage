# Telemetry And SIEM Integrations

The local journal remains canonical evidence. Exporters are downstream mirrors;
export failure must not delete or rewrite journal records.

## Implemented Core Mappings

- ActionLineage JSON.
- OCSF-style record.
- ECS/Elastic-style record.
- Splunk HEC-style record.
- Sigma-style detection skeleton.
- STIX-style bundle with observed-data and note objects.
- TAXII 2.1-style envelope for STIX object sharing.
- OpenTelemetry-style redacted attributes.

All mappings run through `RedactionPolicy` before reaching a sink.
The local OpenTelemetry semantic-convention proposal is documented in
`integrations/opentelemetry/actionlineage-semconv-v0.json` and
`docs/OPENTELEMETRY_SEMCONV.md`.

## Sinks

- `FileSink`: deterministic NDJSON output for CI and demos.
- `WebhookSink`: injectable sender interface for optional webhook adapters.
- `OpenTelemetrySpanSink`: optional span sink that accepts an injected tracer or
  lazily imports the OpenTelemetry SDK/OTLP HTTP exporter from the `adapters`
  extra when first used.
- `TaxiiHttpSink`: optional TAXII object-collection sink that accepts an
  injected sender for tests or lazily imports `httpx` from the `adapters` extra
  when posting to a configured collection URL.

The core package does not open network connections for webhook exports. The
OpenTelemetry sink is opt-in runtime behavior; collector failures are reported
as export failures after journal persistence and never rewrite local evidence.
The TAXII sink follows the same journal-first rule and should be used with
redacted STIX or TAXII export profiles.

Example:

```python
from actionlineage import ExportProfile, OpenTelemetrySpanSink, export_events

result = export_events(
    events,
    profile=ExportProfile.OPENTELEMETRY,
    sink=OpenTelemetrySpanSink(endpoint="http://collector.example.invalid/v1/traces"),
)
assert result.as_dict()["journal_first"] is True
```

TAXII example with an injected sender:

```python
from actionlineage import ExportProfile, TaxiiHttpSink, export_events

result = export_events(
    events,
    profile=ExportProfile.TAXII,
    sink=TaxiiHttpSink(sender=my_reviewed_sender),
)
assert result.as_dict()["journal_first"] is True
```

## Framework Adapter Boundary

`actionlineage.adapters.frameworks` provides dependency-free helpers for mapping
tool callbacks from OpenAI Agents SDK, LangChain, LlamaIndex, CrewAI, shell,
browser automation, and local function runtimes into neutral evidence records.
The helpers do not import those framework SDKs. Concrete runtime integrations
should depend on the SDKs behind optional extras and emit records through this
boundary.

The framework adapter boundary records:

- Transport-neutral descriptor identity from framework name, tool name, schema,
  version, and selected metadata.
- `tool.execution.requested`, `tool.execution.dispatched`,
  `tool.execution.acknowledged`, and `tool.execution.not_dispatched` lifecycle
  records.
- Delegated identity, resources, argument digests, and framework invocation IDs
  without requiring raw tool arguments or raw tool results.

A framework acknowledgement remains an acknowledgement only. Side effects still
require observer or verifier evidence before they are `observed` or `verified`.

## Extension Packs

`actionlineage.packs` validates local manifests for reviewed adapter,
detection, contract, observer, export-profile, and lab-corpus artifacts. Packs
are useful for distribution and CI review; they do not execute code, fetch
remote content, or make marketplace trust claims. See `docs/PACKS.md`.

## Trust Boundary

Exported records are useful for SIEM correlation and downstream workflows, but
they are not canonical. Investigations should refer back to the append-only local
journal and its verification metadata when possible.

## Mapping References

Profile mapping references live in `integrations/mappings/`. They are reviewed
golden descriptions rather than external standard conformance claims. The
STIX/TAXII profiles are local deterministic mappings and do not implement a
TAXII server.
