# Operations Guide

ActionLineage remains local-first. Service mode is optional and should preserve
the local append-only journal as canonical evidence.

## Health States

`check_local_health()` reports:

- `ok` when the journal verifies and the configured projection exists.
- `degraded` when journal verification fails or a configured projection is
  missing.

Health checks do not mutate journals or rebuild projections.

## Service Mode

The optional service factory is `actionlineage.service.create_app()`.

Local development can use `StaticTokenAuthenticator`:

```python
from actionlineage.service import ServicePrincipal, ServiceRole, StaticTokenAuthenticator

authenticator = StaticTokenAuthenticator(
    tokens={
        "local-token": ServicePrincipal(
            principal_id="local-admin",
            roles=frozenset({ServiceRole.ADMIN}),
        )
    }
)
```

Service deployments that already have reviewed JWT infrastructure can use
`JwtAuthenticator` with a configured verification key, issuer, audience, and
accepted algorithms:

```python
from actionlineage.service import JwtAuthenticator

authenticator = JwtAuthenticator(
    verification_key=trusted_public_key_or_secret,
    algorithms=("RS256",),
    issuer="https://issuer.example.com/",
    audience="actionlineage-service",
)
```

OIDC/JWKS verification is available through `OidcJwtAuthenticator`, which uses
PyJWT's `PyJWKClient` from the optional service dependencies. The service does
not perform OIDC discovery or tenant provisioning; production deployments must
review issuer, audience, key rotation, TLS, and role-claim mapping before
exposure beyond trusted networks.

Install optional service dependencies before running service mode:

```bash
uv sync --extra service
```

Service endpoints:

- `GET /health`
- `GET /timeline`
- `GET /events`
- `POST /ingest`
- `POST /contracts/validate`
- `POST /detections/evaluate`
- `POST /export-case`

`/ingest` requires `write`; timeline, events, contract validation, and detection
evaluation require `read`; case export requires `export`.

Service-mode case exports are written under a configured export root. Set
`ACTIONLINEAGE_EXPORT_ROOT` for environment-driven service startup; otherwise
the runtime uses `/data/exports`. The `/export-case` endpoint accepts a relative
`output_dir` below that root and rejects absolute paths, `.` components, and
`..` traversal. Existing case bundle files are not overwritten.

### Tenant Boundaries

`ServiceTenant`, `TenantRegistry`, `TenantRoleBinding`, and
`require_tenant_role()` provide dependency-free tenant authorization primitives
for optional service deployments. A principal must have both the global service
role and a tenant binding that grants the requested role. Missing tenants,
missing bindings, and insufficient tenant roles are explicit denial decisions.

These helpers do not create a hosted SaaS control plane, provision tenants, or
move journals into a shared database. Deployment code remains responsible for
using separate journal/projection paths or storage prefixes for each tenant.

## Backup And Restore

- Back up the journal and trusted anchor files together.
- Keep `JournalArchiveManifest` files with archived journal objects and verify
  them during restore drills.
- Projection databases can be rebuilt and should not be treated as canonical.
- Export case bundles for sharing, but preserve journal verification metadata.

## Deployment Notes

The repository includes Docker, Compose, Kubernetes, and Helm examples for local
or lab evaluation of optional service mode.

Deployment examples are preview support surfaces. They prove packaging and smoke
behavior for the public alpha, but they do not make the service production-supported
or replace deployment-specific reviews for authentication, storage, network
policy, observability, retention, and incident response.

Build and run the local Compose service:

```bash
docker compose -f deploy/docker/compose.yaml up --build
```

The Compose example starts Uvicorn with
`actionlineage.service.runtime:create_service_app_from_env --factory`, stores
the local journal and projection under `/data`, and uses the placeholder
`local-token`. Replace the token before any shared environment.

Apply the static Kubernetes example:

```bash
kubectl apply -f deploy/kubernetes/actionlineage-service.yaml
```

Install the Helm chart:

```bash
helm install actionlineage deploy/helm/actionlineage \
  --set serviceRuntime.token=local-token
```

The Kubernetes and Helm examples mount a persistent volume at `/data`, keep the
append-only journal at `/data/actionlineage.journal`, keep the projection at
`/data/projection.sqlite`, run as a non-root user, and read the bearer token
from a Kubernetes Secret.

## PostgreSQL Projection

SQLite remains the default local projection. For service deployments that need a
shared query backend, `rebuild_postgres_projection()` can rebuild a PostgreSQL
projection from the verified local journal through an executor supplied by the
runtime integration:

```python
from pathlib import Path

from actionlineage.projection import rebuild_postgres_projection

rebuild_postgres_projection(Path("/data/actionlineage.journal"), executor)
```

The executor is intentionally a tiny protocol so teams can use psycopg,
SQLAlchemy, or an internal database wrapper behind optional dependencies. The
PostgreSQL projection is still disposable query state; the append-only journal
and trusted anchors remain canonical evidence.

## Object Storage Archives

ActionLineage can create a local archive manifest for a journal object:

```bash
uv run actionlineage journal create-archive-manifest \
  /data/actionlineage.journal /data/actionlineage.archive.json \
  --object-uri s3://example-bucket/actionlineage.journal \
  --retention-mode governance
```

Upload and retention enforcement remain deployment responsibilities. During
restore, download the journal and manifest, then run:

```bash
uv run actionlineage journal verify-archive-manifest \
  /data/actionlineage.archive.json \
  --journal /data/actionlineage.journal
```

Production deployments still need reviewed TLS, external secret management,
backup, retention, monitoring, ingress, network policy, and
organization-specific authentication configuration.
