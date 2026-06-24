# Operations Guide

ActionLineage remains local-first. Service mode is optional and should preserve
the local append-only journal as canonical evidence.

## Health States

`/live` reports process-level liveness only. It returns HTTP 200 while the
service process can serve requests and does not verify journal integrity.

`/ready` verifies that required local state is usable. It returns HTTP 503 when
the configured journal cannot be locked/read or when journal verification fails.
`/health` remains as a compatibility alias for readiness and therefore also
uses fail-closed HTTP status.

`check_local_health()` reports:

- `ok` when the journal verifies and the configured projection exists.
- `degraded` when journal verification fails, the journal cannot be checked, or
  a configured projection is missing.

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

- `GET /live`
- `GET /ready`
- `GET /health` compatibility readiness alias
- `GET /timeline`
- `GET /events`
- `POST /ingest`
- `POST /contracts/validate`
- `POST /detections/evaluate`
- `POST /export-case`

`/ingest` requires the `write` capability; capability-only principals must
grant both `events:write` and `projections:rebuild` in the current alpha service
model. Timeline, events, contract validation, and detection evaluation require
`read` capabilities; case export requires `cases:export`. Journal-dependent
service endpoints fail closed with HTTP 503 when the internal journal does not
verify.

Service-created events include server-controlled `payload.ingested_by`
provenance. It records the authenticated service principal, role set,
authentication method, non-secret credential identifier, request ID, server
receipt time, and service instance identity. Clients cannot supply
`ingested_by`; requests that try to do so are rejected. Submitted `source` and
`principal` fields remain evidence assertions from the submitted record and are
not treated as authenticated transport identity. Older records without
`payload.ingested_by` remain readable and are identified as legacy records
without invented authenticated identity.

Write-role credentials cannot assert `classification.trust=trusted`. Trusted
evidence assertions require an admin service role in this alpha service model;
unprivileged attempts are rejected.

`/ingest` idempotency is evaluated against the canonical local journal, not the
SQLite projection. The service holds the local journal append lock while it
checks existing idempotency fingerprints, assigns journal sequences, and appends
new events. Replaying the same idempotency key with the same request fingerprint
returns `duplicate`; reusing the key for a different record returns HTTP 409 and
`conflict`. A mixed batch with at least one committed record and at least one
record-level failure returns HTTP 207 with per-record outcomes. If the journal
append commits but the rebuildable projection fails afterward, the response is
HTTP 503 with `journal_committed: true` and `projection.state: "stale"`; clients
can retry safely with the same idempotency key. A duplicate retry also attempts
to rebuild the projection, so response-loss and post-append rebuild failures can
recover without appending another event.

If a multi-record batch commits an earlier record and a later journal append
fails, the service reports the committed prefix and the failed record with HTTP
207, keeps `journal_committed: true`, and attempts to rebuild the projection for
the committed prefix. Storage exception details are bounded to an error type in
the per-record outcome. Retrying the same multi-record body is idempotent for
the committed prefix and can import the remaining suffix once storage recovers.
If the service process exits after a journal append commits but before
projection rebuild returns, the restarted service reports `projection_stale`
health until a retry or explicit rebuild repairs the disposable projection.
Retrying the same idempotency key after restart reports the existing event as a
duplicate and rebuilds without appending another journal record.

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
Explicit capability grants do not satisfy global or tenant role checks; use
capability checks for endpoint permissions and tenant role checks for
tenant-scoped authorization decisions.

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

Liveness probes use `/live`; readiness probes use `/ready`. Journal corruption
therefore removes the pod from service without creating an endless liveness
restart loop.

New journal, projection, lock, and generated demo evidence files default to
private POSIX permissions (`0600` for files and `0700` for application-created
evidence directories). Existing storage that is broader than this is rejected
for writes with an actionable error rather than silently chmodding parent
directories the application did not create. Windows and filesystems that do not
enforce POSIX mode bits require equivalent administrator controls.

## Local Journal Benchmarks

Before proposing segmented journals, append indexes, or checkpoint changes, run
the synthetic local journal benchmark outside the release-critical path:

```bash
uv run python scripts/benchmark_journal_ingest.py \
  --counts 10000,100000,250000 \
  --repetitions 3 \
  --output-dir build/journal-ingest-benchmark-YYYYMMDD \
  --report-path build/journal-ingest-benchmark-YYYYMMDD/report.json
```

The benchmark emits JSON with setup time, verified snapshot timing, and duplicate
idempotency-scan timing. Results are local performance evidence only; they are
not production throughput guarantees and should not be committed unless a
release or design review explicitly asks for the artifact. The `build/` path is
ignored by git and is suitable for local design-review evidence.

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
