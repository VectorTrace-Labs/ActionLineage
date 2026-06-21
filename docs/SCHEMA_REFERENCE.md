# Schema Reference

ActionLineage public alpha supports the `actionlineage.dev/v1alpha1` event envelope.
The JSON Schema lives at `schemas/actionlineage-event-v1alpha1.schema.json`.

## Envelope Fields

- `event_id`: stable event identifier.
- `spec_version`: schema version, currently `actionlineage.dev/v1alpha1`.
- `event_type`: known enum value or preserved future string.
- `occurred_at`: UTC occurrence time.
- `observed_at`: UTC recorder observation time.
- `source`: component, instance, and version that recorded the event.
- `correlation`: trace and run IDs.
- `causality`: root event, parent event, and sequence.
- `principal`: human, agent, service, workload, model, or delegated identity.
- `classification`: sensitivity and trust level.
- `payload`: event-specific JSON object.
- `integrity`: canonicalization and journal hash metadata.

## Evidence Links

Evidence links are payload-level objects in `v1alpha1`:

- `subject_event_id`
- `relationship`
- `evidence_event_id`
- `corroboration_type`
- `observer_identity`
- `confidence`
- `verification_status`
- `limitations`

Envelope-level evidence links are deferred to a future schema migration and
require an ADR.

## Compatibility

Supported journals and fixtures must remain readable. New payload fields may be
added when old readers can preserve them safely. Envelope field changes require
a new schema version or documented migration.
