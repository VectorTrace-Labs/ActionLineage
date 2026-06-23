# Quality Scorecard

Last reviewed: 2026-06-23.

This scorecard maps public claims to implementation, tests, demo evidence, and
maturity. It is the release-truth source for README, roadmap, security policy,
and checklist wording.

## Baseline

| Area | Current evidence |
| --- | --- |
| Branch | Baseline captured on `codex/public-alpha-hardening` from commit `0e500d65d90fbda691d13e63ab58091e85083525` |
| Hardening baseline | `docs/PUBLIC_ALPHA_HARDENING_PLAN.md` |
| Public claim audit | `docs/PUBLIC_CLAIM_AUDIT.md` |
| Required checks before hardening edits | Ruff, format, mypy, pytest, coverage, claim scan, secret scan, SBOM, pip-audit, build, provenance, demo, public PyPI smoke, and no-model Agent Validation baseline passed |
| Current alpha version | `0.1.0a3` |
| Supported Python | Python 3.12+ |
| Default demo | No model API key, cloud account, external service, or internet access |
| Known release blocker | GitHub tag `v0.1.0a3` exists, but no GitHub Release object for `v0.1.0a3` was visible in read-only release listing; current post-tag hardening proof should move through a new `0.1.0a4` repair release rather than being attached to `v0.1.0a3` |

## Claim Matrix

