# Investigation Console

The ActionLineage console is a static, dependency-free HTML artifact generated
from the rebuildable projection. It is useful for reviewing deterministic demo
evidence, sharing sanitized case context, and attaching a human-readable view to
case bundles.

The append-only journal remains canonical evidence. The console is a rendered
view and can be deleted or regenerated at any time.

## Generate a Console

Run the deterministic demo, then render the console:

```bash
uv run actionlineage demo run --output-dir build/actionlineage-demo
uv run actionlineage projection export-console \
  build/actionlineage-demo/projection.sqlite \
  build/actionlineage-demo/console.html \
  --trace-id trace_demo_evidence_plane
```

Open `build/actionlineage-demo/console.html` in a browser.

To include analyst annotations and saved view hints, provide a JSON context file:

```json
{
  "notes": [
    {
      "title": "Triage note",
      "body": "Acknowledged HTTP send remains unverified.",
      "event_id": "evt_demo_11",
      "author": "analyst@example.invalid"
    }
  ],
  "saved_views": [
    {
      "name": "Unverified outcomes",
      "query": "verification_status:unverified",
      "description": "Events that need more corroboration."
    }
  ]
}
```

```bash
uv run actionlineage projection export-console \
  build/actionlineage-demo/projection.sqlite \
  build/actionlineage-demo/console.html \
  --trace-id trace_demo_evidence_plane \
  --case-context console-context.json
```

## Desktop Bundle

For optional native desktop shells, export a deterministic bundle:

```bash
uv run actionlineage projection export-desktop-bundle \
  build/actionlineage-demo/projection.sqlite \
  build/actionlineage-demo/desktop \
  --trace-id trace_demo_evidence_plane
```

The bundle contains:

- `index.html`: the same static console view.
- `actionlineage-desktop.json`: a manifest with entrypoint, event count,
  required local-file capability, canonical-source language, and limitations.

ActionLineage does not ship a native desktop runtime in core. The bundle is a
reviewed input for future native shells and remains a rendered view.

## Included Views

- Timeline rows ordered by the projection's deterministic incident order.
- Evidence graph showing causal parent-to-child edges and evidence-link
  subject-to-evidence edges.
- Event details with escaped JSON payloads.
- Verification matrix showing unknown, verified, unverified, timed-out, and
  conflicting status values when present.
- Evidence-link explorer showing relationship, subject event, evidence event,
  observer identity, and confidence.
- Status counts for investigation triage.
- Static case notes and saved view hints when a context file is provided.

## Boundaries

- The console does not persist new evidence.
- The console does not replace journal verification.
- Missing observations are displayed as missing observations only.
- Case notes and saved views are rendered annotations, not journal evidence.
- Console context text is passed through the redaction policy before rendering.
- Console context files are bounded to 64 KiB by default and notes or saved
  views are bounded to 50 items each. Oversized context fails closed before
  rendering.
- Annotation text that exceeds the active redaction capture limit is rendered
  with a visible truncation marker and digest.
- Generated HTML includes a restrictive Content Security Policy and does not
  require scripts or remote resources.
- Rule debugging is available through the detection API and CLI; collaborative
  workflows are deferred to a later optional console package.

## Python API

```python
from pathlib import Path

from actionlineage.console import ConsoleNote, ConsoleSavedView, write_console

write_console(
    Path("build/actionlineage-demo/projection.sqlite"),
    Path("build/actionlineage-demo/console.html"),
    trace_id="trace_demo_evidence_plane",
    notes=(ConsoleNote(title="Triage", body="HTTP send remains unverified."),),
    saved_views=(ConsoleSavedView(name="Unverified", query="verification_status:unverified"),),
)
```
