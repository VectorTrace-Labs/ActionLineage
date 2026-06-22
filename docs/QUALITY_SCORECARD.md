# Quality Scorecard

Last reviewed: 2026-06-22.

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
| Known release blocker | GitHub tag `v0.1.0a3` exists, but no GitHub Release object for `v0.1.0a3` was visible in read-only release listing |

## Claim Matrix

| Public claim | Implementation evidence | Test evidence | Demo or fixture evidence | Maturity |
| --- | --- | --- | --- | --- |
| Vendor-neutral evidence plane | `PROJECT_CHARTER.md`, `ARCHITECTURE.md`, `src/actionlineage/domain` | `tests/domain`, `tests/compatibility` | Demo uses local deterministic adapter | Alpha-supported |
| MCP is optional adapter behavior | `src/actionlineage/adapters/mcp`, import-boundary tests | `tests/adapters/test_mcp_descriptors.py`, `tests/adapters/test_mcp_sdk.py` | No MCP needed for demo | Preview |
| Core does not import MCP/OpenTelemetry/model providers/FastAPI/cloud SDKs | Package boundaries and lazy imports | Adapter import-boundary tests | Clean demo core path | Alpha-supported |
| `actionlineage.dev/v1alpha1` envelope is readable | `schemas/actionlineage-event-v1alpha1.schema.json`, `src/actionlineage/domain/events.py` | `tests/domain/test_events.py`, `tests/compatibility/test_golden_journals.py` | Golden journals | Alpha-supported |
| Unknown event types are preserved | `src/actionlineage/compatibility.py` | `tests/domain/test_events.py`, `tests/projection/test_sqlite_projection.py` | `vendor.future.observed` fixture path in tests | Alpha-supported |
| Redaction happens before persistence/export/error serialization | `src/actionlineage/domain/redaction.py`, serializers, exporters | `tests/domain/test_redaction.py`, `tests/security/test_release_hardening.py`, exporter tests | Canary fixtures | Alpha-supported |
| Append-only local journal is canonical evidence | `src/actionlineage/journal/local.py` | `tests/journal/test_local_journal.py` | Demo `evidence.jsonl` | Alpha-supported |
| Hash-chain verification detects mutation, deletion, insertion, duplication, and reorder when anchors make changes observable | Journal verifier and anchor helpers | `tests/journal/test_local_journal.py`, `tests/journal/test_anchors.py` | Demo verify command | Local-proof |
| Projection is rebuildable and disposable | `src/actionlineage/projection/sqlite.py` | `tests/projection/test_sqlite_projection.py` | Demo `projection.sqlite` rebuilt from journal | Alpha-supported |
| Incident export, case bundle, graph export, grounded summary, static console | Projection and console modules | `tests/projection`, `tests/console` | Demo console/export commands | Alpha-supported |
| Source-neutral ingestion exists | `src/actionlineage/evidence` | `tests/evidence` | README API example | Alpha-supported |
| Evidence links include subject, evidence event, relationship, observer, confidence, status, and limitations | `EvidenceLink` model and schema | `tests/domain/test_evidence.py`, compatibility schema tests | Demo verified and conflicting events | Alpha-supported |
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
| Agent Validation Lab provides development-only agent scenario validation, no-model replay, provenance, and artifact audits | `evals/`, `.github/workflows/agent-validation.yml`, `docs/AGENT_VALIDATION_ARCHITECTURE.md` | `tests/evals/test_agent_validation_lab.py`, agent-validation CI lanes | Scenario fixtures under `evals/scenarios` and generated replay bundles | Local-proof |
| JSON Lineage Contracts validate events, fields, links, integrity, latency, and detection coverage | `src/actionlineage/contracts` | `tests/contracts` | Demo outbound HTTP contract | Alpha-supported |
| YAML contract/rule examples are review aids | Optional PyYAML loader and docs | Detection YAML loader tests | YAML examples under `contracts`, `detections`, `scenarios` | Preview |
| OpenTelemetry and SIEM/export integrations are non-canonical mirrors | `src/actionlineage/exporters` | `tests/exporters` | Local mapping tests | Preview |
| Optional service mode exists | `src/actionlineage/service` | `tests/service` | Docker/Compose smoke in CI | Preview |
| Optional Postgres projection schema exists | `src/actionlineage/projection/postgres.py` | `tests/projection/test_postgres_projection.py` | Local statement fixtures | Preview |
| Cloud/Kubernetes observers exist as fixture-backed observers | `src/actionlineage/observers/cloud.py` | `tests/observers/test_cloud_observers.py` | No live cloud required | Preview |
| Public release metadata is alpha and supports Python 3.12+ | `pyproject.toml`, `src/actionlineage/__init__.py` | `tests/release/test_release_readiness.py`, CI/release workflow matrices | CLI `version` output | Alpha-supported |
| Release hardening scripts exist | `scripts/` | `tests/security/test_release_hardening.py` | SBOM and provenance generated locally | Local-proof |
| CI runs local release proof gates | `.github/workflows/ci.yml` | `tests/release/test_release_readiness.py` | Wheel, sdist, SBOM, audit, and unsigned provenance are generated in CI | Local-proof |
| Release workflow builds, verifies on Python 3.12/3.13, and attests artifacts | `.github/workflows/release.yml`, `docs/PUBLISHING.md` | `tests/release/test_release_readiness.py`, `scripts/check_release_consistency.py` | Local workflow definition and package-index proof exist; GitHub Release object for `v0.1.0a3` remains owner-gated | Local-proof / External-validation-required |
| GHCR container publishing path exists | `.github/workflows/release.yml`, `docs/PACKAGE_MANAGERS.md` | `tests/release/test_release_readiness.py` | Workflow path can build, smoke-test, and push tagged preview images; public GHCR visibility requires external validation | Preview |
| TestPyPI/PyPI Trusted Publishing publishes packages | `.github/workflows/release.yml`, `docs/PUBLISHING.md` | `tests/release/test_release_readiness.py` | TestPyPI run `27973522992`; PyPI run `27973832210`; fresh Python 3.12 `uvx` install, demo, and journal verify passed | Alpha-supported |
| GitHub security controls are enabled | `.github/workflows` plus repository settings | Workflow files and API validation | GitHub UI/API required | External-validation-required |
| Homebrew tap exists | `docs/PACKAGE_MANAGERS.md` | Documentation tests | Tap repository and validated formula required | Planned |
| PyPI package exists | `docs/PUBLISHING.md`, `docs/PACKAGE_MANAGERS.md` | Fresh package install smoke and release-consistency checker | `https://pypi.org/project/actionlineage/` publishes `0.1.0a3` with `Requires-Python: >=3.12`; fresh install/demo smoke passed | Alpha-supported |
| TestPyPI package exists | `docs/PUBLISHING.md`, `docs/PACKAGE_MANAGERS.md` | Fresh package install smoke and release-consistency checker | `https://test.pypi.org/project/actionlineage/` publishes `0.1.0a3` with `Requires-Python: >=3.12`; fresh install/demo smoke passed | Alpha-supported |
| Package-index organization ownership transfer | `docs/PACKAGE_MANAGERS.md`, `docs/DECISIONS_REQUIRED.md` | Not executable locally | PyPI/TestPyPI organization approval and ownership transfer required | External-validation-required |
| GHCR package exists | Release checklist and publishing guide | Release workflow container smoke | Public GHCR package visibility has not been independently confirmed in this baseline | External-validation-required |