| Public claim | Implementation evidence | Test evidence | Demo or fixture evidence | Maturity |
| --- | --- | --- | --- | --- |
| Vendor-neutral evidence plane | `PROJECT_CHARTER.md`, `ARCHITECTURE.md`, `src/actionlineage/domain` | `tests/domain`, `tests/compatibility` | Demo uses local deterministic adapter | Alpha-supported |
| MCP is optional adapter behavior | `src/actionlineage/adapters/mcp`, import-boundary tests | `tests/adapters/test_mcp_descriptors.py`, `tests/adapters/test_mcp_sdk.py` | No MCP needed for demo | Preview |
| Core does not import MCP/OpenTelemetry/model providers/FastAPI/cloud SDKs | Package boundaries and lazy imports | Adapter import-boundary tests | Clean demo core path | Alpha-supported |
| `actionlineage.dev/v1alpha1` envelope is readable | `schemas/actionlineage-event-v1alpha1.schema.json`, `src/actionlineage/domain/events.py` | `tests/domain/test_events.py`, `tests/compatibility/test_golden_journals.py` | Golden journals | Alpha-supported |
| Unknown event types are preserved | `src/actionlineage/compatibility.py` | `tests/domain/test_events.py`, `tests/projection/test_sqlite_projection.py` | `vendor.future.observed` fixture path in tests | Alpha-supported |
| Redaction happens before persistence/export/error serialization | `src/actionlineage/domain/redaction.py`, serializers, exporters | `tests/domain/test_redaction.py`, `tests/security/test_release_hardening.py`, exporter tests | Canary fixtures | Alpha-supported |
| Append-only local journal is canonical evidence | `src/actionlineage/journal/local.py` | `tests/journal/test_local_journal.py` | Demo `evidence.jsonl`; append preflight/write I/O failures fail as bounded `JournalAppendError` paths without event-payload canary leakage and release the local lock | Alpha-supported |
| Hash-chain verification detects mutation, deletion, insertion, duplication, incomplete final records, and reorder when anchors make changes observable | Journal verifier and anchor helpers | `tests/journal/test_local_journal.py`, `tests/journal/test_anchors.py` | Demo verify command | Local-proof |
| Verified-prefix recovery preserves the original journal | `src/actionlineage/journal/anchors.py`, `docs/JOURNAL_INTEGRITY.md` | `tests/journal/test_anchors.py` | Recovery output is a separate file; source/output aliasing fails closed | Local-proof |
| Projection is rebuildable and disposable | `src/actionlineage/projection/sqlite.py` | `tests/projection/test_sqlite_projection.py` | Demo `projection.sqlite` rebuilt from journal | Alpha-supported |
| Incident export, case bundle, graph export, grounded summary, static console | Projection and console modules | `tests/projection`, `tests/console` | Demo console/export commands; trace-ID and run-ID console selectors render through the CLI; invalid dual-selector use fails with JSON and writes no HTML; empty console selectors render explicit no-match rows through the renderer and CLI without proof-of-absence wording | Alpha-supported |
| Static console annotations are bounded, redacted, escaped, and non-canonical | `src/actionlineage/console/static.py`, `docs/CONSOLE.md` | `tests/console/test_static_console.py` | Console context fails closed for oversized annotations, escapes hostile note and saved-view fields, redacts canaries, and renders CSP-protected HTML | Alpha-supported |
| Source-neutral ingestion exists | `src/actionlineage/evidence` | `tests/evidence` | README API example | Alpha-supported |
| Evidence links include subject, evidence event, relationship, observer, confidence, status, and limitations | `EvidenceLink` model and schema | `tests/domain/test_evidence.py`, compatibility schema tests | Demo verified and conflicting events | Alpha-supported |
| Ambiguous observer correlation remains unverified | `src/actionlineage/observers/local.py`, `tests/fixtures/adversarial/security-regressions.json` | `tests/observers/test_local_observers.py`, `tests/security/test_release_hardening.py` | Minimized `correlation_ambiguity` adversarial fixture keeps multiple plausible HTTP observations out of `verified` status | Local-proof |
| Tool acknowledgement is not side-effect verification | Demo scenario and detection rules | `tests/demo`, `tests/detection/test_sequence.py` | Unverified HTTP send | Alpha-supported |
| Demo covers verified outcome | Demo scenario | `tests/demo/test_scenario.py` | Filesystem-observed read | Alpha-supported |
| Demo covers unverified outcome | Demo scenario | `tests/demo/test_scenario.py` | Acknowledged HTTP send without corroboration | Alpha-supported |
| Demo covers not-dispatched outcome | Demo scenario | `tests/demo/test_scenario.py`, adapter tests | Policy-denied shell-like request | Alpha-supported |
| Demo covers conflicting outcome | Demo scenario | `tests/demo/test_scenario.py`, observer tests | Receiver mismatch and conflict event | Alpha-supported |
| Demo evidence map is generated from local demo artifacts | `scripts/generate_demo_evidence_map.py`, README, demo docs | `tests/security/test_release_hardening.py`, CI demo-map step | `demo-evidence-map.svg` and `demo-evidence-map.json` generated under `build/` or `/tmp` | Local-proof |
| Five-minute demo contract validates | `contracts/examples/outbound-http.json` | Contract validation tests | Demo journal validates with outbound HTTP contract | Alpha-supported |
| Restricted-exfiltration contract is a stricter design example | Contract examples and docs | Contract tests | Not the default demo contract | Preview |
| Sequence detections support bounded operators, windows, grouping, suppression, deduplication, and evidence refs | `src/actionlineage/detection` | `tests/detection` | Demo aligns with built-in rules AL-DET-003, AL-DET-004, AL-DET-005 | Local-proof |
| Lineage Lab supports replay, mutation, minimization, and scorecards | `src/actionlineage/lab` | `tests/lab` | Deterministic demo replay case | Local-proof |
| Agent Validation Lab provides development-only agent scenario validation, no-model replay, provenance, artifact audits, and bounded scheduled evaluation lanes | `evals/`, `.github/workflows/agent-validation.yml`, `docs/AGENT_VALIDATION_ARCHITECTURE.md`, `docs/AGENT_VALIDATION_EVIDENCE.md`, `docs/evidence/agent-validation-baseline.*` | `tests/evals/test_agent_validation_lab.py`, `tests/release/test_release_readiness.py`, agent-validation CI lanes | Generated public baseline report covers 11 scripted scorecards, 47/47 declared capabilities, source commit, seeds, tool descriptor hashes, event/evidence coverage, failure classes, artifact paths, and 0 audited leaks; scheduled no-model artifacts run on trusted default-branch code; optional live-model execution is skipped unless `GH_MODELS_TOKEN` is configured | Local-proof |
| JSON Lineage Contracts validate events, fields, links, integrity, latency, and detection coverage | `src/actionlineage/contracts` | `tests/contracts` | Demo outbound HTTP contract | Alpha-supported |
| YAML contract/rule examples are review aids | Optional PyYAML loader and docs | Detection YAML loader tests | YAML examples under `contracts`, `detections`, `scenarios` | Preview |
| OpenTelemetry and SIEM/export integrations are non-canonical mirrors | `src/actionlineage/exporters` | `tests/exporters` | Local mapping tests | Preview |
| Optional service mode exists | `src/actionlineage/service` | `tests/service` | Docker/Compose smoke in CI | Preview |
| Service-mode test client stays outside runtime scope | `pyproject.toml`, `docs/DEPENDENCY_POLICY.md` | `tests/release/test_release_readiness.py`, `tests/service` | Dev-only `httpx2` backend removes Starlette/FastAPI test warnings without adding to the alpha runtime TCB | Local-proof |
| Optional Postgres projection schema exists | `src/actionlineage/projection/postgres.py` | `tests/projection/test_postgres_projection.py` | Local statement fixtures | Preview |
| Cloud/Kubernetes observers exist as fixture-backed observers | `src/actionlineage/observers/cloud.py` | `tests/observers/test_cloud_observers.py` | No live cloud required | Preview |
| Public release metadata is alpha and supports Python 3.12+ | `pyproject.toml`, `src/actionlineage/__init__.py` | `tests/release/test_release_readiness.py`, CI/release workflow matrices | CLI `version` output | Alpha-supported |
| Release hardening scripts exist | `scripts/` | `tests/security/test_release_hardening.py` | SBOM, dependency license report, provenance, offline release-consistency report, release-candidate manifest, and release proof review index generated locally | Local-proof |
| CI runs local release proof gates | `.github/workflows/ci.yml` | `tests/release/test_release_readiness.py` | Branch-enabled coverage floor, wheel, sdist, first-time-user artifact smoke, SBOM, dependency license check, dependency audit, Markdown link check, and unsigned provenance are generated in CI | Local-proof |
| CI publishes concise quality/security evidence summary | `scripts/write_ci_quality_summary.py`, `.github/workflows/ci.yml`, `docs/RELEASE_CHECKLIST.md` | `tests/security/test_release_hardening.py`, `tests/release/test_release_readiness.py` | GitHub job summary reports Python version, line/branch/combined coverage, demo visual, SBOM, dependency license report, provenance, artifacts, and quickstart smoke evidence | Local-proof |
| Built artifacts pass first-time-user smoke | `scripts/smoke_public_quickstart.py`, `.github/workflows/ci.yml`, `docs/RELEASE_CHECKLIST.md` | `tests/security/test_release_hardening.py`, `tests/release/test_release_readiness.py` | Built wheel and sdist run version, demo, journal verify, contract validate, case export, and static console export | Local-proof |
| First-time evaluator troubleshooting is documented without expanding support claims | `docs/TROUBLESHOOTING.md`, README documentation map, `docs/EVALUATION_REPRODUCTION.md`, `docs/RELEASE_CHECKLIST.md` | `tests/release/test_release_readiness.py` | Troubleshooting covers prerelease install, Python 3.12+ support, `uv`/`pipx`/`pip` behavior, optional extras, demo failures, path/browser issues, offline/online boundaries, release proof/review-index diagnostics, and safe failure reports | Local-proof |
| Repository-local Markdown links and heading fragments are checked without network credentials | `scripts/check_markdown_links.py`, `.github/workflows/ci.yml`, `docs/RELEASE_CHECKLIST.md` | `tests/security/test_release_hardening.py`, `tests/release/test_release_readiness.py` | CI and release checklist run `uv run python scripts/check_markdown_links.py .`; the checker validates local files, same-document anchors, and `file.md#heading` fragments while ignoring external URLs | Local-proof |
| Release workflow builds, verifies on Python 3.12/3.13, attests artifacts, and prepares post-publication smoke evidence | `.github/workflows/release.yml`, `docs/PUBLISHING.md` | `tests/release/test_release_readiness.py`, `scripts/check_release_consistency.py` | Local workflow definition builds wheel/sdist, SBOM, dependency license report, provenance, offline release-consistency report, release-candidate manifest, review index, checksums, and attestations; after an owner-approved TestPyPI/PyPI publish, the workflow waits boundedly for package-index propagation, installs the exact tag version on Python 3.12/3.13, verifies installed metadata, runs public quickstart smoke, and uploads post-publication reports; GitHub Release object for `v0.1.0a3` remains owner-gated | Local-proof / External-validation-required |
| Release-candidate audit prepares owner review without publishing | `docs/RELEASE_CANDIDATE_AUDIT.md`, `docs/DRAFT_RELEASE_NOTES_0.1.0a3.md`, `docs/OWNER_PUBLICATION_CHECKLIST.md` | `tests/release/test_release_readiness.py`, release-candidate command suite | Generated local manifest, generated review index with release-consistency summaries, wheel/sdist hashes, 318-test full suite, 86.14 percent branch-enabled coverage, demo proof, Agent Validation summary, authenticated GitHub branch-protection/secret-scanning reads, and owner/external gates are documented | Local-proof / External-validation-required |
| GHCR container publishing path exists | `.github/workflows/release.yml`, `docs/PACKAGE_MANAGERS.md` | `tests/release/test_release_readiness.py` | Workflow path can build, smoke-test, and push tagged preview images; public GHCR visibility requires external validation | Preview |
| TestPyPI/PyPI Trusted Publishing publishes packages | `.github/workflows/release.yml`, `docs/PUBLISHING.md` | `tests/release/test_release_readiness.py` | TestPyPI run `27973522992`; PyPI run `27973832210`; fresh Python 3.12 `uvx` install, demo, and journal verify passed | Alpha-supported |
| External review and evaluation workflow is prepared without claiming validation | `docs/EXTERNAL_REVIEW_GUIDE.md`, `docs/SECURITY_REVIEW_CHECKLIST.md`, `docs/AGENT_PLATFORM_REVIEW_CHECKLIST.md`, `docs/EVALUATION_REPRODUCTION.md`, `docs/GOOD_FIRST_ISSUES.md`, `docs/REVIEW_OUTREACH_DRAFTS.md`, issue templates | `tests/release/test_release_readiness.py` | Reproduction commands, safe feedback routes, case-study template, good first issue candidates, announcement draft, and technical article outline are documented; real feedback remains external-validation | Local-proof / External-validation-required |
| GitHub security controls are enabled | `.github/workflows` plus repository settings | Workflow files and API validation | GitHub UI/API required | External-validation-required |
| Homebrew tap exists | `docs/PACKAGE_MANAGERS.md` | Documentation tests | Tap repository and validated formula required | Planned |
| PyPI package exists | `docs/PUBLISHING.md`, `docs/PACKAGE_MANAGERS.md` | Fresh package install smoke and release-consistency checker | `https://pypi.org/project/actionlineage/` publishes `0.1.0a3` with `Requires-Python: >=3.12`; fresh install/demo smoke passed; online checker detects known stale package-description claims when package JSON is reachable, including through bounded read-only `curl` fallback after local `urllib` URL/TLS failures | Alpha-supported / External-validation-required |
| TestPyPI package exists | `docs/PUBLISHING.md`, `docs/PACKAGE_MANAGERS.md` | Fresh package install smoke and release-consistency checker | `https://test.pypi.org/project/actionlineage/` publishes `0.1.0a3` with `Requires-Python: >=3.12`; fresh install/demo smoke passed; online checker detects known stale package-description claims when package JSON is reachable, including through bounded read-only `curl` fallback after local `urllib` URL/TLS failures | Alpha-supported / External-validation-required |
| Package-index organization ownership transfer | `docs/PACKAGE_MANAGERS.md`, `docs/DECISIONS_REQUIRED.md` | Not executable locally | PyPI/TestPyPI organization approval and ownership transfer required | External-validation-required |
| GHCR package exists | Release checklist and publishing guide | Release workflow container smoke | Public GHCR package visibility has not been independently confirmed in this baseline | External-validation-required |

