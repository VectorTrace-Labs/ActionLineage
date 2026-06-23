# Public Alpha Hardening Plan

Last reviewed: 2026-06-23.

Historical snapshot: this plan records the public-alpha hardening baseline from
commit `0e500d65d90fbda691d13e63ab58091e85083525` before later `0.1.0a5` and
`0.1.0a6` release-state changes. Preserve its point-in-time findings; use
`README.md`, `docs/PUBLISHING.md`, and `docs/QUALITY_SCORECARD.md` for current
release status.

This plan records the measured hardening baseline for ActionLineage public
alpha work. It is intentionally scoped to release integrity, onboarding proof,
quality evidence, security and reliability hardening, and external-review
readiness. It does not expand ActionLineage beyond the current evidence and
detection plane.

## Baseline Snapshot

| Item | Baseline |
| --- | --- |
| Local branch | `codex/public-alpha-hardening` |
| Baseline commit | `0e500d65d90fbda691d13e63ab58091e85083525` |
| Local version sources before edits | `pyproject.toml` and `actionlineage.__version__` were `0.1.0a3` |
| Local tags | `v0.1.0a1`, `v0.1.0a2`, `v0.1.0a3` |
| Public PyPI/TestPyPI state | `0.1.0a3`, `Requires-Python: >=3.12`, wheel and sdist present |
| GitHub release state | GitHub tag `v0.1.0a3` exists; GitHub Releases listed `v0.1.0a2` and `v0.1.0a1` only |
| Supported Python | 3.12 and 3.13 in metadata and CI |
| Runtime dependencies | 2 direct runtime dependencies: `pydantic`, `typer` |
| Optional release surfaces | adapters, cloud, console, service, dev, and eval remain separately scoped |

## Baseline Verification

| Command | Result |
| --- | --- |
| `uv sync --locked --all-extras` | PASS |
| `uv run ruff check .` | PASS |
| `uv run ruff format --check .` | PASS, 126 files already formatted |
| `uv run mypy src` | PASS, 56 source files |
| `uv run pytest` | PASS, 261 passed, 1 skipped |
| `uv run pytest --cov=actionlineage --cov-branch --cov-report=term` | PASS, 86 percent total coverage, 261 passed, 1 skipped |
| `uv run python scripts/check_claims_language.py .` | PASS, no findings |
| `uv run python scripts/secret_scan.py .` | PASS, no findings |
| `uv run python scripts/generate_sbom.py --output build/baseline/actionlineage-sbom.json` | PASS, 22 package entries |
| `uv run pip-audit` | PASS, no known vulnerabilities |
| `uv build --out-dir build/baseline/dist` | PASS, wheel and sdist built |
| `uv run python scripts/generate_release_provenance.py --dist-dir build/baseline/dist --output build/baseline/actionlineage-release-provenance.json` | PASS, 2 subjects |
| `uvx --prerelease allow --from actionlineage==0.1.0a3 actionlineage version` | PASS, returned `0.1.0a3` |
| `uvx --prerelease allow --from actionlineage==0.1.0a3 actionlineage demo run --output-dir build/baseline/public-pypi-demo` | PASS, 18 events |
| `uvx --prerelease allow --from actionlineage==0.1.0a3 actionlineage journal verify build/baseline/public-pypi-demo/evidence.jsonl` | PASS, 18 records verified |
| `PYTHONPATH=evals uv run --group eval python -m actionlineage_evals validate-scenarios` | PASS, 12 scenarios |
| `PYTHONPATH=evals uv run --group eval python -m actionlineage_evals coverage --strict` | PASS, 48 of 48 declared capabilities covered |
| `PYTHONPATH=evals uv run --group eval python -m actionlineage_evals run --scenario-path evals/scenarios --artifact-root build/baseline/evals --mode scripted --model-adapter scripted --seeds 1` | PASS, 12 scorecards |
| `PYTHONPATH=evals uv run --group eval python -m actionlineage_evals audit-artifacts build/baseline/evals` | PASS, 293 files scanned, 0 leaks |

## Measured Timings

These are local measurements from macOS with Python 3.13.5. They are baseline
data, not universal performance guarantees.

| Operation | Measurement |
| --- | --- |
| Public PyPI `uvx` version install/run | 13 packages installed; 1.57 seconds end to end |
| Built-wheel `uvx` version install/run | 13 packages installed; 0.95 seconds end to end |
| Repository deterministic demo | 0.46 seconds |
| Journal verification for 18-event demo | 0.26 seconds |
| Contract validation for demo journal | 0.27 seconds |
| Projection rebuild for 18-event demo | 0.26 seconds |

## Baseline Findings

