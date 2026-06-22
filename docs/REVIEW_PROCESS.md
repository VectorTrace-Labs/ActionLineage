# Review Process

ActionLineage is maintained as a public-alpha security project. The review
process is designed for solo-maintainer work today while leaving a clean path to
stricter human review requirements when additional trusted maintainers join.

## Current Merge Gates

Changes to `main` must pass the configured required status checks:

- Python CI
- container build and smoke tests
- Dependency Review
- CodeQL analysis

Force pushes and branch deletion remain disabled for `main`.

Required human approvals are not enabled while the project has a single active
maintainer. Requiring one approval in that state turns normal maintainer merges
into repeated branch-protection bypasses, which is less transparent than a
status-check-gated solo-maintainer process.

## AI-Assisted Review

AI review is advisory. It can be requested on pull requests to look for bugs,
missing tests, risky security assumptions, unclear documentation, and release
claim drift.

GitHub Copilot code review is configured with an active default-branch ruleset
that automatically requests Copilot review for non-draft pull requests. The
repository-level instructions in `.github/copilot-instructions.md` give Copilot
ActionLineage-specific review priorities.

AI review does not:

- count as an approving review;
- replace maintainer judgment;
- authorize a merge by itself;
- override failing required checks;
- create a production-readiness claim.

The maintainer remains accountable for deciding whether feedback is relevant,
making any needed changes, and merging only after required checks pass.

## Recommended Pull Request Flow

1. Open a focused pull request with implementation, tests, and docs together
   when public behavior changes.
2. Let required checks run to completion.
3. Request AI review for non-trivial changes, security-sensitive changes, or
   release-process changes.
4. Resolve actionable findings or document why they are not applicable.
5. Merge only when required checks pass and the maintainer has reviewed the
   diff.

## When To Re-enable Human Approval Requirements

Turn on at least one required human approval when there is another trusted
maintainer or reviewer with write access who can review pull requests regularly.

When that happens, keep AI review advisory and require a human approval for the
merge gate.
