# Publishing

ActionLineage uses a GitHub-first alpha release path. The repository builds
release artifacts in GitHub Actions, generates GitHub artifact attestations,
publishes preview GHCR container images for version tags, and publishes
PyPI/TestPyPI packages through Trusted Publishing.

## Release Workflow

The release workflow is `.github/workflows/release.yml`.

It runs on:

- tag pushes matching `v*`
- manual `workflow_dispatch`

Every run performs these stages:

1. Verify the release candidate with lint, format, type checking, tests,
   claim-language guard, secret scan, and dependency audit.
2. Build the wheel and source distribution.
3. Generate SBOM, local release provenance, and checksums.
4. Generate GitHub artifact attestations for the built artifacts.
5. Upload the release artifact bundle.
6. Download the artifact bundle with GitHub CLI and verify checksums plus wheel
   and source distribution presence.
7. Build, smoke-test, and publish a version-tagged GHCR container image.

Manual runs can additionally choose `publish_target`:

- `none`: build and attest only
- `testpypi`: publish distributions to TestPyPI
- `pypi`: publish distributions to PyPI

The artifact-smoke and publishing jobs use job-level `actions: read` to fetch
the already-built artifact bundle with GitHub CLI. Publishing jobs also use
`id-token: write` for Trusted Publishing and no package registry API tokens.
The TestPyPI and PyPI jobs run only when the manual workflow is dispatched
against a tag whose ref starts with `refs/tags/v`.

## GHCR Container Images

The release workflow publishes preview container images to GHCR on version tags
created after this workflow path is present on `main`. It runs after the
release-candidate verification job succeeds and uses the workflow `GITHUB_TOKEN`
with job-level `packages: write`; no Docker Hub account or registry token is
required.

Image tags use both the Git tag and the normalized version:

```text
ghcr.io/vectortrace-labs/actionlineage:vX.Y.Z
ghcr.io/vectortrace-labs/actionlineage:X.Y.Z
```

The workflow smoke-tests the image with:

```bash
docker run --rm ghcr.io/vectortrace-labs/actionlineage:vX.Y.Z version
docker run --rm ghcr.io/vectortrace-labs/actionlineage:vX.Y.Z doctor
```

Do not publish a `latest` tag while ActionLineage remains alpha. Versioned tags
avoid implying production stability and make release evidence easier to audit.

## Trusted Publisher Setup

Package publishing uses Trusted Publisher records in TestPyPI and PyPI. Version
`0.1.0a2` was published from `.github/workflows/release.yml` with no registry
API token.

For TestPyPI:

- owner: `VectorTrace-Labs`
- repository: `ActionLineage`
- workflow: `release.yml`
- environment: `testpypi`
- package/project: `actionlineage`

For PyPI:

- owner: `VectorTrace-Labs`
- repository: `ActionLineage`
- workflow: `release.yml`
- environment: `pypi`
- package/project: `actionlineage`

Do not add PyPI API tokens to the repository. Trusted Publishing uses GitHub
OIDC and short-lived credentials issued by the package index.

The package is currently published while package-index organization approval is
pending. Transfer package ownership to the organization after the PyPI and
TestPyPI organization accounts are approved.

## GitHub Environments

The repository uses two GitHub environments for package publication:

- `testpypi`
- `pypi`

Recommended defaults:

- require a maintainer review for `pypi`
- restrict `pypi` to protected branches and tags
- allow `testpypi` for validation runs
- keep environment URLs set to the corresponding package pages

## Artifact Attestation Verification

After a successful release workflow run, verify downloaded artifacts with GitHub
CLI:

```bash
gh attestation verify actionlineage-0.1.0a2-py3-none-any.whl \
  --repo VectorTrace-Labs/ActionLineage
gh attestation verify actionlineage-0.1.0a2.tar.gz \
  --repo VectorTrace-Labs/ActionLineage
```

Also verify checksums:

```bash
shasum -a 256 -c SHA256SUMS.txt
```

## Current Alpha Publication Evidence

Current public package publication:

- TestPyPI: `https://test.pypi.org/project/actionlineage/`
- PyPI: `https://pypi.org/project/actionlineage/`
- Version: `0.1.0a2`
- TestPyPI workflow run: `27957719209`
- PyPI workflow run: `27958024445`

Fresh `uvx` install, deterministic demo, and journal verification passed from
both indexes. Organization ownership transfer remains an external follow-up.

See `docs/PACKAGE_MANAGERS.md` for GHCR, Homebrew, conda-forge, and deferred
channel planning.
