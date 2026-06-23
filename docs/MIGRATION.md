# Migration Guide

## From MCP-First Planning to Evidence Plane

ActionLineage public alpha centers the neutral evidence model and append-only journal.
MCP interception, policy enforcement, telemetry export, service mode, and the
console are optional adapters or views.

Migration steps:

1. Keep existing `agent.tool.*` journals readable.
2. Emit neutral lifecycle events for new integrations:
   `tool.execution.requested`, `authorized`, `dispatched`, `acknowledged`,
   `not_dispatched`, `side_effect.observed`, and verification outcomes.
3. Represent policy denial as `tool.execution.not_dispatched` with a linked
   policy decision.
4. Treat tool success as acknowledgement only.
5. Add `evidence_link` payload objects when verification or conflict evidence
   exists.

## Supported Journal Compatibility

`actionlineage.dev/v1alpha1` remains readable for the public alpha. Projection
databases are disposable and may be rebuilt. If a future envelope migration is
required, it must include an ADR, fixtures, and a reader compatibility test.

## Service Provenance And Health

Events ingested through service mode in `0.1.0a6` may include
`payload.ingested_by`, a server-controlled provenance object. Existing journals
without this payload key remain valid; readers must treat those records as
legacy records without authenticated ingestion provenance rather than inventing
an identity.

`/live` is now process liveness. `/ready` is readiness and fails closed when the
internal journal is malformed, locked beyond the configured timeout, or
hash-corrupted. `/health` remains available as a readiness-compatible alias.

## Package Extras

- Core install: event model, journal, projection, ingestion, detection,
  contracts, lab, observers, exporters, static console.
- `adapters`: MCP, OpenTelemetry-style, YAML/HTTP, and adapter planning
  dependencies.
- `service`: FastAPI/Uvicorn service runtime dependencies.
- `console`: reserved for future interactive console dependencies.
- `cloud`: reserved for future cloud observer dependencies.
- `dev`: tests, linting, type checking, audits, and release tooling.
