# Changelog

All notable changes will be documented here.

## Unreleased

No unreleased changes.

## 0.1.0a6 - 2026-06-23

### Security

- Require same-pass verified journal snapshots for contract validation,
  detection explanation/evaluation, service journal reads, idempotency scanning,
  projection rebuilds, and replay loading.
- Add server-controlled service ingestion provenance under `payload.ingested_by`
  and reject client-supplied provenance.
- Reject ordinary write-role attempts to assert `trust=trusted`; admin
  authorization is required for trusted evidence assertions.
- Split service liveness and readiness so corrupted journals fail closed on
  `/ready`, `/health`, and journal-dependent endpoints without triggering
  endless liveness restarts.
- Create new journal, projection, lock, and demo evidence files with private
  POSIX modes and replace stale lock sentinels with advisory locks plus
  diagnostic metadata.

### Release

- Align deployment image tags, Helm `appVersion`, documentation examples, and
  release metadata with `0.1.0a6`.
- Add Helm digest image rendering, digest-pinned Kubernetes manifest generation
  during release, and container signing/attestation steps for trusted tag
  releases.
- Pin `uv`, pin the Python container base image by digest, install runtime
  dependencies from the committed lockfile, and install the project from a built
  wheel in the runtime container.
- Bound Python support to `>=3.12,<3.15` and add Python 3.14 to CI, release
  smoke, post-publication verification, classifiers, and docs.

### Compatibility

- `actionlineage.dev/v1alpha1` journals remain readable.
- Older service events without `payload.ingested_by` are treated as legacy
  records without invented authenticated transport identities.
- `/health` remains available for compatibility but follows readiness status.

## 0.1.0a5 - 2026-06-23

### Changed

- Prepared a corrective public-alpha release path for package metadata and
  release-object drift without expanding the alpha-supported product scope.
- Added tag-alignment proof to the generated release review index so local
  artifacts are not mistaken for tag-matched GitHub Release evidence.
- Resolved release-proof static-analysis findings from GitHub code scanning.
- Supersedes the `v0.1.0a4` tag, whose release workflow verified source and
  pushed the preview GHCR image but failed before artifact upload, package
  publication, or GitHub Release creation because the workflow wrote a
  non-canonical provenance artifact name.

### Compatibility

- `actionlineage.dev/v1alpha1` journals remain readable.
- No CLI flags, public schemas, policy semantics, or event names were changed.

## 0.1.0a4 - 2026-06-23

### Changed

- Tagged a corrective release attempt from the reviewed `0.1.0a4` source.

### Release Status

- The release workflow verify jobs passed and preview GHCR image publication ran.
- Release artifact build failed before artifact upload, attestations, package
  publication, or GitHub Release creation because the workflow wrote
  `actionlineage-provenance.json` while the release manifest required
  `actionlineage-release-provenance.json`.
- Do not treat `v0.1.0a4` as the public package release; use `0.1.0a5` for the
  corrective package and GitHub Release repair path.

## 0.1.0a3 - 2026-06-22

### Added

- Vendor-neutral evidence-plane event lifecycle.
- Source-neutral ingestion and normalization SDK.
- Append-only local journal, anchors, recovery helpers, and projection rebuild.
- Investigation timeline, incident export, case bundles, and static console.
- Sequence detections, Lineage Contracts, Lineage Lab replay, and scorecards.
- Optional MCP/policy/service/exporter boundaries.
- Local observers and side-effect verification helpers.
- Security policy, privacy model, release hardening scripts, SBOM generation,
  and adversarial fixtures.

### Compatibility

- `actionlineage.dev/v1alpha1` journals remain readable.
- Existing `agent.tool.*` compatibility events remain supported as adapter-era
  events.
- Projection databases are disposable and may be rebuilt from the canonical
  journal.
