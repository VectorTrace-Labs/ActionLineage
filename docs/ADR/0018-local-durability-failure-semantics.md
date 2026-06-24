# ADR-0018: Local Durability Failure Semantics

- Status: Accepted
- Date: 2026-06-24
- Owners: Marq Mercado

## Context

ActionLineage now has executable coverage for several local durability paths:
journal append preflight and write failures, byte-canonical verification,
verified-prefix recovery, projection rebuild failures after committed appends,
service-ingest duplicate retry recovery, case-bundle staging and publication
failure, local anchors, archive manifests, external-attestation sidecars, and
the benchmark boundary for future append caches.

The remaining risk is semantic drift. If future work adds case-bundle
signatures, longer-running recovery fault injection, segmented journals,
checkpoint indexes, or append caches before the current local failure semantics
are explicit, the project could accidentally overclaim durability or treat a
derived artifact as canonical evidence.

## Decision Drivers

- Keep the append-only journal as canonical evidence.
- Keep projections, case bundles, append caches, and external checkpoints as
  derived or externally qualified surfaces.
- Preserve explicit partial-success behavior for local service batches.
- Avoid claiming all-or-nothing transactions, WORM enforcement, hardware-backed
  signing, or production recovery guarantees from local-only tests.
- Give future fault-injection and cache work a concrete policy to extend.

## Decision

Accept `actionlineage.dev/local-durability-policy-v1` as the local durability
failure-semantics boundary for the public alpha.

The policy is implemented in `src/actionlineage/journal/durability.py` and
exported through `actionlineage.journal` and the top-level `actionlineage`
package. It records reviewed local durability fault classes, the allowed
outcome for each fault, the canonical journal state, derived-artifact state,
retry guidance, and claim boundary.

The policy deliberately separates these states:

- **Canonical journal state**: only verified journal bytes, record count,
  terminal hash, and trusted anchors can support canonical evidence claims.
- **Derived state**: projections, case bundles, desktop bundles, summaries, and
  future append caches can be stale, unpublished, ignored, or rebuilt without
  changing canonical evidence.
- **External status**: unavailable external checkpoint verification remains
  `unknown`, `stale`, or `unverified`; it is never silently converted to
  verified.

Future code that changes local durability behavior must either satisfy this
policy or update it with tests and documentation in the same change.

## Current Policy Coverage

`actionlineage.dev/local-durability-policy-v1` covers:

- Append preflight failure before a candidate event becomes trusted evidence.
- Append write, flush, or `fsync` failure where only a verified prefix may be
  usable.
- Partial records without newline terminators.
- Projection rebuild failure after a committed journal append.
- Service-process crash after append before projection rebuild.
- Multi-record service batches with a committed prefix and later failure.
- Case-bundle staging failures and publish collisions.
- Future append-cache mismatches.
- External checkpoint verifier outage.

## Consequences

- Case-bundle signatures are still future work. Current bundle manifests reserve
  signature/checkpoint fields, but unsigned local bundles remain derived export
  artifacts.
- Longer-running crash and filesystem fault injection should target the policy
  fault classes before expanding public durability claims.
- Future segmented journal or append-cache designs must treat caches as
  rebuildable and must fail closed for stale, tampered, or mismatched cache
  state.
- Existing `v1alpha1` event bytes and journal records do not change.
- Optional service mode remains preview and retains explicit partial-success
  semantics.

## Verification

- `tests/journal/test_durability_policy.py` asserts the policy version,
  deterministic JSON shape, required fault coverage, fail-closed lookup
  behavior, immutability, and top-level exports.
- Release-readiness tests require this ADR, API docs, journal integrity docs,
  operations docs, scorecard, and follow-up tracker to preserve the local
  durability boundary.
- Existing journal, projection, service, and case-bundle tests continue to prove
  the current local behavior behind the policy.
