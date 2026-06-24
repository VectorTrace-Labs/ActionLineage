# Security Hardening Findings Matrix

Last updated: 2026-06-24.

This matrix tracks the production-readiness hardening brief against the current
public-alpha repository state. `Fixed` means repository code and regression tests
cover the stated defect. `Partially fixed` means safe foundations or local-proof
coverage exist, but the repository must not claim the full production capability.
`Requires migration`, `Requires external service`, and `Requires external
validation` identify work that cannot honestly be completed by local code alone.

## Baseline For This Pass

The pass started on `main` at commit `460a99d` with a clean working tree.

| Check | Baseline result |
| --- | --- |
| `uv run ruff check .` | PASS |
| `uv run ruff format --check .` | PASS, 145 files already formatted |
| `uv run mypy src` | PASS, 59 source files |
| `uv run pytest --cov=actionlineage --cov-branch --cov-report=term --cov-report=xml:/tmp/actionlineage-baseline-coverage.xml --cov-fail-under=85` | PASS, 548 tests, 85.59 percent branch coverage |
| `uv run python scripts/check_claims_language.py .` | PASS |
| `uv run python scripts/check_markdown_links.py .` | PASS, 41 links across 117 files |
| `uv run python scripts/secret_scan.py .` | PASS |
| `uv run --all-extras python scripts/check_dependency_licenses.py --output /tmp/actionlineage-baseline-license-report.json` | PASS, 23 packages |
| `uv run --all-extras python scripts/generate_sbom.py --output /tmp/actionlineage-baseline-sbom.json` | PASS, 23 packages |
| `uv run pip-audit` | PASS, no known vulnerabilities |
| `uv run actionlineage version` | PASS, `0.1.0a6` |
| `uv run actionlineage doctor` | PASS |
| `uv build --out-dir /tmp/actionlineage-baseline-dist` | PASS, wheel and sdist built |
| `uv run python scripts/check_release_consistency.py --dist-dir /tmp/actionlineage-baseline-dist --output /tmp/actionlineage-baseline-release-consistency.json` | PASS in offline mode with one expected `UNKNOWN` for absent generated release provenance in a non-release checkout |
| `docker build -f deploy/docker/Dockerfile -t actionlineage:baseline .` | PASS |
| `docker run --rm actionlineage:baseline version` | PASS, `0.1.0a6` |
| `docker run --rm actionlineage:baseline doctor` | PASS |

## Findings

