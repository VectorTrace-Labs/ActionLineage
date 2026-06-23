# Decisions Required

This register separates Codex-executable work from owner or external validation
gates. Items in the owner or external columns must not be silently decided by an
implementation change.

## Owner Decisions

| Decision | Recommended default | Needed before |
| --- | --- | --- |
| Public version posture | Keep published `0.1.0a3` wording until a new owner-approved corrective alpha is cut; use `0.1.0a5` for the next metadata/release repair rather than attaching post-tag proof to `v0.1.0a3` | Any public announcement or version-tag publication |
| Schema namespace | Keep `actionlineage.dev/v1alpha1` | External integrations depend on schemas |
| API promise | Core event/journal/projection/ingestion are alpha-supported; optional service/cloud/adapter exports are preview | 1.0 planning |
| Demo contract | Use `outbound-http.json` for five-minute demo | README quickstart changes |
| Restricted-exfiltration demo | Keep as preview design example until demo emits required normalized action and detection evidence | Promoting that contract in README |
| `AGENTS.md` visibility | Keep ignored/local; publish contributor guidance through normal docs | Making local assistant instructions public |
| Python support | Support Python 3.12+ after CI and local validation; keep Python 3.11 deferred until tested and justified | Widening support below 3.12 |
| Service/deployment support | Keep Docker/Kubernetes/Helm preview | Production deployment claims |
| External release targets | Use GitHub Releases and PyPI/TestPyPI for the public alpha; publish preview GHCR images from version tags; keep Homebrew planned | Publishing new package-manager channels or Homebrew formulae |
| `v0.1.0a3` GitHub Release object | Do not attach post-tag hardening proof to `v0.1.0a3`; either rebuild from the tag or leave it documented as drift while cutting a new owner-approved `0.1.0a5` release | Claiming GitHub release artifacts for `v0.1.0a3` |
| Package metadata refresh | Include project URLs, corrected long description wording, and sdist cache exclusions in the next owner-approved package release; recommended repair version is `0.1.0a5` | Expecting PyPI/TestPyPI to show corrected project links or corrected description text |
| Signing/provenance | Use GitHub artifact attestations for release artifacts; keep local provenance as a supplemental manifest | Claiming attested package artifacts |
| Owner publication checklist | Review `docs/OWNER_PUBLICATION_CHECKLIST.md` before any release object, package, container, or public announcement action | Any publication or announcement |
| Public security contact | Private vulnerability reporting and repository security policy were confirmed enabled through authenticated GitHub reads on 2026-06-23 | Public announcement |
| External review | Select reviewer or review venue | Any claim of independent validation |
| Agent Validation artifact action runtime | Keep pinned Node 24-compatible upload action SHA and avoid the download action in release workflows | Changing artifact handling actions or relaxing artifact audit posture |

## External Validation Required

| Gate | Evidence needed |
| --- | --- |
| Branch protection | Authenticated GitHub API output confirmed protected `main` on 2026-06-23; recheck before announcement if settings change |
| Code scanning | Authenticated reads on 2026-06-23 showed latest `main` `codeql` workflow run `27974809091` and GitHub CodeQL dynamic analysis run `27974805527` completed successfully for commit `0e500d65d90fbda691d13e63ab58091e85083525`; CodeQL alerts were all non-open (`8 fixed`, `2 dismissed`) |
| Dependabot alerts/security updates | Dependabot security updates were enabled and authenticated alert read showed 0 Dependabot alerts on 2026-06-23 |
| Secret scanning and push protection | Secret scanning and push protection were enabled and authenticated alert read showed 0 secret-scanning alerts on 2026-06-23 |
| Private vulnerability reporting | Authenticated REST endpoint returned `enabled: true` on 2026-06-23 |
| Published packages | PyPI package page, TestPyPI package page, or GHCR package page |
| GitHub Release object | Public GitHub Release page for the owner-approved corrective version, preferably `v0.1.0a5`, with tag-matched artifacts and attestations; or a documented decision not to create one for `v0.1.0a3` |
| PyPI/TestPyPI organization ownership transfer | Package-index organization approval and project ownership transfer |
| GHCR package visibility | Public package page for `ghcr.io/vectortrace-labs/actionlineage` after the first successful publish |
| Homebrew tap | `VectorTrace-Labs/homebrew-tap` exists with an audited formula and CI |
| Attested artifacts | Successful `release.yml` run with GitHub artifact attestations and verification instructions |
| Hosted provenance | Release artifact or attestation record linked from release notes |
| External security review | Written review output with scope and date |
| Public evaluation feedback | Reproducible external feedback or minimized failure bundle submitted through the public templates |
| Production evaluation | Non-sensitive deployment notes or case study |

## Stop Conditions

- A change would break supported `v1alpha1` journal readability without an ADR.
- A new production dependency lacks license/security/maintenance review.
- A public claim cannot be mapped to implementation, tests, demo evidence, or a
  maturity label.
- A release artifact requires credentials or paid service access not supplied by
  the owner.
- A new PyPI/TestPyPI publish run is attempted before the matching version bump,
  version tag, Trusted Publisher record, GitHub environment, and package
  ownership path are confirmed.
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
