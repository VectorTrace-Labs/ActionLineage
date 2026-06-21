# ADR-0005: Optional Policy Runtime Fail Behavior

- Status: Proposed
- Date: 2026-06-21
- Owners: Marq Mercado

## Context

ActionLineage treats policy enforcement as an optional adapter capability, not a
domain-core requirement. MCP and other tool adapters still need precise behavior
when policy evaluation allows, denies, requires approval, runs in dry-run mode,
or degrades.

The evidence plane must preserve the distinction between requested, authorized,
dispatched, acknowledged, observed, and verified. A denied or not-dispatched
tool call must not be forwarded downstream.

## Decision

Define policy runtime primitives under `actionlineage.adapters`, outside the
domain core:

- `allow` and `dry_run` permit dispatch.
- `deny` does not permit dispatch and must produce not-dispatched evidence.
- `require_approval` permits dispatch only with a valid approval artifact.
- `error` follows an explicit adapter failure mode.
- `fail_closed` blocks dispatch.
- `fail_open` permits dispatch but must emit degraded evidence.

Approval artifacts bind subject event, scope, expiry, nonce, approver, and the
related decision event when available. Adapter runtimes must reject approval
nonce replay.

## Consequences

MCP and future tool adapters can share policy semantics without importing policy
engines into the domain, journal, or projection packages.

Fail-open behavior is visible as degraded evidence and cannot be mistaken for a
normal allow decision.

Policy results remain evidence. They do not prove that a side effect happened;
side-effect verification still requires independent or explicitly identified
corroboration.

## Verification

Adapter tests cover denied calls not being dispatched, explicit fail-open and
fail-closed behavior, approval replay rejection, malformed result rejection, and
core import-boundary enforcement.