## Known Highest Risks

| Risk | Impact | Current control | Next action |
| --- | --- | --- | --- |
| Preview surfaces look production-ready | Misleading public expectations | Maturity labels in README/docs | Keep scorecard updated with every public claim |
| External security controls can drift after point-in-time reads | False confidence before announcement | Authenticated GitHub reads confirmed branch protection, strict required checks, Dependabot security updates, secret scanning, push protection, private vulnerability reporting, security policy, latest `main` CodeQL success, 0 Dependabot alerts, 0 secret-scanning alerts, 0 repository security advisories, and no open CodeQL alerts | Recheck before announcement or publication if repository settings or default-branch state change |
| Service/deployment examples are not production hardened | Operational misuse | Preview labels and security docs | External deployment review before broader claims |
| Demo and contract examples can drift | Broken onboarding | Demo tests and contract validation | Keep README quickstart tied to passing contract |
| Built package artifacts can drift from source-checkout quickstart | Broken first-time-user path | CI smokes built wheel and sdist through `scripts/smoke_public_quickstart.py` | Keep the smoke path focused on documented public CLI commands |
| Coverage can regress quietly while tests remain green | Weaker release evidence for critical paths | CI runs pytest with branch coverage and an 85 percent branch-enabled total coverage floor | Treat the floor as a non-regression guard, not a public coverage badge |
| Documentation links can drift during review preparation | Broken onboarding and reproduction paths | Repository-local Markdown link and heading-fragment checker in CI and release checklist | Keep the checker local by default and treat external URL reachability as separate release/publication evidence |
| Local hash chains can be overinterpreted | Integrity overclaim | Threat model and journal integrity docs | Continue using precise trust-limit wording |
| GitHub Release object can drift from tags/package indexes | Broken release audit trail | Release-consistency checker and owner gate | Use a new owner-approved `0.1.0a4` release for the current hardening proof, or rebuild exactly from `v0.1.0a3` before repairing that release |
| Public package long descriptions can lag source docs | Stale package-index claims after local README corrections | Online release-consistency checker detects known stale owner-gated release wording when package JSON is reachable | Publish corrected metadata only through an owner-approved release; recommended repair version is `0.1.0a4` |
| Local Python certificate stores can block online release checks | Public release drift may appear as UNKNOWN instead of actionable evidence | JSON metadata checks and project URL HEAD checks fall back to bounded read-only `curl` after local `urllib` URL/TLS failures | Keep online checks non-mutating and keep owner/external gates separate from local reachability |
| Test-only service dependencies can look like runtime scope | Inflated support or TCB claims | Dependency policy and release-readiness tests keep `httpx2` in the dev extra and out of service/runtime extras | Revisit if Starlette/FastAPI changes their test-client backend again |
| Projection SQLite handle closure can regress | Reliability signal can be missed in noisy verification output | Projection API closes connection handles and has warning-as-error regression coverage | Keep warning-as-error projection test in release verification |
| Journal append I/O failures can leak raw operating-system details or leave stale locks | Confusing failure handling or blocked future writes after disk-full or permission errors | Append preflight and write I/O failures are wrapped as bounded `JournalAppendError` messages, avoid event-payload leakage, and release the sidecar lock | Keep simulated I/O failure tests in release verification |
| Recovery tooling could accidentally mutate canonical journals | Loss of original evidence during incident recovery | Verified-prefix export rejects in-place output and streams only verified records to a separate file; truncated final records stop verification at the prior verified prefix | Keep API and CLI in-place rejection tests |
| Empty console selectors can be mistaken for no activity | Misleading review artifact | Static console renderer and CLI export path render explicit no-match rows and state missing observation only means no observation was recorded | Add case-context failure-path coverage if projection behavior changes |
| Static console context can become an oversized or unsafe rendered artifact | Browser-side and review-bundle risk | Context file/item bounds, redaction/truncation markers, strict escaping, CSP tests, and a hostile note/saved-view context fixture | Extend hostile context fixtures when context fields or render surfaces change |
| Similar or duplicated observer records can create false certainty | Incorrect investigation timeline | HTTP fixture observers return unverified ambiguity instead of selecting one plausible match | Extend ambiguity fixtures as new observer families are added |
| Review-readiness docs can be mistaken for validation | Misleading social proof | External-review docs and scorecard separate readiness from actual external evidence | Keep actual reviews, adoption, and production history external-validation until real artifacts exist |
| Release-candidate preparation can be mistaken for publication | Broken release expectations | Release-candidate audit and owner checklist mark publication and release-object work as owner-gated | Do not push, tag, publish, or create release objects from local audit work |

