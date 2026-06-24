# ADR-0008: Static Investigation Console Scope

- Status: Accepted
- Date: 2026-06-21
- Owners: Marq Mercado

## Context

ActionLineage needs an analyst-facing investigation view for public alpha, but the
core product must remain a local-first evidence plane. A full single-page
application, graph renderer, saved cases, and multi-user console would add
front-end build tooling, service assumptions, and new operational attack surface.

The append-only journal remains canonical evidence. The SQLite projection is
rebuildable. Any console output must be a disposable view over projection data,
not a new evidence store.

## Decision

Provide a dependency-free static HTML console exporter for the public alpha. The exporter
renders deterministic projection timelines with:

- Timeline and event details.
- Verification matrix.
- Evidence-link direction from subject event to corroborating evidence.
- Basic verification-status counts.
- Escaped event payload details.
- Optional redacted analyst notes and saved view hints.

Expose it through both Python APIs and a CLI command:

```bash
uv run actionlineage projection export-console projection.sqlite console.html \
  --journal-path evidence.jsonl \
  --trace-id trace_123
```

Optional case context is accepted as a JSON file containing notes and saved
views. Context text is redacted before rendering. These annotations are display
metadata only; they are not journal evidence and do not alter verification
status.

Do not add a JavaScript framework, graph-layout library, or browser application
runtime to core. Rich graph navigation, rule debugging, collaboration, and
screenshots are deferred to a later optional console package.

## Consequences

- Analysts can inspect deterministic demo and case timelines without running a
  service or installing front-end tooling.
- The console can be generated in CI and attached to case bundles.
- Core dependency boundaries stay unchanged.
- The static console is not collaborative, interactive, or canonical evidence.
- Analyst notes can travel with a static case export without becoming canonical
  evidence.
- Future console work can replace or wrap this artifact without changing journal
  or projection compatibility.

## Verification

- Console tests render deterministic demo evidence.
- CLI tests export static HTML from a projection.
- Escaping tests cover hostile selector, payload, and annotation text.
- Redaction tests cover note text before HTML rendering.
- Public API tests include the console export surface.
