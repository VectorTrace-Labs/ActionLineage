# Compatibility Policy

## Scope

This policy governs public ActionLineage event compatibility before the 1.0
schema freeze. It applies to checked-in journals, generated demo journals, and
fixtures used by contracts, detections, replay, and incident export.

Policy version: `actionlineage.dev/compatibility-policy-v1`

## Supported event versions

The current package reads:

- `actionlineage.dev/v1alpha1`

The event envelope is strict. Unknown envelope fields are rejected by the typed
model and JSON schema. Unknown event type strings are readable and preserved, but
they do not receive trusted semantics merely because they use a supported
envelope version.

## Read guarantees

Within `v1alpha1`, ActionLineage must continue to read and verify:

- Accepted baseline journals for event, redaction, journal, and projection work.
- Evidence-plane journals with neutral lifecycle events and evidence links.
- Legacy adapter journals that use `agent.tool.*`, `policy.*`, and approval
  compatibility events.

Golden compatibility fixtures live under `tests/fixtures/journals/`.

## Allowed additive changes

Allowed changes in `v1alpha1`:

- New event type strings, when unknown consumers can preserve them without
  interpreting them as safe behavior.
- New payload fields for existing event types, when they are optional and do not
  change existing field meanings.
- New payload helper objects, such as `payload.evidence_link`, when represented
  inside the existing envelope.
- New projection indexes, because projections are disposable and rebuildable from
  verified journals.

## Changes that require a migration ADR

Require a new ADR and, when applicable, a new schema version:

- Renaming or removing envelope fields.
- Changing the meaning of existing envelope fields.
- Changing canonical serialization or journal hash input.
- Moving evidence links from payloads to envelope-level fields.
- Requiring previously optional payload fields for supported event streams.
- Reclassifying unknown event types as safe or policy-approved behavior.

## Unknown event handling

Consumers must preserve unknown event types as evidence. They must not treat an
unknown event type as proof that an action was allowed, dispatched, observed, or
verified.

The public helper `assess_event_compatibility()` reports whether an event is
readable and whether this package understands its semantics.

## Error handling

Public parse helpers raise redacted ActionLineage exceptions. Error messages must
not echo raw serialized payloads, authorization headers, bearer tokens, API keys,
passwords, private keys, or session cookies.

Journal verification reports malformed records with sanitized issue messages.
