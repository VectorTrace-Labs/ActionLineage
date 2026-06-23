# Alpha Release Checklist

Use this checklist for every public alpha candidate and alpha release.

## Required Local Gates

```bash
uv sync --locked --all-extras
uv run ruff check .
uv run ruff format --check .
uv run mypy src
uv run pytest \
  --cov=actionlineage \
  --cov-branch \
  --cov-report=term \
  --cov-report=xml:build/coverage.xml \
  --cov-fail-under=85
uv run actionlineage demo run --output-dir /tmp/actionlineage-demo
uv run python scripts/generate_demo_evidence_map.py --demo-dir /tmp/actionlineage-demo
uv run python scripts/generate_demo_evidence_map.py --demo-dir /tmp/actionlineage-demo --check
uv run python scripts/check_claims_language.py .
uv run python scripts/check_markdown_links.py .
uv run python scripts/secret_scan.py .
uv run python scripts/generate_sbom.py --output build/actionlineage-sbom.json
uv run python scripts/check_dependency_licenses.py \
  --output build/actionlineage-license-report.json
uv run pip-audit
uv build --out-dir dist
uv run python scripts/smoke_public_quickstart.py \
  --package-spec dist/actionlineage-0.1.0a4-py3-none-any.whl \
  --output-dir build/wheel-quickstart-smoke
uv run python scripts/smoke_public_quickstart.py \
  --package-spec dist/actionlineage-0.1.0a4.tar.gz \
  --output-dir build/sdist-quickstart-smoke
uv run python scripts/generate_release_provenance.py \
  --dist-dir dist \
  --output build/actionlineage-release-provenance.json
uv run python scripts/write_ci_quality_summary.py \
  --python-version "$(uv run python -c 'import platform; print(platform.python_version())')" \
  --coverage-xml build/coverage.xml \
  --coverage-floor 85 \
  --sbom build/actionlineage-sbom.json \
  --license-report build/actionlineage-license-report.json \
  --provenance build/actionlineage-release-provenance.json \
  --dist-dir dist \
  --wheel-smoke-dir build/wheel-quickstart-smoke \
  --sdist-smoke-dir build/sdist-quickstart-smoke \
  --demo-map-svg /tmp/actionlineage-demo/demo-evidence-map.svg \
  --output build/actionlineage-ci-summary.md
```

## Agent Validation Gates

These are development-only, no-model gates. They generate committed summary
evidence from synthetic artifacts without treating model output as an
authoritative oracle.

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
```

## Clean Snapshot Gate

Run tests from tracked repository content so ignored local planning files do not
hide public-snapshot failures:

```bash
clean_dir="$(mktemp -d /tmp/actionlineage-clean-XXXXXX)"
git archive HEAD | tar -x -C "$clean_dir"
cd "$clean_dir"
uv run --all-extras pytest
```

## Demo Gates

```bash
uv run actionlineage demo run --output-dir build/actionlineage-demo
uv run actionlineage journal verify build/actionlineage-demo/evidence.jsonl
uv run actionlineage projection timeline build/actionlineage-demo/projection.sqlite \
  --trace-id trace_demo_evidence_plane
uv run actionlineage projection export-console build/actionlineage-demo/projection.sqlite \
  build/actionlineage-demo/console.html \
  --trace-id trace_demo_evidence_plane
```

## Container Gates

These gates run in GitHub Actions on hosted Ubuntu runners. They do not depend
on a contributor's local Docker daemon.

```bash
docker build -f deploy/docker/Dockerfile -t actionlineage:ci .
docker run --rm actionlineage:ci version
docker run --rm actionlineage:ci doctor
docker run --rm -v "$PWD/build/docker-ci:/artifacts" \
  actionlineage:ci demo run --output-dir /artifacts/demo
docker run --rm -v "$PWD/build/docker-ci:/artifacts" \
  actionlineage:ci journal verify /artifacts/demo/evidence.jsonl
