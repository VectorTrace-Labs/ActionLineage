# Quality Scorecard

Last reviewed: 2026-06-21.

This scorecard maps public claims to implementation, tests, demo evidence, and
maturity. It is the release-truth source for README, roadmap, security policy,
and checklist wording.

## Baseline

| Area | Current evidence |
| --- | --- |
| Branch | `main` at `34b3791`, release pipeline work on `codex/release-signing-pypi-pipeline` |
| Local ignored files | `AGENTS.md`, `Uplift.md` |
| Required checks before uplift | Ruff, format, mypy, pip-audit, build, demo, and clean tracked snapshot passed; local pytest and claim scan failed only because ignored `Uplift.md` was included |
| Current alpha version | `0.1.0a1` |
| Supported Python | Python 3.13+ |
| Default demo | No model API key, cloud account, external service, or internet access |

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
| Five-minute demo contract validates | `contracts/examples/outbound-http.json` | Contract validation tests | Demo journal validates with outbound HTTP contract | Alpha-supported |
| Restricted-exfiltration contract is a stricter design example | Contract examples and docs | Contract tests | Not the default demo contract | Preview |
| Sequence detections support bounded operators, windows, grouping, suppression, deduplication, and evidence refs | `src/actionlineage/detection` | `tests/detection` | Demo aligns with built-in rules AL-DET-003, AL-DET-004, AL-DET-005 | Local-proof |
| Lineage Lab supports replay, mutation, minimization, and scorecards | `src/actionlineage/lab` | `tests/lab` | Deterministic demo replay case | Local-proof |
| JSON Lineage Contracts validate events, fields, links, integrity, latency, and detection coverage | `src/actionlineage/contracts` | `tests/contracts` | Demo outbound HTTP contract | Alpha-supported |
| YAML contract/rule examples are review aids | Optional PyYAML loader and docs | Detection YAML loader tests | YAML examples under `contracts`, `detections`, `scenarios` | Preview |
| OpenTelemetry and SIEM/export integrations are non-canonical mirrors | `src/actionlineage/exporters` | `tests/exporters` | Local mapping tests | Preview |
| Optional service mode exists | `src/actionlineage/service` | `tests/service` | Docker/Compose smoke in CI | Preview |
| Optional Postgres projection schema exists | `src/actionlineage/projection/postgres.py` | `tests/projection/test_postgres_projection.py` | Local statement fixtures | Preview |
| Cloud/Kubernetes observers exist as fixture-backed observers | `src/actionlineage/observers/cloud.py` | `tests/observers/test_cloud_observers.py` | No live cloud required | Preview |
| Public release metadata is alpha | `pyproject.toml`, `src/actionlineage/__init__.py` | `tests/release/test_release_readiness.py` | CLI `version` output | Alpha-supported |
| Release hardening scripts exist | `scripts/` | `tests/security/test_release_hardening.py` | SBOM and provenance generated locally | Local-proof |
| CI runs local release proof gates | `.github/workflows/ci.yml` | `tests/release/test_release_readiness.py` | Wheel, sdist, SBOM, audit, and unsigned provenance are generated in CI | Local-proof |
| Release workflow builds and attests artifacts | `.github/workflows/release.yml`, `docs/PUBLISHING.md` | `tests/release/test_release_readiness.py` | GitHub Actions run required to generate attestations | Local-proof |
| TestPyPI/PyPI Trusted Publishing path exists | `.github/workflows/release.yml`, `docs/PUBLISHING.md` | `tests/release/test_release_readiness.py` | Trusted Publisher records required before publishing | Preview |
| GitHub security controls are enabled | `.github/workflows` plus repository settings | Workflow files and API validation | GitHub UI/API required | External-validation-required |
| PyPI/GHCR packages exist | Release checklist and publishing guide | Not executable locally | Package-index publication required | Planned |

## Known Highest Risks

| Risk | Impact | Current control | Next action |
| --- | --- | --- | --- |
| Preview surfaces look production-ready | Misleading public expectations | Maturity labels in README/docs | Keep scorecard updated with every public claim |
| External security controls cannot be verified locally | False confidence before announcement | `docs/DECISIONS_REQUIRED.md` | Owner validates GitHub settings and release controls |
| Service/deployment examples are not production hardened | Operational misuse | Preview labels and security docs | External deployment review before broader claims |
| Demo and contract examples can drift | Broken onboarding | Demo tests and contract validation | Keep README quickstart tied to passing contract |
| Local hash chains can be overinterpreted | Integrity overclaim | Threat model and journal integrity docs | Continue using precise trust-limit wording |

## Release Gate Summary

Before publishing an alpha tag or announcement:

```bash
uv sync --locked --all-extras
uv run ruff check .
uv run ruff format --check .
uv run mypy src
uv run pytest
uv run python scripts/check_claims_language.py .
uv run python scripts/secret_scan.py .
uv run python scripts/generate_sbom.py --output /tmp/actionlineage-sbom.json
uv run pip-audit
uv build --out-dir /tmp/actionlineage-dist
uv run python scripts/generate_release_provenance.py --dist-dir /tmp/actionlineage-dist --output /tmp/actionlineage-provenance.json
gh workflow run release.yml -f publish_target=none
```

Clean-snapshot validation should also run from `git archive HEAD` with
`uv run --all-extras pytest`.
