# Public Alpha Hardening Plan

Last reviewed: 2026-06-23.

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
| `PYTHONPATH=evals uv run --group eval python -m actionlineage_evals validate-scenarios` | PASS, 11 scenarios |
| `PYTHONPATH=evals uv run --group eval python -m actionlineage_evals coverage --strict` | PASS, 47 of 47 declared capabilities covered |
| `PYTHONPATH=evals uv run --group eval python -m actionlineage_evals run --scenario-path evals/scenarios --artifact-root build/baseline/evals --mode scripted --model-adapter scripted --seeds 1` | PASS, 11 scorecards |
| `PYTHONPATH=evals uv run --group eval python -m actionlineage_evals audit-artifacts build/baseline/evals` | PASS, 236 files scanned, 0 leaks |

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
| PALPHA-007 | P2 | Local Python `urllib` could not verify PyPI TLS due to local certificate-store configuration, while browser/curl checks succeeded. | ENVIRONMENT_LIMITATION |
| PALPHA-008 | P2 | Service-mode verification emitted Starlette/FastAPI test-client deprecation warnings unless the dev-only `httpx2` backend was installed. | FIXED_IN_TEST_CLIENT_SLICE |
| PALPHA-009 | P2 | Local release proof documented license review expectations but lacked an executable dependency license report gate. | FIXED_IN_LICENSE_GATE_SLICE |
| PALPHA-010 | P2 | Local release-candidate artifacts had hashes and a manifest, but lacked a generated reviewer index that verifies artifact bytes and collects owner/external gates in one place. | FIXED_IN_REVIEW_INDEX_SLICE |
| PALPHA-011 | P2 | Local release-candidate manifest contents were documented but manifest generation itself was not a committed, repeatable script. | FIXED_IN_MANIFEST_GENERATOR_SLICE |

## Phase Plan

| Phase | Scope | Current status |
| --- | --- | --- |
| 0 | Baseline and public-claim audit | In progress |
| 1 | Release and version consistency | In progress: checker added; GitHub Release object remains owner-gated |
| 2 | Package metadata and discoverability | In progress: local metadata improved; public metadata waits for next release |
| 3 | README landing experience and visual proof | In progress: generated demo evidence map and freshness check added |
| 4 | Clean installation and first-time-user testing | In progress: baseline public smoke completed; built wheel and sdist first-time-user smoke gate added to CI; first-time evaluator troubleshooting guide added for install, demo, path/browser, extras, and offline/online failures |
| 5 | Visible quality and security evidence | In progress: baseline captured; CI now runs repository-local Markdown link checking, dependency license reporting, an 85 percent branch-enabled total coverage floor, and a concise quality/security evidence summary |
| 6 | Agent Validation Lab public evidence | In progress: deterministic no-model baseline report is generated into `docs/evidence/agent-validation-baseline.*` from 11 scorecards; scheduled no-model artifacts run on trusted default-branch code; optional live-model execution is gated on `GH_MODELS_TOKEN` and remains separate |
| 7 | Reliability and adversarial hardening | In progress: SQLite projection handles close under warning-as-error coverage; static console context bounds and CSP added; verified-prefix recovery rejects in-place overwrite and streams output; journal verification rejects newline-less truncated final records; ambiguous HTTP observer matches remain unverified with fixture coverage; service-mode tests use a dev-only `httpx2` test-client backend so release proof remains warning-free without adding runtime TCB |
| 8 | External review and community readiness | In progress: review guides, reproduction docs, structured feedback templates, generated manifest command, and generated release-proof review index command added; real review remains external-validation |
| 9 | Release-candidate audit | In progress: local candidate audit refreshed against implementation commit `4bf6246fcfbfd1ff497842c68f4214d3efc6bb67`; draft notes, owner checklist, generated manifest script, review index, artifact smoke, dependency license report, and external gates are documented; publication remains owner-gated |

## Owner Gates

- Create or update a GitHub Release for `v0.1.0a3`.
- Publish any new package, container, release artifact, tag, or registry object.
- Change public version posture, schema namespace, production/stable claims, or
  external-review claims.
- Confirm external repository settings such as branch protection, secret
  scanning, private vulnerability reporting, and public package visibility.