docker run --rm -v "$PWD/build/docker-ci:/artifacts" \
  actionlineage:ci projection timeline /artifacts/demo/projection.sqlite \
  --trace-id trace_demo_evidence_plane
docker run --rm -v "$PWD/build/docker-ci:/artifacts" \
  actionlineage:ci contract validate \
  /app/contracts/examples/outbound-http.json \
  /artifacts/demo/evidence.jsonl
```

## Release Artifacts

- Source distribution and wheel.
- SBOM JSON.
- Dependency license report JSON.
- Local release provenance JSON.
- Offline release-consistency JSON generated against the built distribution
  directory.
- Release-candidate manifest JSON generated from local artifact evidence.
- Release proof review index Markdown generated from the local
  release-candidate manifest, including any manifest-listed
  `release-consistency-*.json` report summaries.
- SHA256 checksum file.
- GitHub artifact attestations generated by `.github/workflows/release.yml`.
- Preview GHCR container image for version tags.
- Changelog entry.
- Migration notes.
- Compatibility fixture status.
- Dependency audit output or documented exception.
- TestPyPI and PyPI publication through Trusted Publishing for package-index
  releases.

Generate local alpha artifacts without committing them:

```bash
rm -rf build/release-candidate
mkdir -p build/release-candidate
uv build --out-dir build/release-candidate/dist
uv run python scripts/generate_sbom.py \
  --output build/release-candidate/actionlineage-sbom.json
uv run python scripts/check_dependency_licenses.py \
  --output build/release-candidate/actionlineage-license-report.json
uv run python scripts/generate_release_provenance.py \
  --dist-dir build/release-candidate/dist \
  --output build/release-candidate/actionlineage-release-provenance.json
uv run python scripts/check_release_consistency.py \
  --dist-dir build/release-candidate/dist \
  --output build/release-candidate/release-consistency-offline.json
```

After the release-candidate artifact directory is populated, generate the local
manifest from the artifact bytes and evidence summaries, explicitly pointing at
the distribution directory, then generate a reviewer index that verifies the
manifest-listed artifacts still match their recorded hashes. Repeat
`--gate "name|STATUS|evidence"` for audited gate rows that should appear in the
manifest:

```bash
uv run python scripts/write_release_candidate_manifest.py \
  --artifact-root build/release-candidate \
  --dist-dir build/release-candidate/dist \
  --gate "ruff_check|PASS|uv run ruff check ." \
  --output build/release-candidate/manifest.json
uv run python scripts/write_release_review_index.py \
  --manifest build/release-candidate/manifest.json \
  --output build/release-candidate/REVIEW_INDEX.md
```

## GitHub Release Workflow

The release workflow verifies, builds, attests, and optionally publishes
packages:

```bash
gh workflow run release.yml -f publish_target=none
gh workflow run release.yml -f publish_target=testpypi
gh workflow run release.yml -f publish_target=pypi
```

Use `publish_target=none` for build and attestation validation. Use
`publish_target=testpypi` or `publish_target=pypi` only after the corresponding
Trusted Publisher and GitHub environment are configured, and dispatch those
runs against a version tag.

Required workflow properties:

- release candidate verification runs before build.
- build and publish are separate jobs.
- build job has `attestations: write`, `artifact-metadata: write`,
  `contents: read`, and `id-token: write` so it can attest artifacts before
  upload.
- artifact smoke job has only job-level `actions: read`; it downloads the
  artifact bundle with GitHub CLI, verifies `SHA256SUMS.txt`, and asserts the
  wheel, source distribution, offline release-consistency report,
  release-candidate manifest, and review index are present.
- build job generates `build/release/release-consistency-offline.json` before
  manifest generation, so the report is hashed and summarized in the review
  index.
- build job generates `build/release/manifest.json` with
  `scripts/write_release_candidate_manifest.py --artifact-root build/release
  --dist-dir dist`, then generates `build/release/REVIEW_INDEX.md` before
  checksums and attestations.
- GHCR publishing job has `packages: write`, builds from
  `deploy/docker/Dockerfile`, smoke-tests the image, and pushes only versioned
  tags.
- publishing jobs have only job-level `actions: read` and `id-token: write`;
  they depend on the artifact smoke job and fetch the already-built artifact
  bundle with GitHub CLI.
- publishing jobs require a manual workflow dispatch against `refs/tags/v*`.
- Post-publication verification runs only after the selected TestPyPI or PyPI
  publishing job succeeds; it waits boundedly for package-index propagation,
  installs the exact tag version in clean Python 3.12 and 3.13 environments,
  verifies installed package metadata, runs
  `scripts/smoke_public_quickstart.py`, and uploads
  `actionlineage-post-publication-*` reports.
- no PyPI API token or username/password secret is required.
- TestPyPI uses `repository-url: https://test.pypi.org/legacy/`.