| ID | Priority | Finding | Status |
| --- | --- | --- | --- |
| PALPHA-001 | P0 | GitHub tag `v0.1.0a3` exists, but no GitHub Release object for that tag was visible in read-only release listing. Creating or editing a GitHub Release requires owner approval. | BLOCKED_ON_OWNER |
| PALPHA-002 | P0 | `CHANGELOG.md` used a `1.0.0` heading for alpha release contents while package sources were `0.1.0a3`. | FIXED_IN_SLICE |
| PALPHA-003 | P1 | Package metadata lacked PEP 621 project URLs, reducing PyPI discoverability until the next release. | FIXED_LOCALLY_PENDING_RELEASE |
| PALPHA-004 | P1 | Baseline sdist included `.hypothesis/` local state, increasing artifact noise and review burden. | FIXED_IN_SLICE |
| PALPHA-005 | P1 | Coverage run emitted many `ResourceWarning: unclosed database` warnings in console, projection, contract, and service tests. | FIXED_IN_RELIABILITY_SLICE |
| PALPHA-006 | P1 | Public package metadata on PyPI/TestPyPI has no project URLs until a later owner-approved release uploads corrected metadata. | BLOCKED_ON_RELEASE |
| PALPHA-007 | P2 | Local Python `urllib` could not verify public TLS due to local certificate-store configuration, while browser/curl checks succeeded. Online release-consistency JSON metadata and project URL HEAD checks now fall back to bounded read-only `curl` after `urllib` URL/TLS failures. | MITIGATED_WITH_CURL_FALLBACK |
| PALPHA-008 | P2 | Service-mode verification emitted Starlette/FastAPI test-client deprecation warnings unless the dev-only `httpx2` backend was installed. | FIXED_IN_TEST_CLIENT_SLICE |
| PALPHA-009 | P2 | Local release proof documented license review expectations but lacked an executable dependency license report gate. | FIXED_IN_LICENSE_GATE_SLICE |
| PALPHA-010 | P2 | Local release-candidate artifacts had hashes and a manifest, but lacked a generated reviewer index that verifies artifact bytes and collects owner/external gates in one place. | FIXED_IN_REVIEW_INDEX_SLICE |
| PALPHA-011 | P2 | Local release-candidate manifest contents were documented but manifest generation itself was not a committed, repeatable script. | FIXED_IN_MANIFEST_GENERATOR_SLICE |
| PALPHA-012 | P2 | The GitHub release artifact bundle did not yet generate or smoke-check the release-candidate manifest and review index produced by the local proof scripts. | FIXED_IN_RELEASE_WORKFLOW_PROOF_SLICE |
| PALPHA-013 | P1 | Public package long descriptions can lag the corrected source README and still contain stale owner-gated GitHub Release wording until the next owner-approved package upload. | BLOCKED_ON_RELEASE |
| PALPHA-014 | P2 | Local release-proof reproduction docs mixed `/tmp` distribution artifacts with `build/release-candidate` manifest inputs, making copy-paste verification harder. | FIXED_IN_RELEASE_PROOF_DOCS_SLICE |
| PALPHA-015 | P1 | Owner-approved TestPyPI/PyPI publication jobs did not yet have a bounded, clean-environment post-publication verification lane for the exact published tag version. | FIXED_IN_POST_PUBLICATION_VERIFY_SLICE |
| PALPHA-016 | P2 | Review outreach had only an inline announcement note and lacked a maintainer-reviewable release/evaluation announcement plus technical article outline. | FIXED_IN_OUTREACH_DRAFTS_SLICE |
| PALPHA-017 | P2 | Good first issue ideas were only short bullets, not maintainer-ready candidates with scope, acceptance criteria, verification commands, and out-of-scope boundaries. | FIXED_IN_GOOD_FIRST_ISSUES_SLICE |
| PALPHA-018 | P2 | The repository-local Markdown link checker validated local files but did not catch stale same-document or `file.md#heading` fragments in reviewer-facing docs. | FIXED_IN_MARKDOWN_FRAGMENT_CHECK_SLICE |
| PALPHA-019 | P2 | Static console context controls had escaping, bounds, redaction, and CSP coverage, but lacked one hostile fixture that exercised note and saved-view fields together with HTML-like strings, link-like text, hostile-looking filenames, and secret-like canaries. | FIXED_IN_HOSTILE_CONSOLE_CONTEXT_SLICE |
| PALPHA-020 | P2 | Static console empty selectors rendered an empty timeline and verification table body instead of explicit no-match rows, making zero-result review artifacts less clear. | FIXED_IN_EMPTY_CONSOLE_TIMELINE_SLICE |
| PALPHA-021 | P2 | Static console empty-selector proof covered the renderer directly but not the public `projection export-console` CLI path used by first-time evaluators. | FIXED_IN_EMPTY_CONSOLE_CLI_SLICE |
| PALPHA-022 | P2 | Static console CLI coverage exercised trace-ID exports and empty selectors, but not the alternate public `--run-id` selector path. | FIXED_IN_RUN_ID_CONSOLE_CLI_SLICE |
| PALPHA-023 | P2 | Static console CLI coverage exercised valid selectors but did not prove ambiguous `--trace-id` plus `--run-id` input fails clearly without writing an HTML artifact. | FIXED_IN_CONSOLE_SELECTOR_EXCLUSIVITY_SLICE |
| PALPHA-024 | P2 | Journal append preflight and write I/O failures could surface raw operating-system exceptions rather than bounded ActionLineage journal errors with lock-release regression coverage. | FIXED_IN_JOURNAL_IO_FAILURE_SLICE |

