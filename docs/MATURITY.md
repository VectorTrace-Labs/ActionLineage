# Maturity Model

ActionLineage uses explicit maturity labels so public claims are tied to
evidence and limitations.

## Labels

| Label | Meaning | Public wording |
| --- | --- | --- |
| Alpha-supported | Implemented, documented, covered by tests, and suitable for local alpha evaluation. | "Supported in the public alpha." |
| Local-proof | Demonstrated through deterministic local tests, fixtures, or demo artifacts, but not yet validated in external production environments. | "Locally demonstrated." |
| Preview | Implemented or scaffolded behind optional extras or fixture-only boundaries, with API or operational changes still expected. | "Preview." |
| External-validation-required | Requires owner action, real infrastructure, third-party review, or public service configuration outside this repository. | "Requires external validation." |
| Planned | Accepted roadmap direction with no current release claim. | "Planned." |
| Mismatch | A claim, command, or metadata value does not match implementation or tests and must be corrected before release. | Do not publish as a capability. |

## Alpha-Supported Surface

- `actionlineage.dev/v1alpha1` event envelope and strict parser.
- Redaction before journal persistence, export mapping, and error serialization.
- Append-only local journal and deterministic hash-chain verification.
- Rebuildable SQLite projection, timeline, filters, incident export, case bundle,
  graph export, grounded summary, and static console export.
- Source-neutral ingestion objects and batch import.
- Deterministic local demo with verified, unverified, conflicting, and
  not-dispatched outcomes.
- JSON Lineage Contract validation for local journal evidence.
- PyPI and TestPyPI package publication for the current public-alpha version,
  with fresh install and demo smoke validation.
- Built wheel and source distribution first-time-user smoke validation for
  version, demo, journal verification, contract validation, case export, and
  static console export.
- Python 3.12, 3.13, and 3.14 source, package metadata, CI, and release
  workflow validation.

## Local-Proof Surface

- Journal append I/O failure handling, anchors, Git anchor statements, archive
  manifests, and recovery helpers under documented local trust assumptions;
  verified-prefix recovery writes separate files and rejects in-place journal
  overwrite.
- HTTP fixture observers keep multiple plausible records unverified and expose
  `ambiguous_candidate_count` rather than selecting one match without evidence.
- Observer attestation declarations and `verify_observation()` gating keep
  helper-generated `independent_observer` claims behind current, in-scope,
  no-shared-dependency declarations.
- Built-in sequence detections and Lineage Lab replay/mutation/minimization.
- Agent Validation Lab scenario validation, no-model replay, provenance, and
  artifact audits as a development-only evaluation surface; the current
  deterministic baseline is summarized in `docs/AGENT_VALIDATION_EVIDENCE.md`
  and generated into `docs/evidence/agent-validation-baseline.*`. Scheduled
  no-model artifacts run on trusted default-branch code; optional live-model
  execution is skipped unless maintainers configure `GH_MODELS_TOKEN`.
- Deterministic demo evidence map generated from local demo artifacts for
  onboarding and visual review; canonical evidence remains the local journal.
- Release hardening scripts for claim language, secret scanning, SBOM,
  dependency license reporting, local provenance, dependency audit,
  repository-local Markdown link checking, release consistency, generated
  release-candidate manifests, and generated release proof review indexes.
- CI release-proof gates for branch-enabled total coverage, wheel/sdist build,
  first-time-user artifact smoke, SBOM, dependency license checks, dependency
  audit, unsigned local provenance generation, and concise GitHub job-summary
  evidence.
- Release workflow for CI-built artifacts, GitHub artifact attestations, manual
  Trusted Publishing jobs, and owner-gated post-publication smoke verification
  reports.
- External review guides, reproduction commands, and feedback templates that
  make review easier without claiming review has happened.
- Release-candidate audit artifacts and owner publication checklist that prepare
  publication decisions without performing owner-gated actions. Generated
  manifests and review indexes are local navigation and hash-verification aids,
  not hosted releases or external validation.
- Canonicalization v1 conformance vectors and migration guardrails are
  checked in and executable, while persisted journal hashes remain on
  `actionlineage.dev/json-deterministic-v0`.
- Tenant storage layout and tenant-scoped service authorization are locally
  demonstrated for optional service wrappers: known tenants derive separate
  journal, projection, export, service-log, cache, and anchor namespaces, and
  storage scope requires both global role membership and tenant role binding.

## Preview Surface

- MCP descriptor/runtime helpers and optional policy adapter semantics.
- OpenTelemetry, SIEM/export, STIX/TAXII, and webhook/file sink integrations.
- Optional FastAPI service mode, JWT/OIDC helpers, Docker, Kubernetes, and Helm
  deployment examples.
- GHCR container-image publication from version-tagged release workflow runs.
- Optional Postgres projection schema and verifier.
- Cloud, Kubernetes, and external sensor observers backed by local fixtures.
- Live independent-observer declarations for production sensors.
- Desktop bundle export for future native shells.

## Planned Or External Validation

- PyPI/TestPyPI package ownership transfer to the organization account after
  package-index organization approval.
- GitHub Release object and hosted release artifacts for the next
  owner-approved `v0.1.0a6` release.
- Corrected PyPI/TestPyPI long-description wording after the next
  owner-approved release publishes updated metadata.
- Homebrew tap and formula publication.
- conda-forge recipe publication.
- Portable canonicalization v1 as an active persisted hash format.
- Causality model evolution ADR and future schema migration for typed
  multi-parent causal edges.
- External checkpoint trust-root ADR and provider-neutral verification
  implementation.
- Branch protection and GitHub security-control status.
- Independent security review, outside user evaluation, production operating
  history, and public feedback.
- Hardware-backed signing, live OS sensors, managed graph backends, SaaS control
  plane, marketplace, TAXII network operation, and native desktop app.

## Rules

- A public claim must name its maturity label or link to
  `docs/QUALITY_SCORECARD.md`.
- Preview and planned surfaces must not be described as alpha-supported.
- Missing observations must be reported as missing observations only.
- Verification means corroboration by the named evidence source within stated
  limitations.
