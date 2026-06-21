# ADR-0006: Minimum Corroboration Threshold

- Status: Proposed
- Date: 2026-06-21
- Owners: Marq Mercado

## Context

ActionLineage distinguishes tool acknowledgement from side-effect observation
and verification. A successful tool response is not proof that a side effect
occurred.

The evidence plane needs a repeatable threshold for when an outcome may be
called `verified`.

## Decision

An outcome may be represented as `verified` only when it is corroborated by one
of these evidence categories:

- Independent observer evidence.
- Post-action readback evidence.
- Reviewed fixture oracle evidence.

Self-reported tool output may be recorded, but it remains `unverified` unless it
is explicitly corroborated by one of the categories above.

Timed-out, unavailable, and conflicting observations are first-class outcomes.
Absence of an observation must be reported as missing or unverified evidence,
not as proof that no side effect occurred.

## Consequences

Observer adapters must emit limitations and trust labels. Verification helpers
must preserve conflicts and timeouts instead of overwriting them with a single
success/failure boolean.

Local deterministic observers are suitable for demos and tests, but production
deployments should document observer trust boundaries and failure modes.

## Verification

Tests cover verified, unverified, timed-out, conflicting, unavailable, and
self-reported outcomes. Report wording must avoid proof-of-absence claims.
