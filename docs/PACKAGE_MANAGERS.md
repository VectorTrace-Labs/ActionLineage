# Package Manager Roadmap

ActionLineage uses a staged distribution plan. The goal is to make installation
easy without overstating maturity or adding release channels that cannot be
validated yet.

## Current Channels

| Channel | Status | Notes |
| --- | --- | --- |
| GitHub Releases | Alpha-supported | Release artifacts are built by GitHub Actions, checksummed, and attested. |
| PyPI/TestPyPI | External-validation-required | Trusted Publisher setup is tracked separately and must complete before publication. |
| GHCR container image | Preview | The release workflow builds, smoke-tests, and publishes tagged images with `GITHUB_TOKEN`. |
| Homebrew tap | Planned | A tap and formula should be created after Python package publication or a validated source formula path. |
| conda-forge | Planned | Defer until PyPI publication and at least one public alpha feedback cycle. |

## GHCR

The release workflow publishes a container image for version tags after the
GHCR workflow path lands on `main`:

```text
ghcr.io/vectortrace-labs/actionlineage:vX.Y.Z
ghcr.io/vectortrace-labs/actionlineage:X.Y.Z
```

Future tags use the same pattern. The image is built from
`deploy/docker/Dockerfile`, smoke-tested with `actionlineage version` and
`actionlineage doctor`, and pushed only after the release-candidate verification
job succeeds.

Use the image once the package is visible in GHCR:

```bash
docker pull ghcr.io/vectortrace-labs/actionlineage:vX.Y.Z
docker run --rm ghcr.io/vectortrace-labs/actionlineage:vX.Y.Z version
```

For alpha releases, do not publish or document a `latest` tag. Versioned tags
are easier to audit and avoid implying production stability.

## PyPI And TestPyPI

PyPI remains the primary Python package channel. The release workflow is already
prepared for Trusted Publishing through GitHub OIDC, but package-index owner
setup is required before the jobs can succeed.

Required package-index records:

- TestPyPI project `actionlineage`, trusted publisher environment `testpypi`.
- PyPI project `actionlineage`, trusted publisher environment `pypi`.

Do not add long-lived PyPI API tokens unless Trusted Publishing is unavailable
and the owner explicitly approves the fallback.

## Homebrew Tap

Homebrew is a high-value CLI distribution path, especially for macOS and Linux
users who prefer `brew install` workflows. The recommended tap name is:

```text
VectorTrace-Labs/homebrew-tap
```

Target user command after the tap exists:

```bash
brew install vectortrace-labs/tap/actionlineage
```

Recommended formula strategy:

1. Wait for PyPI or TestPyPI publication so dependency metadata and source
   archives have a stable upstream package path.
2. Generate a formula with Homebrew's Python formula workflow.
3. Vendor or declare Python resources according to Homebrew's Python formula
   guidance.
4. Test locally with:

   ```bash
   brew install --build-from-source ./Formula/actionlineage.rb
   brew test actionlineage
   ```

5. Add tap CI for formula audit, style, install, and test.

Do not commit an unvalidated formula to this repository as a public install
promise. The tap should contain the formula once it has been tested from the
same release artifact users will install.

## Deferred Channels

| Channel | Reason to defer |
| --- | --- |
| conda-forge | Best after PyPI publication and a stable source distribution exists. |
| Docker Hub | GHCR is enough for alpha and avoids a second registry account. |
| Nixpkgs | Valuable later, but adds review and maintenance surface. |
| Scoop/Chocolatey/Winget | Windows packaging should wait for Windows install validation. |
| apt/rpm repositories | Not worth the operational burden during alpha. |

## Owner Gates

- Confirm public GHCR package visibility after the first successful publish.
- Configure TestPyPI/PyPI Trusted Publisher records before package-index
  publication.
- Create or approve the Homebrew tap repository before documenting the `brew`
  command in the README quickstart.
- Decide whether conda-forge belongs in 1.0 or post-1.0 scope after public
  alpha feedback.
