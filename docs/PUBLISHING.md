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
   claim-language guard, secret scan, dependency license check, and dependency
   audit.
2. Build the wheel and source distribution.
3. Generate SBOM, dependency license report, local release provenance, and
   release-candidate manifest and review index.
4. Generate checksums over the final release artifact bundle.
5. Generate GitHub artifact attestations for the built artifacts.
6. Upload the release artifact bundle.
7. Download the artifact bundle with GitHub CLI and verify checksums plus wheel,
   source distribution, manifest, and review-index presence.
8. Build, smoke-test, and publish a version-tagged GHCR container image.
9. After an owner-approved TestPyPI or PyPI publication succeeds, wait boundedly
   for public package-index propagation on Python 3.12 and 3.13, install the
   exact tag version from that index, verify installed metadata, run the public
   quickstart smoke path, and upload the verification report.

Manual runs can additionally choose `publish_target`:

- `none`: build and attest only
- `testpypi`: publish distributions to TestPyPI
- `pypi`: publish distributions to PyPI

The artifact-smoke and publishing jobs use job-level `actions: read` to fetch
the already-built artifact bundle with GitHub CLI. Publishing jobs also use
`id-token: write` for Trusted Publishing and no package registry API tokens.
The TestPyPI and PyPI jobs run only when the manual workflow is dispatched
against a tag whose ref starts with `refs/tags/v`.

The post-publication verification job runs only after the selected publishing
job succeeds. It does not publish or mutate package indexes; it reads package
index JSON, installs the exact published version into clean Python 3.12 and
3.13 environments, checks `importlib.metadata` version information, runs
`scripts/smoke_public_quickstart.py`, and uploads `index-propagation.json`,
`installed-metadata.json`, and `public-smoke.json` as workflow artifacts.

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
`0.1.0a6` is the corrective release-prep version for the next owner-approved
Trusted Publishing run. Version `0.1.0a5` is currently published on both PyPI
and TestPyPI with `Requires-Python: >=3.12`; those published distributions and
their long descriptions cannot be changed in place.

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
gh attestation verify actionlineage-0.1.0a6-py3-none-any.whl \
  --repo VectorTrace-Labs/ActionLineage
gh attestation verify actionlineage-0.1.0a6.tar.gz \
  --repo VectorTrace-Labs/ActionLineage
```

Also verify checksums:

```bash
shasum -a 256 -c SHA256SUMS.txt
```

## Container Signature Verification

For version tags, the release workflow pushes a GHCR image, captures the
published OCI digest, signs that immutable digest with keyless Sigstore/cosign,
and attaches build-provenance and SBOM attestations to the digest. PR builds do
not require signing credentials.

Independent verification after publication:

```bash
IMAGE=ghcr.io/vectortrace-labs/actionlineage@sha256:<published-digest>
IDENTITY='https://github.com/VectorTrace-Labs/ActionLineage/.github/workflows/release.yml@refs/tags/.*'
ISSUER='https://token.actions.githubusercontent.com'

cosign verify \
  --certificate-identity-regexp "$IDENTITY" \
  --certificate-oidc-issuer "$ISSUER" \
  "$IMAGE"

cosign verify-attestation \
  --type slsaprovenance \
  --certificate-identity-regexp "$IDENTITY" \
  --certificate-oidc-issuer "$ISSUER" \
  "$IMAGE"

cosign verify-attestation \
  --type https://actionlineage.dev/simple-sbom-v0 \
  --certificate-identity-regexp "$IDENTITY" \
  --certificate-oidc-issuer "$ISSUER" \
  "$IMAGE"
```

## Current Alpha Publication Evidence

Current public package publication proof:

- TestPyPI: `https://test.pypi.org/project/actionlineage/`
- PyPI: `https://pypi.org/project/actionlineage/`
- Current public version: `0.1.0a5`
- Next prepared corrective version: `0.1.0a6`
- Current GitHub Release: `v0.1.0a5`, published 2026-06-23 with 13 assets

Fresh `uvx` install, deterministic demo, and journal verification were release
proof requirements for the current public alpha. The `0.1.0a6`
post-publication lane must repeat that proof on Python 3.12, 3.13, and 3.14.
Because `0.1.0a6` is a prerelease, `uvx` smoke tests use `--prerelease allow`.
Organization ownership transfer remains an external follow-up.

See `docs/PACKAGE_MANAGERS.md` for GHCR, Homebrew, conda-forge, and deferred
channel planning.
