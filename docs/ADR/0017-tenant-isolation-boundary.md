# ADR-0017: Tenant Isolation Boundary

- Status: Accepted
- Date: 2026-06-24
- Owners: Marq Mercado

## Context

Optional service mode has dependency-free tenant authorization primitives, but a
tenant claim is incomplete unless the associated storage and derived surfaces are
kept in tenant-specific namespaces.

ActionLineage remains local-first and does not claim a hosted SaaS control plane
in the public alpha. The boundary still matters because service deployments,
tests, and future adapters need a clear rule for how tenant IDs bind to canonical
journals, disposable projections, case exports, service logs, caches, and anchor
artifacts.

## Decision Drivers

- Require a known tenant before deriving tenant storage paths.
- Require both global service roles and tenant role bindings for tenant-scoped
  authorization.
- Keep tenant journals separate instead of mixing tenant evidence in one
  canonical local journal.
- Keep projections, exports, logs, caches, and anchors derived from the same
  tenant namespace.
- Reject path-like or ambiguous tenant IDs before they reach filesystem paths.
- Preserve the current preview label for optional service mode.

## Decision

Use `actionlineage.dev/tenant-storage-layout-v1` as the local tenant storage
layout boundary for optional service deployments.

`ServiceTenant`, `TenantRegistry`, and `TenantRoleBinding` remain the
authorization source. `TenantStorageLayout` and `TenantStorageScope` define the
local path namespace. A caller can derive a storage scope only for a tenant that
exists in the registry, and `require_tenant_storage_scope()` requires the
principal to satisfy both checks:

- the global service role grants the requested role; and
- the tenant has a binding for that principal with the requested role.

Tenant IDs used for storage scope derivation are single portable path segments:
ASCII letters, digits, `_`, and `-`, with a bounded length. Empty values,
relative path components, absolute-path material, dots, spaces, separators, and
other ambiguous characters are rejected before path construction.

Each tenant storage scope derives these surfaces from configured roots:

- `journal_path`: canonical local journal for the tenant.
- `database_path`: disposable projection for the tenant journal.
- `export_root`: case-export root for the tenant.
- `service_log_path`: service log path for the tenant.
- `cache_root`: rebuildable cache root for the tenant.
- `anchor_root`, `anchor_path`, and `anchor_log_path`: local anchor artifacts for
  the tenant journal.

Case export paths remain relative paths below the tenant export root or the
single-tenant service export root. Absolute paths, empty paths, `.`, `..`, and
traversal attempts fail before case-bundle generation.

## Boundary Semantics

- Tenant storage scopes are local deployment boundaries, not proof of SaaS
  isolation.
- Projection databases remain disposable and must be rebuilt or verified against
  the tenant journal before trusted reads.
- Logs, caches, exports, and anchors are derived or supporting artifacts. They do
  not replace the tenant journal as canonical evidence.
- A tenant binding does not authorize an endpoint by itself. Endpoint handlers
  must still check the relevant explicit service capability or role.
- Capability-only credentials do not satisfy global or tenant role checks.
- Unknown tenants fail closed before storage paths are returned.
- Future shared database, object-storage, or hosted multi-tenant service work
  needs a follow-up ADR and executable tests before stronger production
  isolation claims.

## Consequences

- Optional service wrappers can route tenant requests to deterministic
  per-tenant journal, projection, export, log, cache, and anchor paths.
- Tenant path derivation has a single validation point and traversal-resistant
  helper.
- The public alpha can claim only locally demonstrated tenant boundary
  primitives, not hosted multi-tenant production isolation.
- Existing single-tenant service deployments can continue using explicit
  `journal_path`, `database_path`, and `export_root`.

## Verification

- `tests/service/test_service_mode.py` covers tenant storage scope derivation,
  known-tenant checks, strict tenant ID validation, export path confinement, and
  global-role plus tenant-binding authorization.
- Release-readiness tests require this ADR, operations guidance, maturity
  labels, scorecard entries, and follow-up tracker status to remain aligned.
