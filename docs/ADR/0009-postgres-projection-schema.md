# ADR-0009: PostgreSQL Projection Schema

- Status: Accepted
- Date: 2026-06-21
- Owners: Marq Mercado

## Context

ActionLineage already uses a local SQLite projection rebuilt from the verified
append-only journal. Public 1.0 deployment planning includes service-mode
operation where teams may want a shared query backend. The canonical evidence
store remains the append-only journal; any database projection must be
disposable and rebuildable.

## Decision

Add a dependency-free PostgreSQL projection writer that accepts a small executor
protocol. It verifies the local journal first, creates a PostgreSQL-compatible
projection schema, deletes existing projected rows, inserts projected event
fields and JSONB event documents, and records rebuild metadata.

The projection schema mirrors the SQLite investigation fields: event identity,
correlation, causality, ordering, integrity hashes, verification status,
evidence-link identifiers, journal record number, and full serialized event
JSON. Runtime integrations may provide a psycopg, SQLAlchemy, or platform
executor behind optional dependencies.

## Consequences

- Core installation does not require a PostgreSQL driver.
- PostgreSQL projection failures do not change the canonical journal.
- Operators can rebuild shared query state from verified local evidence.
- Projection schema changes must remain journal-compatible and should be
  documented in this ADR family before release.
- Multi-tenant authorization, managed database migrations, and object-storage
  journal archival remain separate deployment decisions.
