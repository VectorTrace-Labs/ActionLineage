# Changelog

All notable changes will be documented here.

## Unreleased

No unreleased changes.

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
