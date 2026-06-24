# ADR-0007: Optional Service Auth Model

- Status: Proposed
- Date: 2026-06-21
- Owners: Marq Mercado

## Context

ActionLineage is local-first, but public roadmap planning includes optional service
mode for ingest, query, export, health, contract validation, and detection
evaluation.

Service mode must not change the journal trust model. The append-only local
journal remains canonical evidence.

## Decision

Provide a small service auth model:

- Static bearer tokens for local/dev service deployments.
- JWT authentication with caller-configured verification keys, issuer, audience,
  accepted algorithms, and role-claim mapping.
- OIDC/JWKS authentication through PyJWT's `PyJWKClient` behind the optional
  service dependency set.
- Roles: `read`, `write`, `export`, and `admin`.
- Roles are named bundles of explicit capabilities, not an ordered privilege
  ladder. Capability checks include `events:read`, `events:write`,
  `journal:verify`, `projections:rebuild`, `detections:run`, `cases:read`,
  `cases:export`, `admin:configure`, and `tenants:manage`.
- `admin` grants every current capability. `read`, `write`, and `export` do not
  inherit from each other.
- OIDC discovery, tenant provisioning, and multi-tenant RBAC remain future
  optional service work.

The FastAPI application factory lives under `actionlineage.service` and imports
FastAPI lazily, so core library imports do not require service dependencies.

## Consequences

Local service demos can run with deterministic static tokens. Production
deployments can use JWT/OIDC verification, but must configure trusted issuers,
audiences, key rotation, TLS, and role claims before exposing the service beyond
localhost or a trusted network.

Projection migrations remain service/storage concerns. Journals remain canonical
and are not migrated in place.

## Verification

Tests cover token authentication, JWT/OIDC role and capability claim mapping,
invalid-signature handling, capability checks, local health/degraded state, and
the optional app factory.
