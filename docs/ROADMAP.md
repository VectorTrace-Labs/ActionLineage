# Roadmap

ActionLineage 1.0 is a vendor-neutral evidence and detection plane for
tool-using agents. The current release includes the local journal, neutral event
model, source-neutral ingestion, investigation exports, contracts, detections,
replay robustness, optional adapters, service boundary, and static console.

This roadmap describes active public direction without treating future work as
already delivered.

## Current Release Surface

- Core event envelope, redaction boundary, evidence links, and verification
  states.
- Append-only local journal, hash-chain verification, anchors, archive
  manifests, Git anchor statements, and external attestation sidecars.
- Rebuildable SQLite projection and optional Postgres projection schema.
- Source-neutral ingestion for local, file, HTTP, MCP-mapped, framework, and
  external JSON evidence.
- Deterministic local demo with verified, unverified, and not-dispatched
  outcomes.
- Investigation timeline, filters, event explanation, case bundle, graph export,
  grounded summary, static console, and desktop bundle export.
- Lineage Contracts, sequence detections, replay mutation testing, minimized
  counterexamples, and robustness scorecards.
- Optional MCP, policy, OpenTelemetry, SIEM/export, service, tenant, cloud
  fixture, Kubernetes fixture, and external sensor feed boundaries.
- Security hardening scripts, release checklist, issue templates, privacy model,
  and vulnerability disclosure policy.

## Near-Term 1.x Priorities

1. Fresh-clone release validation on macOS and Linux.
2. More public fixture packs for common agent and tool patterns.
3. Additional observer adapters with clear trust and limitation labels.
4. Expanded detection rule corpus and benign/adversarial replay sets.
5. Better service-mode deployment examples and operational runbooks.
6. Static console polish driven by real analyst workflows.
7. Compatibility fixtures for future `v1alpha1` payload evolution.

## Optional / Ecosystem Tracks

These areas are intentionally visible but should remain optional unless a future
ADR moves them into the required release surface:

- Hardware-backed signing or remote-attestation verification.
- Live eBPF, EDR, process, network, and file collectors.
- Managed graph database backends.
- Hosted multi-tenant SaaS control plane.
- Hosted adapter, observer, detection, and contract marketplace.
- Operating a TAXII sharing network.
- Packaged native desktop application.
- Upstream OpenTelemetry semantic-convention proposal.
- Model-assisted investigation summaries grounded in exported evidence.

## Review Rules

- Keep the domain core independent of MCP, OpenTelemetry, model providers,
  service frameworks, and cloud SDKs.
- Preserve supported `actionlineage.dev/v1alpha1` journals unless an ADR approves
  a migration.
- Add tests and documentation with public behavior changes.
- Do not describe missing observations as proof that a side effect did not
  happen.
- Do not claim tamper-proof behavior, forensic completeness, or universal
  security.
