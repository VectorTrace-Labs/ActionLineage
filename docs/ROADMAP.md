# Roadmap

ActionLineage is a public alpha vendor-neutral evidence and detection plane for
tool-using agents. The current alpha includes the local journal, neutral event
model, source-neutral ingestion, investigation exports, contracts, detections,
replay robustness, optional adapters, service boundary, and static console.

This roadmap describes active public direction without treating future work as
already delivered.

## Current Alpha Release Surface

- Core event envelope, redaction boundary, evidence links, and verification
  states.
- Append-only local journal, hash-chain verification, anchors, archive
  manifests, Git anchor statements, and external attestation sidecars.
- Rebuildable SQLite projection and optional Postgres projection schema plus
  verifier.
- Source-neutral ingestion for local, file, HTTP, MCP-mapped, framework, and
  external JSON evidence.
- Deterministic local demo with verified, unverified, conflicting, and
  not-dispatched outcomes.
- Investigation timeline, filters, event explanation, case bundle, graph export,
  grounded summary, static console, and desktop bundle export.
- Lineage Contracts, sequence detections, replay mutation testing, minimized
  counterexamples, and robustness scorecards.
- Optional MCP, policy, OpenTelemetry, SIEM/export, service, tenant, cloud
  fixture, Kubernetes fixture, and external sensor feed boundaries.
- Observer attestation declarations and verification-helper gating for
  independent-observer claims.
- Security hardening scripts, release checklist, issue templates, privacy model,
  and vulnerability disclosure policy.

## Near-Term Alpha Priorities

1. Fresh-clone release validation on macOS and Linux.
2. More public fixture packs for common agent and tool patterns.
3. Additional live observer adapters with clear trust labels, limitation
   labels, and ADR-0012-style attestation declarations.
4. Expanded detection rule corpus and benign/adversarial replay sets.
5. Better service-mode deployment examples and operational runbooks.
6. Static console polish driven by real analyst workflows.
7. Compatibility fixtures for future `v1alpha1` payload evolution.
8. Canonicalization v1 adoption as an active persisted hash format after a
   migration ADR; conformance vectors and migration guardrails are checked in.
9. Causality schema evolution for typed multi-parent causal edges after
   ADR-0014 acceptance criteria are implemented.
10. External checkpoint trust-root implementation after ADR-0015 provider-neutral
    verification fixtures exist.

## Optional / Ecosystem Tracks

These areas are intentionally visible but remain preview, planned, or
external-validation-required unless a future ADR moves them into the required
release surface:

- Hardware-backed signing, trusted timestamping, WORM/object-lock verification,
  transparency-log inclusion, or remote-attestation verification.
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
