# Release Checklist

Use this checklist for every public release candidate and final release.

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

## Release Artifacts

- Source distribution and wheel.
- SBOM JSON.
- Unsigned local release provenance JSON.
- Changelog entry.
- Migration notes.
- Compatibility fixture status.
- Dependency audit output or documented exception.
- Signed artifacts and hosted provenance attestations when release
  infrastructure is available.

## GitHub Security Controls

- CodeQL workflow is present and code scanning has completed successfully.
- Dependency Review workflow is present for pull requests.
- Dependabot version updates are configured for uv, GitHub Actions, and Docker.
- Dependabot alerts and Dependabot security updates are enabled.
- Secret scanning and push protection are enabled.
- Private vulnerability reporting is enabled.

## Documentation Gates

- README quickstart works from a fresh clone.
- API, CLI, schema, tutorial, migration, FAQ, security, privacy, and operations
  docs are present.
- Public claims avoid unsupported wording.
- Deferred 1.x and enterprise features are not represented as implemented.

## Compatibility Gates

- Supported `v1alpha1` journal fixtures validate and rebuild.
- Legacy `agent.tool.*` compatibility fixtures remain readable.
- Projection rebuild works after deleting disposable projection files.
