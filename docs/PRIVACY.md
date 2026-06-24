# Privacy Model

ActionLineage records evidence about tool-using agents. Evidence can include
principal identifiers, tool descriptors, resource identifiers, delegated
identity references, timestamps, normalized actions, observer output, and
verification links.

## Data Minimization

- Store digests, descriptors, and bounded metadata instead of raw content where
  possible.
- Use `RedactionPolicy` for known sensitive JSON paths.
- Use `redact_structured_log_fields()` before emitting structured log fields
  derived from evidence, exceptions, observers, exporters, or user input.
- Treat authorization headers, bearer tokens, API keys, private keys, passwords,
  session cookies, and configured sensitive fields as never-persist values.
- Keep observer payloads explicit about trust, scope, and limitations.

## Canonical and Disposable Data

- Canonical: append-only local journals and trusted anchors.
- Rebuildable: SQLite projections.
- Disposable: static console HTML, SIEM exports, OpenTelemetry-style attributes,
  webhooks, and report bundles.

Deleting a projection or console does not remove canonical journal evidence.

## Sharing Cases

Before sharing case bundles:

- Verify the journal and projection source.
- Confirm redaction policies used for import and export.
- Review evidence limitations and observer trust levels.
- Avoid implying that missing observations prove a side effect did not occur.

## Retention

ActionLineage does not silently compact canonical journals. Retention controls
must preserve journal verification metadata, anchors, and migration notes.
Projection cleanup is acceptable because projections rebuild from the journal.