## Release Gate Summary

Before publishing an alpha tag or announcement:

```bash
uv sync --locked --all-extras
uv run ruff check .
uv run ruff format --check .
uv run mypy src
uv run pytest --cov=actionlineage --cov-branch --cov-report=term --cov-report=xml:/tmp/actionlineage-coverage.xml --cov-fail-under=85
uv run actionlineage demo run --output-dir /tmp/actionlineage-demo
uv run python scripts/generate_demo_evidence_map.py --demo-dir /tmp/actionlineage-demo
uv run python scripts/generate_demo_evidence_map.py --demo-dir /tmp/actionlineage-demo --check
uv run python scripts/check_claims_language.py .
uv run python scripts/check_markdown_links.py .
uv run python scripts/secret_scan.py .
rm -rf /tmp/actionlineage-release-proof
mkdir -p /tmp/actionlineage-release-proof
uv run python scripts/generate_sbom.py --output /tmp/actionlineage-release-proof/actionlineage-sbom.json
uv run python scripts/check_dependency_licenses.py --output /tmp/actionlineage-release-proof/actionlineage-license-report.json
uv run pip-audit
uv build --out-dir /tmp/actionlineage-release-proof/dist
uv run python scripts/smoke_public_quickstart.py --package-spec /tmp/actionlineage-release-proof/dist/actionlineage-0.1.0a3-py3-none-any.whl --output-dir /tmp/actionlineage-wheel-smoke
uv run python scripts/smoke_public_quickstart.py --package-spec /tmp/actionlineage-release-proof/dist/actionlineage-0.1.0a3.tar.gz --output-dir /tmp/actionlineage-sdist-smoke
uv run python scripts/check_release_consistency.py --dist-dir /tmp/actionlineage-release-proof/dist --output /tmp/actionlineage-release-proof/release-consistency-offline.json
uv run python scripts/generate_release_provenance.py --dist-dir /tmp/actionlineage-release-proof/dist --output /tmp/actionlineage-release-proof/actionlineage-release-provenance.json
uv run python scripts/write_ci_quality_summary.py --python-version 3.13 --coverage-xml /tmp/actionlineage-coverage.xml --coverage-floor 85 --sbom /tmp/actionlineage-release-proof/actionlineage-sbom.json --license-report /tmp/actionlineage-release-proof/actionlineage-license-report.json --provenance /tmp/actionlineage-release-proof/actionlineage-release-provenance.json --dist-dir /tmp/actionlineage-release-proof/dist --wheel-smoke-dir /tmp/actionlineage-wheel-smoke --sdist-smoke-dir /tmp/actionlineage-sdist-smoke --demo-map-svg /tmp/actionlineage-demo/demo-evidence-map.svg --output /tmp/actionlineage-ci-summary.md
uv run python scripts/write_release_candidate_manifest.py --artifact-root /tmp/actionlineage-release-proof --dist-dir /tmp/actionlineage-release-proof/dist --gate "ruff_check|PASS|uv run ruff check ." --output /tmp/actionlineage-release-proof/manifest.json
uv run python scripts/write_release_review_index.py --manifest /tmp/actionlineage-release-proof/manifest.json --output /tmp/actionlineage-release-proof/REVIEW_INDEX.md
gh workflow run release.yml -f publish_target=none
```

Clean-snapshot validation should also run from `git archive HEAD` with
`uv run --all-extras pytest`.
