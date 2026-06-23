# Release Candidate Audit

Last reviewed: 2026-06-23.

Historical snapshot: this document evaluated the `0.1.0a5` release candidate
before the `v0.1.0a5` tag and package publication completed. Its point-in-time
release-state findings are preserved for auditability and may be stale. Current
release status lives in `README.md`, `docs/PUBLISHING.md`, and
`docs/QUALITY_SCORECARD.md`.

This audit prepares the current public-alpha candidate for owner review. It does
not publish, tag, push, upload, create a GitHub Release, or modify repository
settings.

## Candidate

| Item | Result |
| --- | --- |
| Branch | `codex/release-0.1.0a5` |
| Audited implementation commit | Recorded in generated manifest field `audited_implementation_commit`; rerun after any source or documentation commit before publication |
| Version tag alignment | OWNER REVIEW REQUIRED; generated `build/release-candidate/REVIEW_INDEX.md` records the `v0.1.0a5` tag commit when the tag exists and whether it matches the audited implementation commit; do not attach local artifacts to a tag release when this field is `false` or `unknown` |
| Candidate version | `0.1.0a5` |
| Recommendation | Do not republish immutable PyPI/TestPyPI files for `0.1.0a3` or attach post-tag hardening proof to the `v0.1.0a3` release; use the new owner-approved `0.1.0a5` release for metadata and release-object repair after local gates pass. |
| Generated local manifest | `build/release-candidate/manifest.json` |
| Generated review index | `build/release-candidate/REVIEW_INDEX.md` |

`v0.1.0a4` exists as a tag, and its release workflow verify jobs passed, but
the artifact build failed before artifact upload, package publication, or
GitHub Release creation because the tagged workflow used a non-canonical
provenance filename. Do not move that public tag or attach later artifacts to
it; use `0.1.0a5` for the corrective package and release-object repair path.

Generated artifacts under `build/release-candidate/` are local release proof and
are not committed source files. The generated manifest and review index are the
authoritative source for exact local artifact hashes because a documentation
commit changes the source archive.

## Gate Summary

