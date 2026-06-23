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
- Confirm the public version posture remains `0.1.0a3` and
  `Development Status :: 3 - Alpha`.
- Confirm no production, external-audit, external-adoption, or independent
  validation claim is being made.

## GitHub Release Object

- Create or repair the GitHub Release object for `v0.1.0a3` only after owner
  artifact review.
- Prefer release-workflow-built artifacts and GitHub artifact attestations when
  available.
- If local artifacts are attached, verify `SHA256SUMS.txt` and document that
  local provenance is supplemental, unsigned release proof.
- If `REVIEW_INDEX.md` is attached, label it as local reviewer navigation and
  hash-verification evidence, not as an attestation or external validation.
- Link `docs/DRAFT_RELEASE_NOTES_0.1.0a3.md` only after removing any text that
  is not intended for public release notes.

## Package Indexes

- Do not republish or attempt to overwrite existing PyPI/TestPyPI files for
  `0.1.0a3`.
- Publish a new package-index release only after selecting a new version and
  confirming Trusted Publisher records and GitHub environments.
- Expect PyPI/TestPyPI project URLs to remain absent for `0.1.0a3`; corrected
  metadata appears only after a future owner-approved upload.

## Repository Settings

Authenticated read-only GitHub API checks on 2026-06-23 confirmed branch
protection on `main`, strict required checks, Dependabot security updates,
secret scanning, push protection, 0 Dependabot alerts, 0 secret-scanning
alerts, 0 repository security advisories, and 10 CodeQL alerts with no open
alerts (`8 fixed`, `2 dismissed`). Reconfirm through GitHub UI or API before
public claims:

- latest CodeQL status;
- private vulnerability reporting;
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
