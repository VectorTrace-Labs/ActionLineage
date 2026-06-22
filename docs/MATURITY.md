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
- Python 3.12+ source, package metadata, CI, and release workflow validation.

## Local-Proof Surface

- Journal anchors, Git anchor statements, archive manifests, and recovery
  helpers under documented local trust assumptions; verified-prefix recovery
  writes separate files and rejects in-place journal overwrite.
- Built-in sequence detections and Lineage Lab replay/mutation/minimization.
- Agent Validation Lab scenario validation, no-model replay, provenance, and
  artifact audits as a development-only evaluation surface; the current
  deterministic baseline is summarized in `docs/AGENT_VALIDATION_EVIDENCE.md`.
- Deterministic demo evidence map generated from local demo artifacts for
  onboarding and visual review; canonical evidence remains the local journal.
- Release hardening scripts for claim language, secret scanning, SBOM, local
  provenance, dependency audit, repository-local Markdown link checking, and
  release consistency.
- CI release-proof gates for wheel/sdist build, SBOM, dependency audit, and
  unsigned local provenance generation.
- Release workflow for CI-built artifacts, GitHub artifact attestations, and
  manual Trusted Publishing jobs.
- External review guides, reproduction commands, and feedback templates that
  make review easier without claiming review has happened.
- Release-candidate audit artifacts and owner publication checklist that prepare
  publication decisions without performing owner-gated actions.

## Preview Surface

- MCP descriptor/runtime helpers and optional policy adapter semantics.
- OpenTelemetry, SIEM/export, STIX/TAXII, and webhook/file sink integrations.
- Optional FastAPI service mode, JWT/OIDC helpers, tenant checks, Docker,
  Kubernetes, and Helm deployment examples.
- GHCR container-image publication from version-tagged release workflow runs.
- Optional Postgres projection schema.
- Cloud, Kubernetes, and external sensor observers backed by local fixtures.
- Desktop bundle export for future native shells.

## Planned Or External Validation

- PyPI/TestPyPI package ownership transfer to the organization account after
  package-index organization approval.
- GitHub Release object and hosted release artifacts for `v0.1.0a3`; the tag
  exists, but creating or repairing the release object is an owner action.
- Public package metadata project URLs for PyPI/TestPyPI after the next
  owner-approved release publishes corrected metadata.
- Homebrew tap and formula publication.
- conda-forge recipe publication.
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