| Gate | Status | Evidence |
| --- | --- | --- |
| Dependency synchronization | PASS | `uv sync --locked --all-extras`; eval group reinstalled for eval lane |
| Ruff lint | PASS | `uv run ruff check .` |
| Ruff format check | PASS | `uv run ruff format --check .`, 135 files already formatted |
| Strict mypy | PASS | `uv run mypy src`, 56 source files |
| Full pytest after public-alpha hardening slices | PASS | `319 passed`; no warning summary |
| Branch coverage with eval group | PASS | `319 passed`, 86.14 percent total coverage; no warning summary |
| Compatibility tests | PASS | Included in full suite; golden journals and public API tests passed |
| Property-based regression tests | PASS | Included in full suite through Hypothesis tests |
| Claim-language scan | PASS | `uv run python scripts/check_claims_language.py .` |
| Secret scan | PASS | `uv run python scripts/secret_scan.py .` |
| Dependency license check | PASS | 23 direct dependencies checked, 0 issues |
| Dependency audit | PASS | `uv run pip-audit`, no known vulnerabilities |
| Local Markdown link check | PASS | 45 links checked across 101 files; repository-relative links and heading fragments resolved |
| Clean tracked snapshot | PASS | Fresh `git archive HEAD` snapshot passed `317 passed, 1 skipped` with `uv run --all-extras pytest`; the skip was the optional eval-only `inspect_ai` import check |
| Wheel and sdist build | PASS | `uv build --out-dir build/release-candidate/dist` |
| Built wheel metadata | PASS | Version `0.1.0a5`, `Requires-Python: >=3.12`, six project URLs |
| Built sdist metadata | PASS | Version `0.1.0a5`, `Requires-Python: >=3.12`, six project URLs, no local cache entries |
| Built wheel smoke | PASS | `actionlineage version`, demo run, journal verify, contract validate, case export, and static console export succeeded from wheel |
| Built sdist smoke | PASS | `actionlineage version`, demo run, journal verify, contract validate, case export, and static console export succeeded from sdist |
| Deterministic demo | PASS | 18 events, last hash `sha256:c51f29aadf75d59dd69813e0348f6fbfe2a4297a31051bbdb362017aac01b981` |
| Journal verification | PASS | 18 records verified |
| Contract validation | PASS | `contracts/examples/outbound-http.json` |
| Case export | PASS | `build/release-candidate/case/` |
| Static console export | PASS | `build/release-candidate/console.html` |
| Demo evidence map freshness | PASS | SVG and JSON generated from `incident.json` and checked fresh |
| SBOM generation | PASS | 23 package entries |
| Dependency license report | PASS | `build/release-candidate/actionlineage-license-report.json` |
| Release provenance generation | PASS | 2 artifact subjects |
| SHA256 checksums | PASS | `build/release-candidate/SHA256SUMS.txt` |
| Release-candidate manifest generation | PASS | `scripts/write_release_candidate_manifest.py` generated `build/release-candidate/manifest.json` with 8 artifacts, 23 gates, and no manifest issues |
| Release proof review index | PASS | `build/release-candidate/REVIEW_INDEX.md` generated from the local manifest; 8 of 8 manifest-listed artifact hashes verified; release-consistency reports are summarized when present |
| Release workflow artifact proof | PASS | `.github/workflows/release.yml` generates `build/release/release-consistency-offline.json`, `build/release/manifest.json`, and `build/release/REVIEW_INDEX.md`, includes them in checksums and attestations, and smoke-checks the bundle after artifact download |
| Release consistency, offline | PASS | 0 failures, 1 expected pre-tag unknown for local `v0.1.0a5` tag |
| Release consistency, online | FAIL / OWNER-GATED | `fail_count=8`, `unknown_count=1`; package and GitHub JSON checks and project URL HEAD checks fall back from Python `urllib` to bounded read-only `curl` after local URL/TLS failures; this detects the expected pre-publication `0.1.0a5` gates: PyPI/TestPyPI still expose `0.1.0a3`, project URLs and descriptions still reflect older package metadata, the `v0.1.0a5` tag is absent, the GitHub Release object is absent, and the matching local version tag is unknown before tagging |
| Project URL HEAD reachability | PASS | All six configured project URLs returned 2xx/3xx status through the bounded curl fallback in this local certificate-store constrained environment |
| Public state via independent curl spot-checks | PASS / BLOCKED | PyPI/TestPyPI still expose `0.1.0a3` until `0.1.0a5` is published; `v0.1.0a5` tag and GitHub Release object remain owner-gated |
| Container build | NOT_IN_RELEASE_SCOPE | Preview container gates run in GitHub Actions on hosted Ubuntu |
| GitHub Release object for `v0.1.0a5` | BLOCKED_ON_OWNER | Creating release objects requires owner action after tag-matched artifacts exist |
| Repository security settings | PASS / AUTHENTICATED READ | Authenticated GitHub API read confirmed `main` branch protection with strict required checks (`CodeQL analysis`, `container`, `Dependency review`, `Python 3.12`, `Python 3.13`), required conversation resolution, force-push and deletion protection, Dependabot security updates, secret scanning, push protection, private vulnerability reporting enabled, and security policy enabled. Authenticated alert reads showed 0 Dependabot alerts, 0 secret-scanning alerts, 0 repository security advisories, and 10 CodeQL alerts with no open alerts (`8 fixed`, `2 dismissed`). Latest `main` CodeQL workflow and GitHub CodeQL dynamic analysis runs both completed successfully on 2026-06-22 for commit `0e500d65d90fbda691d13e63ab58091e85083525`. |
| External security review | BLOCKED_ON_EXTERNAL_VALIDATION | No external review is claimed |
| New package publication | BLOCKED_ON_OWNER | Do not publish or overwrite package-index artifacts without explicit owner approval |

## Built Artifacts

