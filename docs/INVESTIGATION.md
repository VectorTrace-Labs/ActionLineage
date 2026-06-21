# Investigation Workflow

ActionLineage investigation workflows are derived from the rebuildable
projection. The append-only journal remains canonical evidence.

## Rebuild the projection

```bash
uv run actionlineage projection rebuild evidence.jsonl projection.sqlite
```

Projection corruption is handled by rebuilding from a verified journal. Do not
treat projection files as canonical evidence.

## Filter timelines

Use `projection filter` for analyst-oriented slices:

```bash
uv run actionlineage projection filter projection.sqlite \
  --tool-name safe_http.send \
  --verification-status verified
```

Supported filters include trace, run, event type, principal, tool name, resource
identifier, verification status, sensitivity, trust, and descriptor hash.

## Explain an event

```bash
uv run actionlineage projection explain-event projection.sqlite evt_123
```

The explanation includes the event, causal parent, child event IDs, and evidence
links where the event is either the subject or corroborating evidence.

## Export incident JSON

```bash
uv run actionlineage projection export-incident projection.sqlite --trace-id trace_123
```

Incident export includes:

- Ordered events.
- Involved principals.
- Tool names and descriptor hashes when present.
- Resource identifiers.
- Verification status counts.
- Evidence links.
- Conflicts, unknowns, limitations, and detection hits.

## Summarize an incident

```bash
uv run actionlineage projection summarize projection.sqlite --trace-id trace_123
```

The summary is deterministic and grounded only in projected evidence. It returns
a headline, key findings, limitations, and the event IDs used as grounding. It
does not call a model provider and is not canonical evidence; verify important
claims against the append-only local journal.

## Export an investigation graph

```bash
uv run actionlineage projection export-graph projection.sqlite --trace-id trace_123
```

The graph export is a dependency-free interchange format for analyst tools,
graph databases, static consoles, or native clients. It includes event,
principal, tool, resource, verification-status, causal, and evidence-link
relationships derived from redacted projected evidence. The graph is not a
separate source of truth; the append-only local journal remains canonical.

## Export a case bundle

```bash
uv run actionlineage projection export-case projection.sqlite ./case --trace-id trace_123
```

The bundle writes:

- `case.json`: machine-readable incident export.
- `events.ndjson`: one event per line in timeline order.
- `report.md`: concise Markdown summary for review.

Case reports must say "No observation recorded is not proof that a side effect
did not occur." They must not claim that missing evidence proves absence.

## Export a static console

```bash
uv run actionlineage projection export-console projection.sqlite console.html --trace-id trace_123
```

The static console renders the timeline, event details, evidence-link direction,
and verification matrix from projection data. It is a disposable analyst view;
the append-only journal remains canonical evidence.
