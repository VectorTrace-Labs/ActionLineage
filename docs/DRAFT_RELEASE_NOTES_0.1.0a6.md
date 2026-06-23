# Draft Release Notes For `v0.1.0a6`

Last reviewed: 2026-06-23.

These are draft notes for owner review. They do not push a tag, publish a
package, publish a container, create a GitHub Release, or close issues.

## Summary

ActionLineage `0.1.0a6` hardens the public alpha after the `v0.1.0a5`
alpha-hardening review. The release keeps the same alpha-supported core scope
while closing journal-integrity, service-ingestion, readiness, deployment,
Python-support, supply-chain, filesystem-permission, and lock-recovery gaps.

## Security Fixes

- Contract and detection consumers now require a verified journal snapshot
  instead of parsing records that merely contain `event_hash`.
- Service ingestion records server-controlled `payload.ingested_by` provenance
  and rejects client-supplied provenance.
- Ordinary write-role service credentials cannot assert `trust=trusted`; admin
  authorization is required for trusted evidence assertions.
- `/live` is process liveness, while `/ready` and `/health` fail closed on
  unusable internal state such as malformed or hash-corrupted journals.
- Deployment examples use `0.1.0a6` image tags, split liveness/readiness probes,
  and support digest-pinned Helm images.
- Python support is explicitly bounded to `>=3.12,<3.15` and CI/release matrices
  include Python 3.12, 3.13, and 3.14.
- Release workflows pin `uv`, pin the Python container base image by digest, and
  add digest-based container signing and attestations for trusted tag releases.
- New journal and projection files are created with private POSIX modes, and
  journal locks use advisory process locks with diagnostic metadata instead of
  stale exclusive sentinel files.

## Compatibility Notes

- `actionlineage.dev/v1alpha1` event compatibility is preserved.
- Service-created events may include `payload.ingested_by`. Older events without
  this field remain readable and are identified as legacy no-provenance records
  by service APIs rather than receiving invented authenticated identities.
- `/health` remains for compatibility but follows readiness status semantics.
- Helm chart package version remains Helm-compatible SemVer-style
  `0.1.0-a6`; `appVersion` remains the Python application version `0.1.0a6`.

## Known Limitations

- Local hash-chain evidence is tamper-evident under verified bytes and trusted
  anchors; it is not tamper-proof against a host attacker who can rewrite local
  evidence and trusted roots.
- Container signatures and attestations are produced only by trusted tag/release
  workflow contexts after the image is pushed.
- Source-tree defaults keep tag-based image references until a published GHCR
  digest exists; the release workflow generates the digest-pinned Kubernetes
  manifest after publication.
