# Release Candidate Audit

Last reviewed: 2026-06-22.

This audit prepares the current public-alpha candidate for owner review. It does
not publish, tag, push, upload, create a GitHub Release, or modify repository
settings.

## Candidate

| Item | Result |
| --- | --- |
| Branch | `codex/public-alpha-hardening` |
| Audited implementation commit | `53126d609b445429194e6633f1ef843d00565607` before this audit-doc refresh |
| Candidate version | `0.1.0a3` |
| Recommendation | Do not republish immutable PyPI/TestPyPI files for `0.1.0a3`; create or repair the GitHub Release object only after owner review. |
| Generated local manifest | `build/release-candidate/manifest.json` |

Generated artifacts under `build/release-candidate/` are local release proof and
are not committed source files.

## Gate Summary

| Gate | Status | Evidence |
| --- | --- | --- |
| Dependency synchronization | PASS | `uv sync --locked --all-extras` |
| Ruff lint | PASS | `uv run ruff check .` |
| Ruff format check | PASS | `uv run ruff format --check .` |
| Strict mypy | PASS | `uv run mypy src`, 56 source files |
| Full pytest after all-extras sync | PASS | `288 passed, 1 skipped, 1 warning`; skipped eval-only inspection path is covered by eval-group run |
| Branch coverage with eval group | PASS | `289 passed`, 86.02 percent total coverage |
| Compatibility tests | PASS | Included in full suite; golden journals and public API tests passed |
| Property-based regression tests | PASS | Included in full suite through Hypothesis tests |
| Claim-language scan | PASS | `uv run python scripts/check_claims_language.py .` |
| Secret scan | PASS | `uv run python scripts/secret_scan.py .` |
| Dependency audit | PASS | `uv run pip-audit`, no known vulnerabilities |
| Local Markdown link check | PASS | Repository-relative Markdown links resolved |
| Clean tracked snapshot | PASS | `288 passed, 1 skipped, 1 warning` from `git archive HEAD` snapshot with `uv run --all-extras pytest` |
| Wheel and sdist build | PASS | `uv build --out-dir build/release-candidate/dist` |
| Built wheel metadata | PASS | Version `0.1.0a3`, `Requires-Python: >=3.12`, six project URLs |
| Built sdist metadata | PASS | Version `0.1.0a3`, `Requires-Python: >=3.12`, six project URLs, no local cache entries |
| Built wheel smoke | PASS | `actionlineage version`, demo run, journal verify, contract validate, case export, and static console export succeeded from wheel |
| Built sdist smoke | PASS | `actionlineage version`, demo run, journal verify, contract validate, case export, and static console export succeeded from sdist |
| Deterministic demo | PASS | 18 events, last hash `sha256:c51f29aadf75d59dd69813e0348f6fbfe2a4297a31051bbdb362017aac01b981` |
| Journal verification | PASS | 18 records verified |
| Contract validation | PASS | `contracts/examples/outbound-http.json` |
| Case export | PASS | `build/release-candidate/case/` |
| Static console export | PASS | `build/release-candidate/console.html` |
| Demo evidence map freshness | PASS | SVG and JSON generated from `incident.json` and checked fresh |
| SBOM generation | PASS | 22 package entries |
| Release provenance generation | PASS | 2 artifact subjects |
| SHA256 checksums | PASS | `build/release-candidate/SHA256SUMS.txt` |
| Release consistency, offline | PASS | 0 failures, 0 unknowns |
| Release consistency, online via Python urllib | PASS with UNKNOWNs | 0 failures, 10 unknowns due local Python certificate-store failure |
| Public state via curl | PASS / BLOCKED | PyPI/TestPyPI expose `0.1.0a3`; GitHub tag exists; GitHub Release object for `v0.1.0a3` is absent |
| Container build | NOT_IN_RELEASE_SCOPE | Preview container gates run in GitHub Actions on hosted Ubuntu |
| GitHub Release object for `v0.1.0a3` | BLOCKED_ON_OWNER | Creating or repairing release objects requires owner action |
| Repository security settings | BLOCKED_ON_EXTERNAL_VALIDATION | Branch protection, secret scanning, push protection, private vulnerability reporting, Dependabot alert status, and latest CodeQL status require external validation |
| External security review | BLOCKED_ON_EXTERNAL_VALIDATION | No external review is claimed |
| New package publication | BLOCKED_ON_OWNER | Do not publish or overwrite package-index artifacts without explicit owner approval |

## Built Artifacts

| Artifact | SHA256 |
| --- | --- |
| `build/release-candidate/dist/actionlineage-0.1.0a3-py3-none-any.whl` | `943eac5a50fa727979e0ecf232a93922c90de1b0db6c7d65d6e1aeaf9f3939e1` |
| `build/release-candidate/dist/actionlineage-0.1.0a3.tar.gz` | `d9c6234de90fd1b13ca70fee3da3f74da81c688e7cf4b4143811470e3687fba7` |
| `build/release-candidate/actionlineage-sbom.json` | `af3cc4f842480acb30fdf72c3735ba5f7fa2b41a14343b20c71c0a5fe91bb9ce` |
| `build/release-candidate/actionlineage-release-provenance.json` | `063cf5a60c0828f4979664fe42a71d14c0a6f0d6d5b2e9858dcda51014c8e806` |

