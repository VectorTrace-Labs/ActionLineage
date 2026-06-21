# ADR-0003: Evidence Plane Pivot

- Status: Proposed
- Date: 2026-06-21
- Owners: Marq Mercado

## Context

ActionLineage is pivoting from a gateway-first MCP firewall into a vendor-neutral evidence and detection plane for tool-using agents.

The current implementation already provides the accepted local evidence baseline:

- Versioned event model.
- Redaction boundary.
- Append-only local journal.
- Hash-chain verification.
- Rebuildable SQLite projection.

MCP interception and policy enforcement remain useful, but they are optional adapters rather than the center of the product.

## Decision

Make the append-only local journal the canonical evidence store. Keep the domain core independent of MCP, OpenTelemetry, model providers, policy engines, and gateway transports.

Represent requested, authorized, dispatched, acknowledged, observed, and verified as separate states. A successful tool response is only acknowledgement unless it is corroborated by independent or explicitly identified evidence.

Represent side-effect verification through payload-level evidence links in `v1alpha1` events. Defer envelope-level evidence-link changes until a schema migration is approved.

MCP interception, OpenTelemetry export, and policy enforcement are optional adapters that translate into the neutral evidence model.

## Consequences

Existing journals and fixtures remain readable unless a future schema migration is explicitly approved.

New side-effect and verification events are added without renaming existing MCP-era events.

Policy denial remains testable, but it is no longer the primary demo proof.

Product claims must avoid proof-of-absence, tamper-proof, forensically complete, or universally secure wording.

## Verification

Existing baseline checks must remain green throughout migration.

New acceptance tests must cover unknown, unverified, timed-out, conflicting, observed, and verified outcomes.

Adapter tests must prove MCP/policy behavior without importing adapter dependencies into domain core.
