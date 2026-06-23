# Changelog

All notable changes will be documented here.

## Unreleased

No unreleased changes.

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
