# Known Limitations

Last reviewed: 2026-06-23.

This page collects public-alpha limitations that reviewers should keep in view.
The maturity model in `docs/MATURITY.md` remains the source of truth for
supported, local-proof, preview, planned, and external-validation labels.

## Evidence Semantics

- A successful tool response is an acknowledgement, not proof of a side effect.
- Missing observations are reported as missing observations only.
- Conflicting evidence preserves disagreement and provenance.
- Verification depends on named corroborating evidence and its stated
  limitations.
- ActionLineage is not a sandbox, guardrail, DLP engine, or universal prevention
  layer.

## Integrity And Recovery

- The local journal is canonical local evidence under documented host and file
  system trust assumptions.
- Hash-chain verification detects supported journal mutations when the verifier
  has the relevant records and anchors.
- Projections, consoles, and exported bundles are derived artifacts and should
  be rebuilt from supported journals when in doubt.
- Hardware-backed signing, remote attestation, and managed evidence storage are
  not part of the public alpha.

## Runtime And Integration Scope

- Core packages intentionally avoid MCP, OpenTelemetry, FastAPI, cloud SDKs,
  model-provider SDKs, and agent frameworks.
- MCP, policy adapter, OpenTelemetry, service mode, Postgres, cloud observers,
  Kubernetes, Helm, and GHCR publication remain preview or externally gated.
- Service mode is not documented as production ready.
- Live cloud observers are fixture-backed in the current public alpha unless
  separately validated.

## Evaluation Scope

- The Agent Validation Lab is development-only and not a runtime dependency.
- No-model scripted scenarios are deterministic proof for the listed fixtures,
  not a claim about live model reliability.
- Live-model evaluation, if configured by maintainers, is optional, bounded,
  and non-blocking for provider instability.
- Model output is not authoritative product evidence.

## Release And External Validation

- The `v0.1.0a5` tag, GitHub Release object, PyPI package, and TestPyPI package
  are public as of 2026-06-23. The already published `0.1.0a5` PyPI/TestPyPI
  long descriptions cannot be changed in place; corrected release-state,
  service-health, provenance, Python-support, and container wording requires the
  next owner-approved package upload.
- The `0.1.0a6` source tree is a prepared hardening candidate until the owner
  approves the tag, release workflow, package uploads, container publication,
  and GitHub Release object.
- Anonymous checks on 2026-06-23 did not expose a public GHCR package page for
  `ghcr.io/vectortrace-labs/actionlineage`; GHCR remains preview and externally
  validated.
- Authenticated GitHub reads confirmed branch protection, secret scanning, push
  protection, private vulnerability reporting, a repository security policy,
  Dependabot security updates, 0 Dependabot alerts, 0 secret-scanning alerts, 0
  repository security advisories, latest `main` CodeQL success, and no open
  CodeQL alerts on 2026-06-23.
- No external audit, external adoption, production history, or independent
  validation is claimed by this repository.

## Data Handling

- Public issues should use synthetic or minimized data only.
- Do not share live credentials, authorization headers, customer data,
  proprietary prompts, or unredacted production journals.
- Generated local proof belongs under `build/`, `dist/`, or temporary
  directories and should not be committed by default.