| ID | Finding | Status | Current repository evidence | Remaining dependency |
| --- | --- | --- | --- | --- |
| F1 | Verified event immutability is bypassable through reachable backing storage. | Confirmed and fixed in this pass. | `src/actionlineage/domain/events.py` stores frozen JSON objects and arrays in sealed tuple-backed state; `tests/domain/test_events.py`, `tests/journal/test_local_journal.py`, `tests/detection/test_sequence.py`, and `tests/exporters/test_profiles.py` cover top-level reassignment, nested mutation, backing-store access/replacement, constructor aliasing, cross-event aliasing, Pydantic copy/construct paths, copy/deepcopy/pickle, verified snapshots, evidence-like payloads, metadata, extension fields, detection, and export-after-mutation attempts. | Deliberately hostile Python techniques such as `object.__setattr__` and `ctypes` remain outside the local invariant, as documented by the brief. |
| F2 | Verified projection results contain mutable nested objects. | Confirmed and fixed in this pass. | `src/actionlineage/projection/sqlite.py` now freezes verification-bearing timeline events, event explanations, grounded-summary selectors, graph selectors, graph attributes, and case-export embedded incident timelines with the same recursively immutable JSON containers used by verified events. `tests/projection/test_sqlite_projection.py` covers direct internal mutation attempts, constructor aliasing, detached `as_dict()` output, explanation generation, summary generation, graph construction, and case export. | Future projection/result types must use the same immutable-result boundary before carrying verification metadata. |
| F3 | Public API responses and portable evidence expose host filesystem paths. | Confirmed and fixed in this pass. | F3 public/portable path privacy now splits `VerifiedProjectionSnapshot.as_dict()` portable proof from `diagnostics_as_dict()` local paths, changes SQLite projection identity from `sqlite-file:<path>` to a deterministic content-derived digest, emits relative case-bundle file names and path-free manifests, and covers POSIX, macOS-shaped, Windows-shaped, CLI, and service timeline path-leak fixtures in `tests/projection/test_sqlite_projection.py` and `tests/service/test_service_mode.py`. | Explicit diagnostics still include local paths by design; older path-based projection identities require rebuild before they can produce portable public proofs. |
| F4 | Journal append and duplicate lookup cost scale linearly. | Confirmed and partially fixed. | `scripts/benchmark_journal_ingest.py`, `tests/release/test_benchmark_scripts.py`, ADR-0011, and ADR-0018 document benchmark evidence and keep future append indexes derived/rebuildable. | A segmented or equivalent authenticated incremental journal format, durable rebuildable idempotency index, migration path, and crash/fault-injection suite remain future work before stronger scaling claims. |
| F5 | No independently controlled external trust root exists. | Confirmed as future/external work with local foundations. | Local anchors, Git anchor statements, archive manifests, external-attestation sidecars, ADR-0015, and `actionlineage.dev/local-durability-policy-v1` define local and external-checkpoint boundaries. | Production-oriented signer, verifier, publisher, witness, receipt verification, key rotation/revocation behavior, and an independently controlled service remain required. |
| F6 | Canonicalization is not yet a stable cross-language protocol. | Confirmed and partially fixed. | ADR-0013 and `tests/fixtures/canonicalization/json-canonicalization-v1-vectors.json` define future `json-canonicalization-v1` conformance vectors while runtime journals remain `json-deterministic-v0`. | Runtime adoption requires a versioned migration/read-old/write-new strategy without changing historical hashes. |
| F7 | Storage ordering and causal lineage remain conflated. | Requires versioned migration. | ADR-0014 defines the future multi-parent causal-edge model and current `v1alpha1` compatibility boundary. | Schema, event bytes, projection, graph, detection, export, cycle/missing-parent, and cross-tenant reference handling require a migration ADR and implementation. |
| F8 | Observer independence is only partially established. | Confirmed and partially fixed. | ADR-0012, observer attestation declarations, `verify_observation()`, and observer tests require reviewed declarations before helper-generated independent-observer links. | Persisted versioned attestations, revocation/re-evaluation, live sensor evidence, and production trust-domain review remain required before production independence claims. |
| F9 | Hosted multi-tenant isolation is not demonstrated end to end. | Local boundary confirmed; hosted isolation unsupported. | ADR-0017 and service tests cover local tenant storage scope, strict tenant IDs, export confinement, and global-role plus tenant-binding authorization. | Shared hosted database/object-store isolation, backups/restores, metrics/logs/caches, and production administrative boundaries require a deployed architecture and external validation. |
| F10 | Deployment assurance remains incomplete. | Partially fixed. | `deploy/docker`, Kubernetes/Helm artifacts, `tests/release/test_deployment_artifacts.py`, CI Docker build/smoke, and baseline Docker smoke validate current preview artifacts. | Expand executable manifest validation for every listed runtime hardening control and keep deployment docs preview-scoped until operator validation exists. |
| F11 | Release claims lack a generated commit-bound evidence manifest. | Confirmed and partially fixed. | Release provenance, SBOM, dependency license report, release-candidate manifest, review index, checksums, and release workflow artifact attestations exist. | A schema-versioned evidence manifest mapping each public claim to commit, workflow, artifact digest, maturity, and limitations must be generated in CI and required before stronger release claims. |
| F12 | External validation and incident-style proof remain incomplete. | Requires independent human/external validation; repository preparation partially fixed. | Review guides, checklists, reproduction docs, validation evidence, vulnerability reporting path, and local deterministic demos exist. | Independent audit, design-partner deployment, production adoption, and an externally reviewed incident-style discrepancy case study cannot be fabricated by local code. |

## Current Implementation Order

1. Add longer-running recovery and filesystem fault-injection tests against
   `actionlineage.dev/local-durability-policy-v1`.
2. Use the F4-F12 foundations above to drive versioned migrations, optional
   external-service integrations, and owner/external validation without
   overstating public-alpha support.
