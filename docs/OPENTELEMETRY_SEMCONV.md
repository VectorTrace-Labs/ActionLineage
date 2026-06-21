# OpenTelemetry Semantic Convention Proposal

ActionLineage includes a local OpenTelemetry semantic-convention proposal at
`integrations/opentelemetry/actionlineage-semconv-v0.json`.

The proposal documents the redacted attributes emitted by
`otel_attributes_for_event` and `OpenTelemetrySpanSink`:

- `actionlineage.event_id`
- `actionlineage.event_type`
- `actionlineage.spec_version`
- `actionlineage.trace_id`
- `actionlineage.run_id`
- `actionlineage.source.component`
- `actionlineage.payload_json`

This is a proposal artifact for review and integration testing. It is not an
upstream OpenTelemetry standard. Exported spans are downstream mirrors of
redacted evidence; the append-only local journal remains canonical evidence.

Exporting a span does not verify a side effect. A successful tool response is an
acknowledgement only, and side-effect verification still requires independent or
explicitly identified corroborating evidence.
