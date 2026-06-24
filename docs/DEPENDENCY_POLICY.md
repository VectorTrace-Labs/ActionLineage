# Dependency Policy

## Principles

- Minimize the trusted computing base.
- Prefer the standard library for small, well-understood functions.
- Use established libraries for protocols, cryptography, parsing, and security-sensitive normalization.
- Pin and lock dependencies for reproducible development.
- Do not add a dependency only to avoid writing a small amount of ordinary code.

## Required review for production dependencies

Document:

- Purpose and alternatives considered.
- License.
- Maintainer activity and release cadence.
- Security advisories and update policy.
- Transitive dependency impact.
- Whether it handles secrets, authentication, parsing, cryptography, or network traffic.
- Removal/migration plan if abandoned.

## Current dependency baseline

- Python 3.12+
- `uv` for environment and lockfile management.
- Pydantic for configuration and serialization boundaries.
- Typer for CLI.
- Standard library `sqlite3` for the rebuildable projection.
- Pytest, Hypothesis, Ruff, mypy, pip-audit, and jsonschema for quality checks.

## Development-only test-client dependency

`httpx2` is included only in the `dev` optional extra so Starlette/FastAPI
service-mode tests use Starlette's current test-client backend without
deprecation warnings. It is not a core, service-runtime, adapter, journal,
projection, or CLI dependency.

- Purpose: local test-client transport for optional FastAPI service tests.
- Alternatives considered: suppressing the warning, or writing a local ASGI
  test harness. Suppression would hide dependency drift, and a custom harness
  would duplicate framework behavior for little release value.
- License: BSD-3-Clause, based on current PyPI metadata.
- Maintainer and update policy: locked by `uv.lock`, reviewed through normal
  dependency-update PRs, SBOM generation, `scripts/check_dependency_licenses.py`,
  and `pip-audit`.
- Transitive impact: `httpcore2` and `truststore`; shared dependencies such as
  AnyIO, IDNA, H11, and typing extensions are already present elsewhere.
- Security implications: used in local tests to exercise preview service
  endpoints; it can handle test HTTP requests but does not enter the alpha
  runtime trusted computing base.
- Removal plan: remove once Starlette/FastAPI no longer needs the separate
  `httpx2` test-client backend or if service tests move to a supported
  framework-native replacement.

## Optional adapter baseline

These dependencies are not part of the core trusted computing base. They belong
behind optional extras and must not be imported by `domain`, `journal`,
`projection`, or core CLI modules:

- FastAPI and Uvicorn for optional service mode.
- Official MCP Python SDK, constrained to the currently supported major version.
- HTTPX for adapter HTTP clients.
- OpenTelemetry SDK/exporter for trace mirroring.
- PyJWT with crypto support for service JWT/OIDC verification; used instead of
  custom JWT parsing or signature validation. PyJWT 2.x is MIT licensed,
  production-stable in package metadata, handles authentication-token parsing
  and signature verification, and enters only the optional service trusted
  computing base.
- PyYAML for optional YAML contracts, detections, and scenarios.
- SQLAlchemy for optional Postgres projection support.
- Pydantic Settings for adapter/runtime configuration boundaries.

ADR-0016 expands this into the protected evidence-kernel boundary. Import
boundary tests now cover event/evidence, journal, anchoring, observer policy,
projection, contract, query, and export paths so optional SDKs and service
frameworks do not enter evidence-critical modules accidentally.

## Version caution

The MCP Python SDK is undergoing a major-version transition. Verify the official repository before changing the `mcp` constraint. Do not upgrade across a major version in the same pull request as a feature.

## Release audit commands

Run these before publishing a release candidate:

```bash
uv run pip-audit
uv run --all-extras python scripts/generate_sbom.py --output build/actionlineage-sbom.json
uv run --all-extras python scripts/check_dependency_licenses.py \
  --output build/actionlineage-license-report.json
```

Generated SBOMs and dependency license reports are release artifacts. Do not
commit them unless the release process explicitly asks for a reviewed artifact
snapshot.