Verify downloaded release artifacts after the workflow runs:

```bash
gh attestation verify actionlineage-0.1.0a4-py3-none-any.whl \
  --repo VectorTrace-Labs/ActionLineage
gh attestation verify actionlineage-0.1.0a4.tar.gz \
  --repo VectorTrace-Labs/ActionLineage
shasum -a 256 -c SHA256SUMS.txt
```

See `docs/PUBLISHING.md` for the Trusted Publisher setup values.

After package publication, verify the current public package from PyPI:

```bash
uvx --prerelease allow --from actionlineage==0.1.0a4 actionlineage version
uvx --prerelease allow --from actionlineage==0.1.0a4 actionlineage demo run --output-dir /tmp/actionlineage-demo
uvx --prerelease allow --from actionlineage==0.1.0a4 actionlineage journal verify /tmp/actionlineage-demo/evidence.jsonl
```

## Package Manager Channels

Current alpha distribution priorities:

- GitHub Releases remain the canonical public alpha release channel.
- GHCR preview container images remain version-tagged when owner-approved
  publication is in scope.
- PyPI/TestPyPI publish the public alpha through Trusted Publishing.
- Homebrew tap work is planned after package-index publication or a validated
  source formula path.
- conda-forge, Docker Hub, Nixpkgs, Windows package managers, and OS package
  repositories are deferred until there is stronger demand and validation.

See `docs/PACKAGE_MANAGERS.md`.

## GitHub Security Controls

- CodeQL workflow is present; latest public code-scanning status must be
  confirmed before using a public badge or announcement claim.
- Dependency Review workflow is present for pull requests.
- Docker image build and runtime smoke validation are required in CI before
  merging Docker base-image changes.
- Built wheel and source distribution first-time-user smoke validation runs in
  CI with `scripts/smoke_public_quickstart.py`.
- CI enforces an 85 percent branch-enabled total coverage floor and writes a
  concise quality/security evidence summary with
  `scripts/write_ci_quality_summary.py`.
- Dependabot version updates are configured for uv, GitHub Actions, and Docker.
- Authenticated GitHub reads on 2026-06-23 confirmed Dependabot security
  updates, secret scanning, push protection, 0 Dependabot alerts, 0
  secret-scanning alerts, 0 repository security advisories, private
  vulnerability reporting, repository security policy, latest `main` CodeQL
  success, and no open CodeQL alerts.

## Documentation Gates

- README quickstart works from a fresh clone.
- First-time-user troubleshooting covers prerelease installation, unsupported
  Python versions, package-manager behavior, optional extras, common demo
  failures, path/browser issues, offline/online expectations, release proof and
  review-index diagnostics, and safe failure reports.
- API, CLI, schema, tutorial, migration, FAQ, security, privacy, and operations
  docs are present.
- Repository-relative Markdown links and local Markdown heading fragments resolve with
  `uv run python scripts/check_markdown_links.py .`.
- Public claims avoid unsupported wording.
- Preview, planned, and external-validation-required features are not
  represented as alpha-supported.

## Compatibility Gates

- Supported `v1alpha1` journal fixtures validate and rebuild.
- Legacy `agent.tool.*` compatibility fixtures remain readable.
- Projection rebuild works after deleting disposable projection files.
