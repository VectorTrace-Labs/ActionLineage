# Alpha Release Checklist

Use this checklist for every public alpha candidate and alpha release.

## Required Local Gates

```bash
uv sync --locked --all-extras
uv run ruff check .
uv run ruff format --check .
uv run mypy src
uv run pytest
uv run python scripts/check_claims_language.py .
uv run python scripts/secret_scan.py .
uv run python scripts/generate_sbom.py --output build/actionlineage-sbom.json
uv run pip-audit
uv build
uv run python scripts/generate_release_provenance.py \
  --dist-dir dist \
  --output build/actionlineage-release-provenance.json
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
- Unsigned local release provenance JSON.
- Changelog entry.
- Migration notes.
- Compatibility fixture status.
- Dependency audit output or documented exception.
- Signed artifacts and hosted provenance attestations when release
  infrastructure is available. Until then, label these as
  external-validation-required.

Generate local alpha artifacts without committing them:

```bash
rm -rf /tmp/actionlineage-dist
uv build --out-dir /tmp/actionlineage-dist
uv run python scripts/generate_sbom.py --output /tmp/actionlineage-sbom.json
uv run python scripts/generate_release_provenance.py \
  --dist-dir /tmp/actionlineage-dist \
  --output /tmp/actionlineage-provenance.json
```

## GitHub Security Controls

- CodeQL workflow is present and code scanning has completed successfully.
- Dependency Review workflow is present for pull requests.
- Docker image build and runtime smoke validation are required in CI before
  merging Docker base-image changes.
- Dependabot version updates are configured for uv, GitHub Actions, and Docker.
- Dependabot alerts and Dependabot security updates are enabled.
- Secret scanning and push protection are enabled.
- Private vulnerability reporting is enabled.

## Documentation Gates

- README quickstart works from a fresh clone.
- API, CLI, schema, tutorial, migration, FAQ, security, privacy, and operations
  docs are present.
- Public claims avoid unsupported wording.
- Preview, planned, and external-validation-required features are not
  represented as alpha-supported.

## Compatibility Gates

- Supported `v1alpha1` journal fixtures validate and rebuild.
- Legacy `agent.tool.*` compatibility fixtures remain readable.
- Projection rebuild works after deleting disposable projection files.
