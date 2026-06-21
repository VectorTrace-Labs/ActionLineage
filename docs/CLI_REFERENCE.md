# CLI Reference

Run commands with:

```bash
uv run actionlineage --help
```

## General

- `actionlineage version`: print package version.
- `actionlineage doctor`: print local runtime diagnostics.

## Demo

- `actionlineage demo run --output-dir build/actionlineage-demo`: write the
  deterministic no-key/no-cloud demo journal, projection, and incident export.

## Journal

- `actionlineage journal verify evidence.jsonl`: verify journal hash-chain
  integrity.
- `actionlineage journal create-anchor evidence.jsonl anchor.json`: create a
  trusted local anchor.
- `actionlineage journal verify-anchor evidence.jsonl anchor.json`: verify a
  journal against an anchor.
- `actionlineage journal create-anchor evidence.jsonl anchor.json --signing-key-file anchor.key`:
  create an HMAC-signed anchor without putting the key in shell arguments.
- `actionlineage journal verify-anchor evidence.jsonl anchor.json --signing-key-file anchor.key`:
  verify a signed anchor with the trusted key file.
- `actionlineage journal append-anchor-log anchor.json anchors.log`: append an
  anchor to a local anchor log sidecar.
- `actionlineage journal verify-anchor-log anchors.log`: verify the local
  anchor-log hash chain.
- `actionlineage journal verify-anchor-log anchors.log --expected-record-count 3 --expected-last-entry-hash sha256:...`:
  verify the log against trusted tail values.
- `actionlineage journal create-git-anchor-statement evidence.anchor.json evidence.anchor.git.json --repo . --ref HEAD`:
  create a deterministic sidecar tying a committed anchor file to a Git commit.
- `actionlineage journal verify-git-anchor-statement evidence.anchor.json evidence.anchor.git.json --repo . --ref HEAD`:
  verify the anchor bytes, committed Git blob, and optional current ref.
- `actionlineage journal create-external-attestation evidence.anchor.json evidence.attestation.json --statement-file statement.bin --attester reviewed-hsm`:
  create a sidecar linking anchor bytes to an external attestation statement digest.
- `actionlineage journal verify-external-attestation evidence.anchor.json evidence.attestation.json --statement-file statement.bin`:
  verify local consistency of an external attestation sidecar and optional statement bytes.
- `actionlineage journal create-archive-manifest evidence.jsonl evidence.archive.json --object-uri s3://bucket/key`:
  create a local manifest for an intended archived journal object.
- `actionlineage journal verify-archive-manifest evidence.archive.json`:
  verify local journal bytes and trusted tail values against an archive manifest.
- `actionlineage journal export-verified-prefix evidence.jsonl prefix.jsonl`:
  export records before the first detected integrity issue.

## Projection

- `actionlineage projection rebuild evidence.jsonl projection.sqlite`: rebuild
  the query projection from a verified journal.
- `actionlineage projection timeline projection.sqlite --trace-id trace_123`:
  query a timeline.
- `actionlineage projection filter projection.sqlite --tool-name safe_http.send`:
  query filtered timeline slices.
- `actionlineage projection explain-event projection.sqlite evt_123`: explain
  causal and evidence-link context for one event.
- `actionlineage projection export-incident projection.sqlite --trace-id trace_123`:
  write incident JSON to stdout.
- `actionlineage projection summarize projection.sqlite --trace-id trace_123`:
  write a deterministic evidence-grounded investigation summary to stdout.
- `actionlineage projection export-graph projection.sqlite --trace-id trace_123`:
  write dependency-free investigation graph JSON to stdout.
- `actionlineage projection export-case projection.sqlite ./case --trace-id trace_123`:
  write JSON, NDJSON, and Markdown case artifacts. Existing bundle files are
  not overwritten.
- `actionlineage projection export-console projection.sqlite console.html --trace-id trace_123`:
  render the static investigation console.
- `actionlineage projection export-console projection.sqlite console.html --trace-id trace_123 --case-context context.json`:
  render the console with redacted analyst notes and saved view hints.
- `actionlineage projection export-desktop-bundle projection.sqlite ./desktop --trace-id trace_123`:
  render `index.html` and `actionlineage-desktop.json` for optional native desktop shells.

## Contracts

- `actionlineage contract init contract.json`: create a starter contract.
- `actionlineage contract explain contract.json`: explain requirements.
- `actionlineage contract validate contract.json evidence.jsonl`: validate
  evidence and print JSON or annotation output.
- `actionlineage contract test contract.json evidence.jsonl`: CI-oriented
  validation with nonzero exit on failure.

## Detections

- `actionlineage detection explain-sequence rules.json evidence.jsonl`: explain
  sequence-rule stage candidates and matches without printing event payloads.

## Extension Packs

- `actionlineage pack validate actionlineage-pack.json`: validate a local
  extension pack manifest and artifact checksums.
- `actionlineage pack list actionlineage-pack.json`: list local extension pack
  artifacts grouped by kind.
