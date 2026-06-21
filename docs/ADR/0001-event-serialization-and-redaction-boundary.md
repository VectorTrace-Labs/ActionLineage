# ADR-0001: Event Serialization and Redaction Boundary

- Status: Accepted
- Date: 2026-06-21
- Owners: Marq Mercado

## Context

Prompt 02 introduces the first executable event envelope and redaction boundary.
The project needs deterministic domain serialization for tests and future
journal work, but the final hash-chain canonicalization algorithm is explicitly
out of scope for this slice.

The event model also needs a concrete compatibility stance. `v1alpha1` is still
pre-release, but accepting unreviewed persisted fields would make redaction and
schema validation harder to audit.

## Decision drivers

- Security
- Correctness
- Auditability
- Deterministic tests
- Future schema compatibility

## Options considered

### Strict checked-in schema

Known envelope objects reject fields that are not present in the checked-in JSON
schema and Pydantic boundary models. New optional fields are allowed only after
the schema and model are updated together.

Pros:

- Reduces the chance of persisting unreviewed secret-bearing fields.
- Keeps JSON schema tests and typed-model tests aligned.
- Makes review diffs explicit when the public event surface grows.

Cons:

- Consumers cannot blindly accept arbitrary additive fields in the current
  implementation.

### Permissive additive fields

The event schema and typed model would preserve unknown fields.

Pros:

- More flexible for experimental producers.

Cons:

- Harder to prove redaction coverage for unknown fields.
- Makes persisted evidence less reviewable.
- Weakens `AT-EVT-002` because unknown fields would be accepted before the
  compatibility contract is stable.

## Decision

Use a strict checked-in schema for persisted `v1alpha1` events. Additive fields
remain compatible only when they are added explicitly to the schema and typed
models. Known and future event type strings are allowed; unknown event types may
be preserved but must not be interpreted as safe by later consumers.

Domain serialization uses a deterministic JSON interface based on UTF-8,
`sort_keys=True`, compact separators, no NaN values, and UTC RFC 3339
timestamps ending in `Z`. This interface is named
`actionlineage.dev/json-deterministic-v0` and is an interim boundary for tests
and redacted persistence handoff. It is not the final journal hash-chain
canonicalization algorithm.

Before persistence, export, tracing, logging, or future hash input, callers must
pass events through the redaction boundary. Redaction is fail-closed: if
redaction cannot produce a JSON-compatible event object, serialization raises and
does not return the original value.

## Consequences

- The current JSON schema has `additionalProperties: false` for envelope value
  objects.
- `classification` is required because the product spec treats data
  classification as part of the event envelope.
- `integrity` is present now, but `previous_event_hash` and `event_hash` may be
  `null` until the journal hash-chain slice defines the final algorithm.
- Structured sensitive paths, sensitive field names, common secret patterns, and
  bounded capture metadata are part of the pre-persistence boundary.
- The final canonical hash-chain ADR may replace or refine
  `json-deterministic-v0`.

## Verification

- `AT-EVT-001` through `AT-EVT-005` are tested at the Pydantic and JSON schema
  boundary.
- `AT-RED-001` through `AT-RED-004` are tested at the domain serialization
  boundary.
- Canary secret tests assert that bearer-token fixtures do not appear in
  serialized event output or captured logs.