Exact hashes for a local proof run are generated into
`build/release-candidate/manifest.json`, `build/release-candidate/REVIEW_INDEX.md`,
and `build/release-candidate/SHA256SUMS.txt`. The generated review index
verifies manifest-listed artifact hashes and reports gate status counts.

| Artifact | Hash source |
| --- | --- |
| `build/release-candidate/dist/actionlineage-0.1.0a5-py3-none-any.whl` | `build/release-candidate/manifest.json` and `build/release-candidate/SHA256SUMS.txt` |
| `build/release-candidate/dist/actionlineage-0.1.0a5.tar.gz` | `build/release-candidate/manifest.json` and `build/release-candidate/SHA256SUMS.txt` |
| `build/release-candidate/actionlineage-sbom.json` | `build/release-candidate/manifest.json` and `build/release-candidate/SHA256SUMS.txt` |
| `build/release-candidate/actionlineage-license-report.json` | `build/release-candidate/manifest.json` and `build/release-candidate/SHA256SUMS.txt` |
| `build/release-candidate/actionlineage-release-provenance.json` | `build/release-candidate/manifest.json` and `build/release-candidate/SHA256SUMS.txt` |
| `build/release-candidate/release-consistency-offline.json` | `build/release-candidate/manifest.json` and `build/release-candidate/SHA256SUMS.txt` |
| `build/release-candidate/release-consistency-online.json` | `build/release-candidate/manifest.json` and `build/release-candidate/SHA256SUMS.txt` |

## Agent Validation Baseline

| Item | Result |
| --- | --- |
| Scenario validation | PASS, 11 scenarios |
| Scenario lint | PASS, 0 issues |
| Capability coverage | PASS, 47/47 declared capabilities covered |
| Eval import boundary | PASS, no core imports from eval-only packages |
| Scripted no-model run | PASS, 11 scorecards, 0 failed |
| Artifact audit | PASS, 236 files scanned, 0 leaks |
| Public baseline report | PASS, `docs/evidence/agent-validation-baseline.md` and `docs/evidence/agent-validation-baseline.json` generated from `build/evals/public-alpha` |
| Failure classes | `none`: 6, `provider_failure`: 1, `inconclusive_budget_exhausted`: 1, `harness_failure`: 1, `agent_failure`: 1, `product_failure`: 1 |

The `product_failure` scenario is an expected control scenario and does not
represent a release blocker.

## Public State Snapshot

Read-only `curl` checks showed:

- PyPI version: `0.1.0a3`.
- PyPI `Requires-Python`: `>=3.12`.
- PyPI project URLs and corrected long description: absent until the
  owner-approved `0.1.0a5` package release.
- TestPyPI version: `0.1.0a3`.
- TestPyPI `Requires-Python`: `>=3.12`.
- TestPyPI project URLs and corrected long description: absent until the
  owner-approved `0.1.0a5` package release.
- GitHub tags: `refs/tags/v0.1.0a3` and `refs/tags/v0.1.0a4`;
  `v0.1.0a5` remains owner-gated.
- `v0.1.0a4` release workflows: verify jobs passed, preview GHCR image pushed,
  release artifact manifest failed before artifact upload or package
  publication.
- GitHub releases listed: `v0.1.0a2`, `v0.1.0a1`.
- GitHub Release object for `v0.1.0a5`: not created before owner release.

Authenticated read-only GitHub API checks showed:

- Repository visibility: public.
- Default branch: `main`.
- `main` branch protection: enabled.
- Strict required checks: `CodeQL analysis`, `container`,
  `Dependency review`, `Python 3.12`, and `Python 3.13`.
- Required conversation resolution: enabled.
- Force pushes and branch deletion: disabled.
- Dependabot security updates: enabled.
- Secret scanning and push protection: enabled.
- Private vulnerability reporting: enabled.
- Security policy: enabled.
- Dependabot alerts: 0.
- Secret-scanning alerts: 0.
- Repository security advisories: 0.
- CodeQL alerts: 10 total, 0 open, 8 fixed, 2 dismissed.
- Latest `main` `codeql` workflow run: success, run `27974809091`,
  commit `0e500d65d90fbda691d13e63ab58091e85083525`.