## Phase Plan

This table separates repository-controlled hardening from owner or external
validation. `Local complete` means the current branch has committed
implementation, documentation, tests, or deterministic evidence for the stated
scope; it does not claim publication, production readiness, or independent
review. Owner or external gates stay open until there is public, independently
verifiable evidence.

| Phase | Scope | Repo-controlled status | Remaining gate or reason not fully done | ETA class |
| --- | --- | --- | --- | --- |
| 0 | Baseline and public-claim audit | Local complete for current branch: baseline measurements, public-claim scans, secret scan, SBOM, dependency audit, package smoke, and evaluation baseline were captured. | Refresh before final announcement or release-candidate cut. | Done locally; refresh-only |
| 1 | Release and version consistency | Local complete except public release object: checker added; release workflow now prepares bounded post-publication package-index verification after owner-approved publishing. | GitHub Release object for `v0.1.0a5` remains owner-gated until tag-matched artifacts exist. | Blocked on owner action |
| 2 | Package metadata and discoverability | Local complete: metadata and sdist hygiene were improved in source. | PyPI/TestPyPI pages keep old `0.1.0a3` metadata until the next owner-approved `0.1.0a5` package release. | Blocked on owner release |
| 3 | README landing experience and visual proof | Local complete: generated demo evidence map and freshness check added; static console trace-ID, run-ID, empty-selector, and ambiguous-selector CLI paths now have coverage. | Optional outside evaluator feedback may still improve onboarding language. | Done locally |
| 4 | Clean installation and first-time-user testing | Local complete: baseline public package smoke was captured; built wheel and sdist first-time-user smoke gate added to CI; evaluator troubleshooting guide added. | Post-publication smoke must run again after any new owner-approved package upload. | Done locally; rerun after release |
| 5 | Visible quality and security evidence | Local complete: CI now runs repository-local Markdown link and heading-fragment checking, dependency license reporting, an 85 percent branch-enabled total coverage floor, dependency audit, and concise quality/security evidence summaries. Authenticated GitHub read confirmed main branch protection, strict required checks, Dependabot security updates, secret scanning, push protection, private vulnerability reporting, security policy, latest `main` CodeQL success, and current alert counts. | Recheck before public announcement if repository settings or default-branch state change. | Done locally; authenticated external evidence recorded |
| 6 | Agent Validation Lab public evidence | Local complete for no-model public-alpha evidence: deterministic baseline report is generated into `docs/evidence/agent-validation-baseline.*` from 12 scorecards; scheduled no-model artifacts run on trusted default-branch code. | Optional live-model evidence requires maintainer-provided `GH_MODELS_TOKEN`; no live-model claim is made. | Done locally for no-model evidence |
| 7 | Reliability and adversarial hardening | Local complete for current branch: SQLite close handling, static console context bounds/CSP/redaction/escaping, run-ID CLI coverage, selector-exclusivity rejection, empty selector no-match renderer/CLI fixtures, verified-prefix recovery, truncated-journal rejection, bounded journal append preflight/write I/O failure handling, ambiguous HTTP observer fixture behavior, and warning-free service-mode tests are covered. | Independent security review may still find issues; no additional repo-controlled Phase 7 blocker is known. | Done locally; external review pending |
| 8 | External review and community readiness | Local preparation complete: review guides, reproduction docs, structured feedback templates, good first issue candidates, generated manifest command, generated release-proof review index command, and outreach drafts were added. | Actual independent review, outside adoption, or public feedback remains external validation. | External timeline |
| 9 | Release-candidate audit | Local proof refreshed for this hardening pass: full tests, 86.14 percent branch-enabled coverage, built wheel/sdist smoke, SBOM, dependency license report, dependency audit, provenance, release consistency, Agent Validation, generated manifest, generated review index, checksums, and authenticated GitHub security-setting reads are documented. | Rerun the generated manifest/review-index proof after any later source or documentation commit before publication; GitHub Release and package publication remain owner-gated. | Done locally; rerun after any new commit |

## Owner Gates

- Create a GitHub Release for `v0.1.0a5`.
- Publish any new package, container, release artifact, tag, or registry object.
- Change public version posture, schema namespace, production/stable claims, or
  external-review claims.
- Confirm public package visibility for any newly published package or
  container artifact.
