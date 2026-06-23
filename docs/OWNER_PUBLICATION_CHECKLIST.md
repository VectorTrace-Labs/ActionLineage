# Owner Publication Checklist

Last reviewed: 2026-06-23.

This checklist lists actions that require owner approval or external service
access. Codex must not perform these actions without explicit approval.

## Before Any Public Announcement

- Review `docs/RELEASE_CANDIDATE_AUDIT.md`.
- Review generated artifacts under `build/release-candidate/`.
- Generate or confirm the release-candidate manifest at
  `build/release-candidate/manifest.json` with
  `scripts/write_release_candidate_manifest.py`.
- Generate and review `build/release-candidate/REVIEW_INDEX.md` from the
  manifest so artifact hashes, local gates, and owner/external gates are visible
  in one place.
- Confirm no generated proof artifacts should be committed.
- Confirm the public version posture remains alpha. The currently published
  package is `0.1.0a5`; the recommended alpha-hardening repair is a new
  owner-approved `0.1.0a6` release rather than attempting to mutate published
  `0.1.0a5` artifacts or package descriptions.
- Confirm no production, external-audit, external-adoption, or independent
  validation claim is being made.

## GitHub Release Object

- Do not edit the published `v0.1.0a5` GitHub Release or attach `0.1.0a6`
  remediation artifacts to it.
- Use a new `v0.1.0a6` tag and release for package metadata,
  long-description wording, container digest/signing, provenance, and
  alpha-hardening fixes from the current remediation commit.
- Prefer release-workflow-built artifacts and GitHub artifact attestations when
  available.
- If local artifacts are attached, verify `SHA256SUMS.txt` and document that
  local provenance is supplemental, unsigned release proof.
- If `REVIEW_INDEX.md` is attached, label it as local reviewer navigation and
  hash-verification evidence, not as an attestation or external validation.
- Confirm the version tag commit matches the audited implementation commit in
  `build/release-candidate/REVIEW_INDEX.md`. If it does not match, do not
  attach those artifacts to that tag's GitHub Release; rebuild from the tag or
  choose a new owner-approved version and tag.
- Link `docs/DRAFT_RELEASE_NOTES_0.1.0a6.md` only after removing any text that
  is not intended for public release notes.

Recommended owner-reviewed `0.1.0a6` repair sequence:

1. Make a dedicated release-prep commit that bumps `pyproject.toml`,
   `src/actionlineage/__init__.py`, changelog, README/package-manager install
   commands, release tests, and draft notes to `0.1.0a6`.
2. Run the full local release gate suite and regenerate
   `build/release-candidate/`.
3. Confirm `build/release-candidate/REVIEW_INDEX.md` shows
   `Version tag matches audited commit` as `true` after the tag exists. If it
   is `false` or `unknown`, stop and rebuild from the tag or cut a new
   owner-approved version.
4. Create and push `v0.1.0a6` only after the local gates pass.
5. Dispatch `.github/workflows/release.yml` against `v0.1.0a6` with
   `publish_target=none`; review uploaded artifacts, checksums, manifest,
   review index, and GitHub artifact attestations.
6. Dispatch the same workflow against `v0.1.0a6` with
   `publish_target=testpypi`, then `publish_target=pypi`, only after Trusted
   Publisher and environment checks are confirmed.
7. Prepare public notes from `docs/DRAFT_RELEASE_NOTES_0.1.0a6.md` and create a
   draft release from the workflow-built artifacts:

   ```bash
   gh release create v0.1.0a6 \
     --repo VectorTrace-Labs/ActionLineage \
     --verify-tag \
     --draft \
     --title "ActionLineage v0.1.0a6" \
     --notes-file /tmp/actionlineage-v0.1.0a6-release-notes.md
   ```

8. Publish the GitHub Release only after the package-index pages, release
   assets, checksums, review index, and attestation links agree on `0.1.0a6`.
   Review the draft in the GitHub UI before publishing.

## Package Indexes

- Do not republish or attempt to overwrite existing PyPI/TestPyPI files for
  `0.1.0a5`.
- Publish a new package-index release only after selecting a new version and
  confirming Trusted Publisher records and GitHub environments.
- Use `0.1.0a6` as the recommended corrective package release so PyPI/TestPyPI
  can expose corrected long-description wording without mutating immutable
  `0.1.0a5` files.
- Expect the published `0.1.0a5` long description to remain as-is; corrected
  metadata appears only after a future owner-approved upload.

## Repository Settings

Authenticated read-only GitHub API checks on 2026-06-23 confirmed branch
protection on `main`, strict required checks, Dependabot security updates,
secret scanning, push protection, 0 Dependabot alerts, 0 secret-scanning
alerts, 0 repository security advisories, private vulnerability reporting,
repository security policy, latest `main` CodeQL success, and 10 CodeQL alerts
with no open alerts (`8 fixed`, `2 dismissed`). Reconfirm through GitHub UI or
API before public claims if settings or default-branch state change.

- public GHCR package visibility, if a preview image is published.

## External Review

- Select an external reviewer or review venue before claiming independent
  review.
- Provide `docs/EXTERNAL_REVIEW_GUIDE.md`,
  `docs/SECURITY_REVIEW_CHECKLIST.md`, and
  `docs/EVALUATION_REPRODUCTION.md`.
- Ask reviewers to use synthetic data or minimized failure bundles.
- Do not publish reviewer names, findings, adoption notes, or case studies until
  the contributor approves the exact public text.

## Stop Conditions

- A package, tag, release, container, website, DNS, or repository setting would
  change without owner approval.
- A public claim would require external validation that has not happened.
- A version change, schema change, policy semantics change, or production
  support claim is needed.
- A release artifact contains secrets, private data, or generated local state
  that was not intentionally approved for publication.
