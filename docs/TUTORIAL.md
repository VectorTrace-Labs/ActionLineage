# Tutorial: Local Evidence Investigation

This tutorial runs entirely locally.

## 1. Install

```bash
uv sync --locked --all-extras
```

## 2. Run the Demo

```bash
uv run actionlineage demo run --output-dir build/actionlineage-demo
```

The command writes:

- `evidence.jsonl`: canonical journal.
- `projection.sqlite`: rebuildable projection.
- `incident.json`: incident export.
- `timeline.json`: compact timeline summary.

## 3. Verify the Journal

Use the command emitted in the demo JSON under `commands.verify`, or run:

```bash
uv run actionlineage journal verify build/actionlineage-demo/evidence.jsonl
```

## 4. Inspect the Timeline

```bash
uv run actionlineage projection timeline \
  build/actionlineage-demo/projection.sqlite \
  --trace-id trace_demo_evidence_plane
```

Look for separate requested, authorized, dispatched, acknowledged, observed, and
verified states. The acknowledged HTTP send remains unverified because no
independent receiver observation corroborates it.

## 5. Export a Case

```bash
uv run actionlineage projection export-case \
  build/actionlineage-demo/projection.sqlite \
  build/actionlineage-demo/case \
  --trace-id trace_demo_evidence_plane
```

## 6. Render the Console

```bash
uv run actionlineage projection export-console \
  build/actionlineage-demo/projection.sqlite \
  build/actionlineage-demo/console.html \
  --trace-id trace_demo_evidence_plane
```

Open `build/actionlineage-demo/console.html` in a browser.

## 7. Validate a Contract

```bash
uv run actionlineage contract validate \
  contracts/examples/outbound-http.json \
  build/actionlineage-demo/evidence.jsonl
```

Contracts are CI evidence requirements, not runtime policy.
The stricter `contracts/examples/restricted-exfiltration.json` example is for
detection-coverage design review and is not the five-minute demo contract.
