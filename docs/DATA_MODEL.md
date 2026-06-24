# Lineage Data Model

## Event envelope

Every persisted record uses the same strict envelope and a typed or documented payload.

```json
{
  "spec_version": "actionlineage.dev/v1alpha1",
  "event_id": "evt_...",
  "event_type": "side_effect.verified",
  "occurred_at": "2026-06-21T18:42:12.123456Z",
  "observed_at": "2026-06-21T18:42:12.127901Z",
  "source": {
    "component": "local-verifier",
    "instance_id": "demo_01",
    "version": "0.1.0"
  },
  "correlation": {
    "trace_id": "trace_...",
    "span_id": null,
    "run_id": "run_...",
    "session_id": null
  },
  "causality": {
    "parent_event_id": "evt_observed",
    "root_event_id": "evt_intent",
    "sequence": 12
  },
  "principal": {
    "principal_id": "agent_demo",
    "principal_type": "agent",
    "on_behalf_of": "user_demo",
    "model_id": null,
    "credential_id": "none"
  },
  "classification": {
    "sensitivity": "internal",
    "trust": "trusted"
  },
  "payload": {},
  "integrity": {
    "previous_event_hash": "sha256:...",
    "event_hash": "sha256:...",
    "canonicalization": "actionlineage.dev/json-deterministic-v0"
  }
}
```

`actionlineage.dev/json-deterministic-v0` is the active public-alpha journal
serialization boundary. ADR-0013 reserves
`actionlineage.dev/json-canonicalization-v1` as a future portable
canonicalization boundary. Checked-in conformance vectors and runtime migration
guardrails now exist, but v1 is still rejected for persisted evidence hashes
until a future migration ADR explicitly adopts it.

## Principal types

- `human`
- `service`
- `agent`
- `model`
- `workload`
- `credential`
- `unknown`

Preserve initiating principal, executing principal, model identity, and effective credential as separate fields when all are known.

## Resource types

- `file`
- `url`
- `network_destination`
- `process`
- `host`
- `identity`
- `cloud_resource`
- `database_record`
- `message`
- `secret`
- `unknown`

Resources should carry stable identifiers where possible, plus classification and trust metadata.

## Event types

### Run and intent lifecycle

- `agent.intent.recorded`
- `agent.run.started`
- `agent.run.completed`
- `agent.run.failed`

### Neutral tool execution lifecycle

- `tool.execution.requested`
- `tool.execution.authorized`
- `tool.execution.dispatched`
- `tool.execution.acknowledged`
- `tool.execution.not_dispatched`

These states are separate. Acknowledgement is not proof that a side effect occurred.

### Side-effect evidence lifecycle

- `side_effect.observed`
- `side_effect.verified`
- `side_effect.unverified`
- `side_effect.timed_out`
- `side_effect.conflict_detected`

### Compatibility and adapter events

- `agent.tool.discovered`
- `agent.tool.schema_changed`
- `agent.tool.call.requested`
- `agent.tool.call.started`
- `agent.tool.call.completed`
- `agent.tool.call.failed`
- `agent.tool.call.denied`
- `policy.evaluation.started`
- `policy.decision`
- `approval.requested`
- `approval.resolved`

These remain valid, but MCP and enforcement code belongs behind adapters.

### Normalization, alerts, and system health

- `resource.observed`
- `action.normalized`
- `lineage.alert.created`
- `recorder.degraded`
- `projection.rebuilt`
- `integrity.verification.failed`

## Evidence links

Verification events should include an evidence link payload:

```json
{
  "evidence_link": {
    "subject_event_id": "evt_tool_ack",
    "relationship": "corroborates",
    "evidence_event_id": "evt_receiver_observed",
    "corroboration_type": "independent_observer",
    "observer_identity": "local_receiver_fixture",
    "confidence": 0.95,
    "verification_status": "verified",
    "limitations": ["local deterministic fixture only"]
  }
}
```

Supported relationships:

- `corroborates`
- `contradicts`
- `observes`
- `limits`

Supported corroboration types:

- `independent_observer`
- `post_action_readback`
- `fixture_oracle`
- `self_reported`
- `unknown`

ADR-0012 governs when an observation may be described as
`independent_observer`. A trust label alone is not enough; production
independence requires a reviewed declaration of producer identity, collection
method, boundaries, shared dependencies, blind spots, failure behavior,
redaction scope, policy version, owner, and review date.

