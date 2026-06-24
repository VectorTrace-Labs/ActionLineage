# ADR-0016: Protected Evidence Kernel Boundary

- Status: Accepted
- Date: 2026-06-24
- Owners: Marq Mercado

## Context

ActionLineage is still packaged as one Python distribution, but not every
module has the same trust role. The public-alpha evidence claims depend on a
small protected kernel: event serialization and redaction, source-neutral
evidence normalization, journal verification, anchoring, observer attestation
policy, projection verification, contract validation, and query/export
boundaries that render verified evidence.

Optional adapters, service mode, OpenTelemetry mirroring, cloud collectors,
model-provider integrations, Lineage Lab, demos, static console presentation,
and release scripts can add useful surfaces, but they must not become implicit
trust roots for canonical evidence.

Without an explicit boundary, future feature work could accidentally pull
optional SDKs, service frameworks, network clients, policy engines, or model
providers into evidence-critical code paths. That would expand the trusted
computing base and weaken the current claim that the default demo and core
evidence path work without model credentials, cloud accounts, or internet
access.

## Decision Drivers

- Keep canonical evidence generation and verification dependency-light.
- Preserve the default demo's no-network, no-cloud, no-model boundary.
- Make optional adapters depend on the evidence kernel, not the other way
  around.
- Keep preview service, cloud, telemetry, and hosted surfaces out of alpha
  trust claims.
- Make future boundary expansions require an ADR, tests, and release-truth
  updates.

## Protected Kernel Paths

The protected evidence kernel currently includes these source paths:

- `src/actionlineage/domain`
- `src/actionlineage/errors.py`
- `src/actionlineage/compatibility.py`
- `src/actionlineage/evidence`
- `src/actionlineage/journal`
- `src/actionlineage/observers/attestation.py`
- `src/actionlineage/observers/verification.py`
- `src/actionlineage/projection`
- `src/actionlineage/contracts`
- `src/actionlineage/exporters`
- `src/actionlineage/cli.py`

`src/actionlineage/exporters` and `src/actionlineage/cli.py` are included only
for the public query/export boundary: they may format or mirror redacted
evidence, but they do not become canonical evidence stores.

## Decision

Treat the protected kernel as the minimum evidence-critical trusted computing
base for the public alpha.

Protected kernel modules may use the standard library and reviewed core runtime
dependencies already in the base package, such as Pydantic and Typer. They must
not directly import optional runtime dependencies, including MCP SDKs,
OpenTelemetry SDKs, FastAPI/Uvicorn, HTTPX/HTTPX2, PyJWT, SQLAlchemy, PyYAML,
cloud SDKs, model-provider SDKs, or agent-framework SDKs.

Optional adapter, service, cloud, telemetry, and model-provider modules must
translate into protected-kernel interfaces. They must not require protected
kernel modules to import optional SDKs or treat preview stores as canonical
evidence.

Future changes that add an optional dependency, network client, service
framework, policy engine, model-provider SDK, cloud SDK, database ORM, or
cryptographic signing service to the protected kernel require a new ADR or an
update to this ADR before merge. The ADR must document why the standard library
or existing dependencies are insufficient, whether the dependency handles
secrets or trust decisions, how failures surface, and what tests prove the
boundary remains explicit.

## Boundary Semantics

- Event and evidence serialization remains redacted before persistence,
  tracing, logging, error serialization, or export.
- Journal files, hash chains, trusted anchors, and verified archive manifests
  remain the canonical local evidence path.
- Projection databases, Postgres rows, static console output, case bundles,
  OpenTelemetry spans, SIEM/webhook/TAXII exports, service responses, and
  release proof artifacts remain rebuildable or derived surfaces unless a
  future ADR changes that boundary.
- Observer `independent_observer` claims require the reviewed attestation policy
  gate. A trust label alone is not enough.
- Contract validation and detection output may cite exact evidence, but they do
  not authorize tool execution or replace journal verification.
- Query and export surfaces must either operate on verified projected state or
  clearly label stale, unverified, preview, or derived output.
- A failure in an optional adapter, service, exporter, or projection must not
  silently convert to a successful canonical evidence claim.

## Consequences

- Public-alpha claims can stay precise: ActionLineage has a small local
  evidence kernel with optional adapter surfaces around it.
- Optional surfaces can still grow, but they must depend on protected-kernel
  contracts instead of widening the kernel by accident.
- Import-boundary tests can detect accidental SDK/framework drift in
  evidence-critical modules.
- Some useful integrations will require adapter code and explicit translation
  layers instead of direct imports in core paths.

## Verification

- `tests/release/test_protected_kernel_boundary.py` parses protected-kernel
  Python imports and fails if optional runtime dependency roots appear.
- Release-readiness tests require this ADR, the protected path list, and
  release-truth docs to remain aligned.
- Existing domain, journal, observer, projection, contract, export, CLI,
  service, and adapter tests continue to validate behavior on their respective
  sides of the boundary.
