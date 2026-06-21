# Extension Packs

ActionLineage extension packs are local manifests for reviewed adapter,
detection, contract, observer, export-profile, and lab-corpus artifacts. They
are a distribution and review aid; they are not canonical evidence and they do
not imply a hosted marketplace or endorsement.

## Manifest

```json
{
  "schema_version": "actionlineage.dev/pack/v1",
  "name": "demo-pack",
  "version": "1.0.0",
  "publisher": "VectorTrace Labs",
  "license": "Apache-2.0",
  "description": "Reviewed local pack fixture.",
  "tags": ["demo", "detection"],
  "compatibility": {"actionlineage": ">=0.1.0a1,<0.2"},
  "artifacts": [
    {
      "kind": "detection_rule",
      "name": "restricted-read-to-send",
      "path": "rules/restricted-read-to-send.json",
      "sha256": "sha256:..."
    }
  ]
}
```

Supported artifact kinds are:

- `adapter`
- `contract`
- `detection_rule`
- `export_profile`
- `lab_corpus`
- `observer`

Artifact paths must be relative to the manifest directory and must not escape
that directory. When `sha256` is present, validation compares it to local file
bytes.

## CLI

```bash
uv run actionlineage pack validate actionlineage-pack.json
uv run actionlineage pack list actionlineage-pack.json
```

`pack validate` exits nonzero when the manifest is malformed, references missing
artifacts, uses unsupported artifact kinds, escapes the pack directory, or has a
checksum mismatch.

## Trust

Pack validation only checks local manifest structure and artifact identity. It
does not execute pack contents, fetch remote content, verify publisher identity,
or decide that detections are correct. Review and test packs with contracts,
deterministic fixtures, and Lineage Lab before production use.