## Agent Validation Baseline

| Item | Result |
| --- | --- |
| Scenario validation | PASS, 11 scenarios |
| Scenario lint | PASS, 0 issues |
| Capability coverage | PASS, 47/47 declared capabilities covered |
| Eval import boundary | PASS, no core imports from eval-only packages |
| Scripted no-model run | PASS, 11 scorecards, 0 failed |
| Artifact audit | PASS, 236 files scanned, 0 leaks |
| Failure classes | `none`: 6, `provider_failure`: 1, `inconclusive_budget_exhausted`: 1, `harness_failure`: 1, `agent_failure`: 1, `product_failure`: 1 |

The `product_failure` scenario is an expected control scenario and does not
represent a release blocker.

## Public State Snapshot

Read-only `curl` checks showed:

- PyPI version: `0.1.0a3`.
- PyPI `Requires-Python`: `>=3.12`.
- PyPI project URLs: absent until a future owner-approved package release.
- TestPyPI version: `0.1.0a3`.
- TestPyPI `Requires-Python`: `>=3.12`.
- TestPyPI project URLs: absent until a future owner-approved package release.
- GitHub tag: `refs/tags/v0.1.0a3`.
- GitHub releases listed: `v0.1.0a2`, `v0.1.0a1`.
- GitHub Release object for `v0.1.0a3`: absent.

## Exact Clean-Install Commands

Wheel:

```bash
uvx --from build/release-candidate/dist/actionlineage-0.1.0a3-py3-none-any.whl actionlineage version
uvx --from build/release-candidate/dist/actionlineage-0.1.0a3-py3-none-any.whl actionlineage demo run --output-dir build/release-candidate/wheel-smoke/demo
uvx --from build/release-candidate/dist/actionlineage-0.1.0a3-py3-none-any.whl actionlineage journal verify build/release-candidate/wheel-smoke/demo/evidence.jsonl
uvx --from build/release-candidate/dist/actionlineage-0.1.0a3-py3-none-any.whl actionlineage contract validate contracts/examples/outbound-http.json build/release-candidate/wheel-smoke/demo/evidence.jsonl
uvx --from build/release-candidate/dist/actionlineage-0.1.0a3-py3-none-any.whl actionlineage projection export-case build/release-candidate/wheel-smoke/demo/projection.sqlite build/release-candidate/wheel-smoke/case --trace-id trace_demo_evidence_plane
uvx --from build/release-candidate/dist/actionlineage-0.1.0a3-py3-none-any.whl actionlineage projection export-console build/release-candidate/wheel-smoke/demo/projection.sqlite build/release-candidate/wheel-smoke/console.html --trace-id trace_demo_evidence_plane
```

Source distribution:

```bash
uvx --from build/release-candidate/dist/actionlineage-0.1.0a3.tar.gz actionlineage version
uvx --from build/release-candidate/dist/actionlineage-0.1.0a3.tar.gz actionlineage demo run --output-dir build/release-candidate/sdist-smoke/demo
uvx --from build/release-candidate/dist/actionlineage-0.1.0a3.tar.gz actionlineage journal verify build/release-candidate/sdist-smoke/demo/evidence.jsonl
uvx --from build/release-candidate/dist/actionlineage-0.1.0a3.tar.gz actionlineage contract validate contracts/examples/outbound-http.json build/release-candidate/sdist-smoke/demo/evidence.jsonl
uvx --from build/release-candidate/dist/actionlineage-0.1.0a3.tar.gz actionlineage projection export-case build/release-candidate/sdist-smoke/demo/projection.sqlite build/release-candidate/sdist-smoke/case --trace-id trace_demo_evidence_plane
uvx --from build/release-candidate/dist/actionlineage-0.1.0a3.tar.gz actionlineage projection export-console build/release-candidate/sdist-smoke/demo/projection.sqlite build/release-candidate/sdist-smoke/console.html --trace-id trace_demo_evidence_plane
```

## Remaining Risks

- The GitHub Release object for `v0.1.0a3` remains the main release-integrity
  blocker.
- Existing public PyPI/TestPyPI metadata lacks project URLs until a later
  owner-approved package upload.
- Python `urllib` cannot complete HTTPS checks in this local environment, while
  `curl` can. The audit records both paths.
- External repository security settings and third-party review cannot be
  verified from local source alone.
- Container publication remains preview and externally gated.

## Related Owner Docs

- Draft release notes: `docs/DRAFT_RELEASE_NOTES_0.1.0a3.md`.
- Owner publication checklist: `docs/OWNER_PUBLICATION_CHECKLIST.md`.
