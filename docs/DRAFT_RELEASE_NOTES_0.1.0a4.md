# Draft Release Notes For `v0.1.0a4`

Last reviewed: 2026-06-23.

These are draft notes for owner review of the recommended corrective alpha
release. They are not a publication request, release tag, or package upload.
Use them only after the repository version, changelog, tag, release workflow
artifacts, and package-index uploads all agree on `0.1.0a4`.

## Summary

ActionLineage `0.1.0a4` is the recommended next public-alpha repair release for
the `0.1.0a3` metadata and GitHub Release drift. It should preserve the existing
alpha product scope while making the release evidence tag-aligned, package
metadata discoverable, and public claims consistent with the source docs.

## Why A New Alpha Is Recommended

- PyPI and TestPyPI artifacts for `0.1.0a3` are immutable and cannot be repaired
  in place.
- Public `0.1.0a3` package metadata is missing project URLs and can retain stale
  long-description wording until a new upload.
- The current hardening proof was generated after the `v0.1.0a3` tag, so those
  local artifacts must not be attached to the `v0.1.0a3` GitHub Release as
  tag-matched release proof.
- A new `v0.1.0a4` tag from the reviewed hardening commit gives reviewers one
  coherent commit, artifact set, package version, release object, and
  attestation trail.

## Intended Release Scope

- No event-schema namespace change.
- No production or stable maturity claim.
- No expansion of service, deployment, MCP, cloud, or container support beyond
  the existing alpha, preview, planned, or external-validation labels.
- Package metadata should include the configured project URLs and corrected
  README wording.
- Release notes should state that external review readiness exists, but no independent external review, adoption, production use, or audit is claimed.

## Required Before Publication

1. Bump source metadata and docs from `0.1.0a3` to `0.1.0a4` in a dedicated
   release-prep commit.
2. Regenerate local release-candidate proof from that exact commit.
3. Confirm `build/release-candidate/REVIEW_INDEX.md` shows
   `Version tag matches audited commit` as `true` after tagging.
4. Run the release workflow with `publish_target=none` for tag-aligned build,
   checksums, artifact attestations, manifest, and review-index proof.
5. Publish to TestPyPI and PyPI only through the configured Trusted Publishing
   environments.
6. Create a draft GitHub Release for `v0.1.0a4` from workflow-built artifacts
   and attestation links, then review the draft before publishing it.
7. Run online release consistency after publication and keep any remaining
   owner or external gates visible.

## Suggested Public Highlights

- Public package metadata now exposes repository, documentation, changelog,
  issue tracker, and security policy links.
- Release artifacts are generated from the same commit as the version tag.
- Local release proof includes Ruff, format check, mypy, pytest, branch
  coverage, claim scan, Markdown link check, secret scan, dependency license
  check, dependency audit, SBOM, provenance, wheel/sdist build, artifact smoke
  tests, generated release-candidate manifest, generated release proof review
  index, and Agent Validation no-model checks.
- The deterministic demo still runs without a model API key, cloud account,
  external service, or internet access after installation.

## Known Limitations

- ActionLineage remains a public alpha.
- Local hash-chain evidence is not tamper-proof against a host attacker who can
  rewrite local roots.
- Service mode, MCP interception, cloud observers, GHCR images, Kubernetes, and
  deployment assets remain preview or external-validation surfaces.
- Package-index organization transfer, external review, public evaluation
  feedback, and production operating history remain external follow-up.
