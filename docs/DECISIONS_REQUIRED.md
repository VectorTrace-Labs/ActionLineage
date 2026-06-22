# Decisions Required

This register separates Codex-executable work from owner or external validation
gates. Items in the owner or external columns must not be silently decided by an
implementation change.

## Owner Decisions

| Decision | Recommended default | Needed before |
| --- | --- | --- |
| Public version posture | Keep `0.1.0a3` and `Development Status :: 3 - Alpha` | Any public announcement |
| Schema namespace | Keep `actionlineage.dev/v1alpha1` | External integrations depend on schemas |
| API promise | Core event/journal/projection/ingestion are alpha-supported; optional service/cloud/adapter exports are preview | 1.0 planning |
| Demo contract | Use `outbound-http.json` for five-minute demo | README quickstart changes |
| Restricted-exfiltration demo | Keep as preview design example until demo emits required normalized action and detection evidence | Promoting that contract in README |
| `AGENTS.md` visibility | Keep ignored/local; publish contributor guidance through normal docs | Making local assistant instructions public |
| Python support | Support Python 3.12+ after CI and local validation; keep Python 3.11 deferred until tested and justified | Widening support below 3.12 |
| Service/deployment support | Keep Docker/Kubernetes/Helm preview | Production deployment claims |
| External release targets | Use GitHub Releases and PyPI/TestPyPI for the public alpha; publish preview GHCR images from version tags; keep Homebrew planned | Publishing new package-manager channels or Homebrew formulae |
| `v0.1.0a3` GitHub Release object | Create or repair the GitHub Release only after owner review of artifacts, notes, and attestation links | Claiming GitHub release artifacts for `v0.1.0a3` |
| Package metadata refresh | Include project URLs and sdist cache exclusions in the next owner-approved package release | Expecting PyPI/TestPyPI to show corrected project links |
| Signing/provenance | Use GitHub artifact attestations for release artifacts; keep local provenance as a supplemental manifest | Claiming attested package artifacts |
| Public security contact | Confirm GitHub private vulnerability reporting and contact path | Public announcement |
| External review | Select reviewer or review venue | Any claim of independent validation |
| Agent Validation artifact action runtime | Keep pinned Node 24-compatible upload action SHA and avoid the download action in release workflows | Changing artifact handling actions or relaxing artifact audit posture |

## External Validation Required

| Gate | Evidence needed |
| --- | --- |
| Branch protection | GitHub settings or API output showing protected `main` |
| Code scanning | Successful CodeQL run visible in GitHub |
| Dependabot alerts/security updates | Repository settings and current alert status |
| Secret scanning and push protection | Repository settings confirmation |
| Private vulnerability reporting | GitHub security settings confirmation |
| Published packages | PyPI package page, TestPyPI package page, or GHCR package page |
| GitHub Release object | Public GitHub Release page for `v0.1.0a3` with expected artifacts or a documented decision not to create one |
| PyPI/TestPyPI organization ownership transfer | Package-index organization approval and project ownership transfer |
| GHCR package visibility | Public package page for `ghcr.io/vectortrace-labs/actionlineage` after the first successful publish |
| Homebrew tap | `VectorTrace-Labs/homebrew-tap` exists with an audited formula and CI |
| Attested artifacts | Successful `release.yml` run with GitHub artifact attestations and verification instructions |
| Hosted provenance | Release artifact or attestation record linked from release notes |
| External security review | Written review output with scope and date |
| Production evaluation | Non-sensitive deployment notes or case study |

## Stop Conditions

- A change would break supported `v1alpha1` journal readability without an ADR.
- A new production dependency lacks license/security/maintenance review.
- A public claim cannot be mapped to implementation, tests, demo evidence, or a
  maturity label.
- A release artifact requires credentials or paid service access not supplied by
  the owner.
- A new PyPI/TestPyPI publish run is attempted before the matching Trusted
  Publisher record, GitHub environment, and package ownership path are confirmed.
- A deployment/security claim depends on GitHub or external settings that have
  not been independently checked.

## Deferred Work

- Hardware-backed signing or remote attestation.
- Live eBPF/EDR-grade sensors.
- Managed graph database backend.
- Hosted multi-tenant SaaS control plane.
- Marketplace for adapter, observer, detection, and contract packs.
- TAXII network operation.
- Native desktop application.
- Formal upstream OpenTelemetry semantic-convention proposal.
