# Perfection Plan

This plan translates the public 10/10 goal into reviewable alpha-to-1.0 work.
Codex-executable work is separated from owner or external validation.

## Phase 0: Scorecard And Release Instructions

Status: implemented for public alpha.

Acceptance tests:

- Claim matrix covers README, roadmap, security, release, and demo claims.
- Local ignored assistant/planning files do not break normal release scans.
- `docs/DECISIONS_REQUIRED.md` lists owner gates.

Rollback: revert the docs and scanner-boundary changes.

Stop condition: any public claim cannot be labeled or mapped to evidence.

## Phase 1: Public Truth And Alpha Scope

Status: implemented for `0.1.0a3`.

Acceptance tests:

- Package metadata and CLI version report alpha.
- README separates alpha-supported, local-proof, preview, planned, and external
  validation surfaces.
- API docs label service, cloud, OpenTelemetry, MCP, and deployment exports as
  preview.

Rollback: restore previous metadata and docs. No event-schema migration is
involved.

Owner gate: any move back to `1.0.0` or Production/Stable requires an explicit
release decision and external validation evidence.

## Phase 2: Five-Minute Clean Installation

Status: implemented for repository-based alpha evaluation and locally built
wheel/source-distribution first-time-user smoke validation.

Acceptance tests:

- Fresh clone path uses `uv sync --locked --all-extras` and `make demo`.
- Built wheel and source distribution artifacts run the public CLI quickstart
  path through `scripts/smoke_public_quickstart.py`.
- README and tutorial validate `contracts/examples/outbound-http.json` against
  demo evidence.
- Clean tracked snapshot passes with `uv run --all-extras pytest`.

Rollback: restore prior README/tutorial commands.

Stop condition: a clean tracked snapshot cannot run the documented demo and
contract without credentials or external services.

## Phase 3: Flagship Demo Completeness

Status: implemented for local deterministic evidence.

Acceptance tests:

- Demo includes verified, unverified, conflicting, and not-dispatched outcomes.
- Incident export and static console surface conflict status and limitations.
- Built-in rules match demo evidence for unverified, conflicting, and
  not-dispatched cases.

Rollback: restore the previous 16-event demo and docs.

Owner gate: promoting the stricter restricted-exfiltration contract into the
default demo requires adding `action.normalized` evidence and reviewing detection
coverage language.

## Phase 4: Correctness, Recovery, Security, Compatibility

Status: Codex-executable alpha gates implemented; external validation remains.

Codex-executable work:

- Keep golden journals readable and projectable.
- Keep scanners, SBOM, dependency license checks, dependency audit, and local
  provenance in CI.
- Keep provenance subjects limited to release artifacts.
- Keep branch-enabled total coverage and concise GitHub job-summary evidence in
  CI as non-regression release signals.
- Add benchmarks when release cadence needs them.

External validation:

- Independent security review.
- Real deployment recovery exercise.
- Third-party compatibility fixture contribution.

## Phase 5: Release Packaging And Public Proof

Status: Codex-executable alpha packaging proof and release-publishing workflow implemented; external package-index gates remain.

Codex-executable work:

- Keep Docker build and smoke tests in CI.
- Keep deployment docs preview-labeled.
- Generate local wheel, sdist, SBOM, dependency license report, and unsigned
  provenance.
- Generate a local release proof review index from the release-candidate
  manifest so reviewers can verify artifact hashes and gate status from one
  file.
- Build release artifacts in GitHub Actions.
- Generate GitHub artifact attestations for release artifacts.
- Prepare manual TestPyPI/PyPI Trusted Publishing jobs without package-index
  tokens.

External validation:

- Configure TestPyPI and PyPI Trusted Publisher records for `release.yml`.
- Run TestPyPI and PyPI publish jobs.
- Link successful attestation verification from release notes.
- Confirm branch protection, CodeQL, Dependabot alerts, secret scanning, push
  protection, and private vulnerability reporting in GitHub.

## Phase 6: External Review Readiness

Status: review preparation is implemented for public alpha; actual review and
adoption evidence remain external validation.

Acceptance tests:

- External review guide gives a five-minute install path, expected outputs,
  semantics to challenge, safe data-sharing rules, and feedback routes.
- Security and agent-platform review checklists preserve maturity labels and
  product invariants.
- Evaluation reproduction commands cover public package, repository demo,
  Agent Validation, local release proof, and the generated release proof review
  index without requiring credentials.
- Issue templates collect reproducible, minimized feedback without requesting
  secrets or private data.

Rollback: remove the review docs and templates. No event-schema migration is
involved.

Stop condition: any review-readiness text claims external audit, external
adoption, production use, independent review, or community validation without
real evidence.

## 1.0 Exit Criteria

ActionLineage should not call itself 1.0 until all of the following are true:

- Public APIs have a compatibility policy and deprecation window.
- Default install works without cloning the repository.
- Demo and docs are validated from published artifacts.
- Security controls and release artifacts are externally verifiable.
- At least one outside user or reviewer has exercised the public release path.
- Preview service/deployment surfaces are either hardened or clearly excluded
  from 1.0 support.
