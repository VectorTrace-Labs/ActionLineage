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
  package is `0.1.0a3`; the recommended corrective metadata/release repair is a
  new owner-approved `0.1.0a4` release rather than attaching post-tag proof to
  `v0.1.0a3`.
- Confirm no production, external-audit, external-adoption, or independent
  validation claim is being made.

## GitHub Release Object

- Create or repair the GitHub Release object for `v0.1.0a3` only after owner
  artifact review.
- Do not attach artifacts from the current post-tag hardening proof to
  `v0.1.0a3` unless the release proof was rebuilt from that tag and the review
  index shows `Version tag matches audited commit` as `true`.
- Prefer a new `v0.1.0a4` tag and release when the goal is to repair package
  metadata, long-description wording, and release-object drift from the current
  hardening commit.
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
- Link `docs/DRAFT_RELEASE_NOTES_0.1.0a3.md` only after removing any text that
  is not intended for public release notes.

Recommended owner-reviewed repair sequence:

1. Rebuild or confirm `build/release-candidate/` from the exact commit being
   reviewed.
2. Verify local checksums:

   ```bash
   shasum -a 256 -c build/release-candidate/SHA256SUMS.txt
   ```

3. Confirm `build/release-candidate/REVIEW_INDEX.md` shows
   `Version tag matches audited commit` as `true`. If it is `false`, stop and
   rebuild from the tag or cut a new owner-approved version instead of
   publishing mismatched release assets.
4. Prepare a public release-notes file from
   `docs/DRAFT_RELEASE_NOTES_0.1.0a3.md`, removing the owner-review preface and
   any wording not intended for the public GitHub Release body.
5. Create a draft release, not a published release:

   ```bash
   gh release create v0.1.0a3 \
     --repo VectorTrace-Labs/ActionLineage \
     --verify-tag \
     --draft \
     --title "ActionLineage v0.1.0a3" \
     --notes-file /tmp/actionlineage-v0.1.0a3-release-notes.md \
     build/release-candidate/dist/actionlineage-0.1.0a3-py3-none-any.whl \
     build/release-candidate/dist/actionlineage-0.1.0a3.tar.gz \
     build/release-candidate/SHA256SUMS.txt \
     build/release-candidate/manifest.json \
     build/release-candidate/REVIEW_INDEX.md \
     build/release-candidate/actionlineage-sbom.json \
     build/release-candidate/actionlineage-license-report.json \
     build/release-candidate/actionlineage-release-provenance.json
   ```

6. Review the draft in the GitHub UI before publishing. Do not mark the release
   public until the asset list, release body, local-proof wording, and any
   attestation links have been checked.

Recommended owner-reviewed `0.1.0a4` repair sequence:

1. Make a dedicated release-prep commit that bumps `pyproject.toml`,
   `src/actionlineage/__init__.py`, changelog, README/package-manager install
   commands, release tests, and draft notes to `0.1.0a4`.
2. Run the full local release gate suite and regenerate
   `build/release-candidate/`.
3. Create and push `v0.1.0a4` only after the local gates pass.
4. Dispatch `.github/workflows/release.yml` against `v0.1.0a4` with
   `publish_target=none`; review uploaded artifacts, checksums, manifest,
   review index, and GitHub artifact attestations.
5. Dispatch the same workflow against `v0.1.0a4` with
   `publish_target=testpypi`, then `publish_target=pypi`, only after Trusted
   Publisher and environment checks are confirmed.
6. Prepare public notes from `docs/DRAFT_RELEASE_NOTES_0.1.0a4.md` and create a
   draft release from the workflow-built artifacts:

   ```bash
   gh release create v0.1.0a4 \
     --repo VectorTrace-Labs/ActionLineage \
     --verify-tag \
     --draft \
     --title "ActionLineage v0.1.0a4" \
     --notes-file /tmp/actionlineage-v0.1.0a4-release-notes.md
   ```

7. Publish the GitHub Release only after the package-index pages, release
   assets, checksums, review index, and attestation links agree on `0.1.0a4`.

## Package Indexes

- Do not republish or attempt to overwrite existing PyPI/TestPyPI files for
  `0.1.0a3`.
- Publish a new package-index release only after selecting a new version and
  confirming Trusted Publisher records and GitHub environments.
- Use `0.1.0a4` as the recommended corrective package release so PyPI/TestPyPI
  can expose project URLs and corrected long-description wording without
  mutating immutable `0.1.0a3` files.
- Expect PyPI/TestPyPI project URLs to remain absent for `0.1.0a3`; corrected
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