The `verify_observation()` helper defaults to `unknown` corroboration. Callers
that request `independent_observer` through the helper must provide an
`ObserverAttestationDeclaration` that is current, matches the observer, covers
the subject action/resource scope, declares all required independence
boundaries as independent, and has no shared dependencies. Missing, stale,
shared, incomplete, or out-of-scope declarations fail closed before an
independent-observer evidence link is produced.

Supported verification statuses:

- `unknown`
- `unverified`
- `timed_out`
- `conflicting`
- `observed`
- `verified`

Absence of an observation is not proof that a side effect did not occur.

## Tool identity

Tool identity is the tuple:

```text
adapter identity + tool name + canonical descriptor hash when descriptor data is available
```

The descriptor hash should cover security-relevant descriptor fields, including description, input schema, output schema, annotations, and selected metadata. MCP is one possible source of descriptors, not a core dependency.

## Content capture

Default to metadata and digests. Full content capture must be opt-in and bounded.

For arguments and results, support:

- Structured field allowlists.
- Sensitive-field annotations.
- Redacted placeholders.
- Original byte length.
- Truncation indicator.
- SHA-256 digest of the pre-redaction fixture only when doing so does not create a new sensitive identifier.

## Compatibility

During `v1alpha1`:

- Additive optional fields are allowed only through explicit schema and model updates.
- Persisted events that include fields not present in the checked-in schema are rejected by the current domain model.
- Renames and semantic changes require a new schema version.
- Consumers must reject unknown major versions.
- Unknown event types may be preserved but not interpreted as safe.

The public compatibility policy is maintained in
[`COMPATIBILITY.md`](COMPATIBILITY.md). Golden journal fixtures under
`tests/fixtures/journals/` prove that accepted baseline, evidence-plane, and
legacy adapter events remain readable.

The event envelope schema remains `schemas/actionlineage-event-v1alpha1.schema.json`.
Payload-level evidence links are documented and validated separately in
`schemas/evidence-link-v1alpha1.schema.json` so `v1alpha1` can preserve
envelope compatibility.

## Local journal integrity

The local journal stores newline-delimited canonical event JSON. Verification
requires each record to exactly match the deterministic serialized event bytes
plus one `\n`; duplicate keys, non-finite numeric tokens, CRLF conversion,
added whitespace, reordered keys, trailing bytes, and multiple JSON values on a
line fail before that record is accepted into a verified snapshot. Each appended
event records the previous persisted event hash in
`integrity.previous_event_hash` and its own SHA-256 digest in
`integrity.event_hash`. A record is considered complete only after its newline
terminator has been written; verification reports `truncated_record` for a
final record missing that terminator and stops at the prior verified prefix.

This is local byte-canonical verification under
`actionlineage.dev/json-deterministic-v0`. It is not yet a claim of portable
cross-language canonical JSON or RFC 8785/JCS conformance.

The hash input is the redacted persisted event with `integrity.event_hash` set to `null`. This avoids recursive hashing while binding every other event field, including `previous_event_hash`, into the digest.

This local hash chain is tamper-evident only relative to the journal bytes and any trusted expected record count or last hash supplied to verification. A local attacker who can rewrite the entire journal and any local root anchor can produce a new self-consistent chain. Tail truncation cannot be detected without a trusted expected record count or last event hash.

## SQLite query projection

The SQLite projection is a disposable query index, not canonical evidence. It is rebuilt from a journal only after the journal verifier succeeds.

The projection schema uses SQLite `PRAGMA user_version = 2` and two tables:

- `projection_metadata`: key/value rebuild metadata, including schema version, source journal path, indexed record count, and last event hash.
- `events`: one row per event ID with denormalized timeline fields, optional verification/evidence-link index fields, and full canonical event JSON.

Event indexing is idempotent for an already indexed event with the same event ID, journal record number, and event JSON. A repeated event ID with different content is a projection error rather than an overwrite.

Timeline queries support exactly one selector: `trace_id` or `run_id`. Results are ordered by `occurred_at`, then `causality.sequence`, then journal record number, then `event_id`.

Incident export returns JSON containing the selector, event count, documented timeline order, and the full projected event objects.

Case bundle export publishes a derived private directory containing
`case.json`, `events.ndjson`, `report.md`, and `manifest.json`. The manifest
binds the artifact sizes and SHA-256 digests to the same verified
journal/projection summary used for the incident export. The bundle is
reviewable local evidence, not a replacement for the append-only journal or a
future external signature/checkpoint.