## Known Highest Risks

| Risk | Impact | Current control | Next action |
| --- | --- | --- | --- |
| Preview surfaces look production-ready | Misleading public expectations | Maturity labels in README/docs | Keep scorecard updated with every public claim |
| External security controls cannot be verified locally | False confidence before announcement | `docs/DECISIONS_REQUIRED.md` | Owner validates GitHub settings and release controls |
| Service/deployment examples are not production hardened | Operational misuse | Preview labels and security docs | External deployment review before broader claims |
| Demo and contract examples can drift | Broken onboarding | Demo tests and contract validation | Keep README quickstart tied to passing contract |
| Local hash chains can be overinterpreted | Integrity overclaim | Threat model and journal integrity docs | Continue using precise trust-limit wording |
| GitHub Release object can drift from tags/package indexes | Broken release audit trail | Release-consistency checker and owner gate | Create/repair `v0.1.0a3` GitHub Release only with owner approval |
| Projection SQLite handle closure can regress | Reliability signal can be missed in noisy verification output | Projection API closes connection handles and has warning-as-error regression coverage | Keep warning-as-error projection test in release verification |

## Release Gate Summary

Before publishing an alpha tag or announcement:

```bash
uv sync --locked --all-extras
uv run ruff check .
uv run ruff format --check .
uv run mypy src
uv run pytest
uv run actionlineage demo run --output-dir /tmp/actionlineage-demo
uv run python scripts/generate_demo_evidence_map.py --demo-dir /tmp/actionlineage-demo
uv run python scripts/generate_demo_evidence_map.py --demo-dir /tmp/actionlineage-demo --check
uv run python scripts/check_claims_language.py .
uv run python scripts/secret_scan.py .
uv run python scripts/generate_sbom.py --output /tmp/actionlineage-sbom.json
uv run pip-audit
uv build --out-dir /tmp/actionlineage-dist
uv run python scripts/check_release_consistency.py --dist-dir /tmp/actionlineage-dist
uv run python scripts/generate_release_provenance.py --dist-dir /tmp/actionlineage-dist --output /tmp/actionlineage-provenance.json
gh workflow run release.yml -f publish_target=none
```

Clean-snapshot validation should also run from `git archive HEAD` with
`uv run --all-extras pytest`.
