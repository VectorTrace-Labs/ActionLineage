# Evaluation Reproduction

Last reviewed: 2026-06-23.

This page collects reproducible public-alpha evaluation commands. Generated
artifacts belong under `build/`, `dist/`, or a temporary directory and are not
committed unless a release process explicitly requests them.

If an installation, demo, browser, path, or offline/online environment issue
blocks these commands, see `docs/TROUBLESHOOTING.md`.

## Published Package Smoke

After the owner-approved `0.1.0a6` publication, run:

```bash
uvx --prerelease allow --from actionlineage==0.1.0a6 actionlineage version
uvx --prerelease allow --from actionlineage==0.1.0a6 actionlineage demo run --output-dir actionlineage-pypi-demo
uvx --prerelease allow --from actionlineage==0.1.0a6 actionlineage journal verify actionlineage-pypi-demo/evidence.jsonl
```

Expected package version after publication: `0.1.0a6`. Until that owner gate
is complete, `0.1.0a5` remains the latest public package and the source checkout
commands below are the deterministic evaluation path for this branch.

## Repository Demo And Visual Proof

```bash
uv sync --locked --all-extras
make demo
make demo-map
uv run python scripts/generate_demo_evidence_map.py \
  --demo-dir build/actionlineage-demo \
  --check
uv run actionlineage journal verify build/actionlineage-demo/evidence.jsonl
uv run actionlineage contract validate \
  contracts/examples/outbound-http.json \
  build/actionlineage-demo/evidence.jsonl
```

Expected artifacts:

- `build/actionlineage-demo/evidence.jsonl`;
- `build/actionlineage-demo/projection.sqlite`;
- `build/actionlineage-demo/incident.json`;
- `build/actionlineage-demo/demo-evidence-map.svg`;
- `build/actionlineage-demo/demo-evidence-map.json`.

## No-Model Agent Validation Baseline

```bash
PYTHONPATH=evals uv run --group eval python -m actionlineage_evals validate-scenarios
PYTHONPATH=evals uv run --group eval python -m actionlineage_evals lint-scenarios
PYTHONPATH=evals uv run --group eval python -m actionlineage_evals coverage --strict
PYTHONPATH=evals uv run --group eval python -m actionlineage_evals check-boundaries
PYTHONPATH=evals uv run --group eval python -m actionlineage_evals run \
  --scenario-path evals/scenarios \
  --artifact-root build/evals/public-alpha \
  --mode scripted \
  --model-adapter scripted \
  --seeds 1
PYTHONPATH=evals uv run --group eval python -m actionlineage_evals audit-artifacts \
  build/evals/public-alpha
PYTHONPATH=evals uv run --group eval python -m actionlineage_evals public-report \
  build/evals/public-alpha \
  --json-output docs/evidence/agent-validation-baseline.json \
  --markdown-output docs/evidence/agent-validation-baseline.md
PYTHONPATH=evals uv run --group eval python -m actionlineage_evals check-public-baseline \
  build/evals/public-alpha
```

Expected current baseline:

- 11 scenarios;
- 47 of 47 declared capabilities covered;
- 11 scripted scorecards;
- 0 failed scorecards;
- 0 audited leaks;
- committed baseline check passes with either exact match or provenance-only
  drift.

See `docs/AGENT_VALIDATION_EVIDENCE.md` for the current scenario index,
failure-class counts, and known gaps. The generated committed baseline is in
`docs/evidence/agent-validation-baseline.md` and
`docs/evidence/agent-validation-baseline.json`.

## Local Release Proof

```bash
uv run ruff check .
uv run ruff format --check .
uv run mypy src
uv run pytest
uv run pytest --cov=actionlineage --cov-branch --cov-report=term
uv run python scripts/check_claims_language.py .
uv run python scripts/check_markdown_links.py .
uv run python scripts/secret_scan.py .
uv build --out-dir build/release-proof/dist
uv run --all-extras python scripts/generate_sbom.py --output build/release-proof/actionlineage-sbom.json
uv run --all-extras python scripts/check_dependency_licenses.py \
  --output build/release-proof/actionlineage-license-report.json
uv run python scripts/generate_release_provenance.py \
  --dist-dir build/release-proof/dist \
  --output build/release-proof/actionlineage-release-provenance.json
uv run python scripts/check_release_consistency.py \
  --dist-dir build/release-proof/dist \
  --output build/release-proof/release-consistency-offline.json
uv run pip-audit
```

These commands prove local release readiness only. Creating GitHub Releases,
publishing packages, pushing containers, changing repository settings, and
claiming external validation remain owner or external-validation gates.

For the full release-candidate audit bundle, the local manifest can be generated
from artifact bytes and then turned into a reviewer-facing proof index after the
artifacts have been generated. Repeat `--gate "name|STATUS|evidence"` for
audited gate rows that should appear in the manifest:

```bash
uv run python scripts/write_release_candidate_manifest.py \
  --artifact-root build/release-proof \
  --dist-dir build/release-proof/dist \
  --gate "ruff_check|PASS|uv run ruff check ." \
  --output build/release-proof/manifest.json
uv run python scripts/write_release_review_index.py \
  --manifest build/release-proof/manifest.json \
  --output build/release-proof/REVIEW_INDEX.md
```

If `release-consistency-offline.json` is present in the manifest, the generated
review index summarizes the report counts and any non-passing checks so
reviewers do not have to inspect the raw JSON first.

## Minimized Failure Bundles

When reporting a failure:

- include the exact command and exit code;
- include generated artifacts only if they use synthetic data;
- redact any credentials or private data before sharing;
- include `actionlineage version` output and Python version;
- describe whether the failure is product, harness, provider, or environment
  related when known.