- Latest `main` GitHub CodeQL dynamic analysis run: success, run
  `27974805527`, commit `0e500d65d90fbda691d13e63ab58091e85083525`.

## Exact Clean-Install Commands

Wheel:

```bash
uvx --from build/release-candidate/dist/actionlineage-0.1.0a5-py3-none-any.whl actionlineage version
uvx --from build/release-candidate/dist/actionlineage-0.1.0a5-py3-none-any.whl actionlineage demo run --output-dir build/release-candidate/wheel-smoke/demo
uvx --from build/release-candidate/dist/actionlineage-0.1.0a5-py3-none-any.whl actionlineage journal verify build/release-candidate/wheel-smoke/demo/evidence.jsonl
uvx --from build/release-candidate/dist/actionlineage-0.1.0a5-py3-none-any.whl actionlineage contract validate contracts/examples/outbound-http.json build/release-candidate/wheel-smoke/demo/evidence.jsonl
uvx --from build/release-candidate/dist/actionlineage-0.1.0a5-py3-none-any.whl actionlineage projection export-case build/release-candidate/wheel-smoke/demo/projection.sqlite build/release-candidate/wheel-smoke/case --trace-id trace_demo_evidence_plane
uvx --from build/release-candidate/dist/actionlineage-0.1.0a5-py3-none-any.whl actionlineage projection export-console build/release-candidate/wheel-smoke/demo/projection.sqlite build/release-candidate/wheel-smoke/console.html --trace-id trace_demo_evidence_plane
```

Source distribution:

```bash
uvx --from build/release-candidate/dist/actionlineage-0.1.0a5.tar.gz actionlineage version
uvx --from build/release-candidate/dist/actionlineage-0.1.0a5.tar.gz actionlineage demo run --output-dir build/release-candidate/sdist-smoke/demo
uvx --from build/release-candidate/dist/actionlineage-0.1.0a5.tar.gz actionlineage journal verify build/release-candidate/sdist-smoke/demo/evidence.jsonl
uvx --from build/release-candidate/dist/actionlineage-0.1.0a5.tar.gz actionlineage contract validate contracts/examples/outbound-http.json build/release-candidate/sdist-smoke/demo/evidence.jsonl
uvx --from build/release-candidate/dist/actionlineage-0.1.0a5.tar.gz actionlineage projection export-case build/release-candidate/sdist-smoke/demo/projection.sqlite build/release-candidate/sdist-smoke/case --trace-id trace_demo_evidence_plane
uvx --from build/release-candidate/dist/actionlineage-0.1.0a5.tar.gz actionlineage projection export-console build/release-candidate/sdist-smoke/demo/projection.sqlite build/release-candidate/sdist-smoke/console.html --trace-id trace_demo_evidence_plane
```

## Remaining Risks

- The `v0.1.0a5` tag, GitHub Release object, TestPyPI upload, and PyPI upload
  remain owner-gated release-integrity blockers.
- The recommended repair path is the new `0.1.0a5` alpha release built from a
  reviewed hardening commit, with tag-matched workflow artifacts and package
  metadata, rather than editing `v0.1.0a3` with post-tag artifacts.
- Existing public PyPI/TestPyPI metadata lacks project URLs and may retain stale
  long-description wording until a later owner-approved package upload.
- Python `urllib` URL/TLS failures are mitigated for package and GitHub JSON
  metadata and project URL HEAD checks by bounded read-only `curl` fallbacks.
- External repository security settings, latest `main` CodeQL runs, and alert
  counts were confirmed through authenticated read-only GitHub API responses;
  third-party review still requires external validation before public claims.
- Container publication remains preview and externally gated.

## Related Owner Docs

- Draft release notes: `docs/DRAFT_RELEASE_NOTES_0.1.0a5.md`.
- Owner publication checklist: `docs/OWNER_PUBLICATION_CHECKLIST.md`.
