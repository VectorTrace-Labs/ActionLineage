# Good First Issue Candidates

Last reviewed: 2026-06-23.

This document prepares issue drafts for maintainers. It does not open issues,
assign work, claim community participation, or approve new product scope. A
maintainer should copy, edit, and create these manually only when they are ready
to review the resulting contribution. They are not automatically opened.

## Candidate 1: Extend Ambiguous HTTP Correlation Coverage

Suggested labels: `good first issue`, `tests`, `observers`.

Why it helps:

The public alpha's evidence semantics depend on ambiguous observations staying
unverified rather than becoming false certainty. A small additional fixture
keeps that invariant visible to reviewers.

Suggested scope:

- Add one minimized case to `tests/observers/test_local_observers.py` or
  `tests/fixtures/adversarial/security-regressions.json`.
- Use synthetic HTTP receiver or callback data only.
- Keep `ambiguous_candidate_count` visible in the observed state.

Acceptance criteria:

- The new case has at least two plausible observations for one acknowledged
  action.
- The result remains `UNVERIFIED`.
- The limitation text still states that correlation remains ambiguous.
- No live network, credential, or external service is used.

Suggested verification:

```bash
uv run pytest tests/observers/test_local_observers.py
uv run pytest tests/security/test_release_hardening.py
```

Out of scope:

- Adding live sensors.
- Changing verification thresholds.
- Promoting preview observers to alpha-supported status.

## Candidate 2: Add Reference-Style Fragment Link Coverage

Suggested labels: `good first issue`, `docs`, `quality`.

Why it helps:

The repository-local Markdown checker catches missing files, unsafe local
links, same-document anchors, and `file.md#heading` fragments without network
access. A small reference-style regression would make future parser changes
easier to review.

Suggested scope:

- Add a focused reference-link test in
  `tests/security/test_release_hardening.py`.
- Use a reference definition with a local Markdown fragment and an optional
  title.
- Keep the test network-free and deterministic.

Acceptance criteria:

- Existing link-check tests still pass.
- A valid reference-style heading fragment passes.
- A missing reference-style heading fragment reports `missing_fragment`.
- External `http`, `https`, `mailto`, and `tel` links remain out of scope.

Suggested verification:

```bash
uv run pytest tests/security/test_release_hardening.py
uv run python scripts/check_markdown_links.py .
```

Out of scope:

- Fetching external URLs.
- Requiring GitHub-specific anchor behavior beyond a documented local rule.
- Adding a documentation hosting dependency.

## Candidate 3: Add A Future Event Compatibility Fixture

Suggested labels: `good first issue`, `compatibility`, `tests`.

Why it helps:

ActionLineage promises to preserve unknown event types as readable evidence.
A small golden journal fixture makes that compatibility rule easier to inspect.

Suggested scope:

- Add a small JSONL fixture under `tests/fixtures/journals/`.
- Include one future-style event type such as `vendor.future.observed`.
- Extend `tests/compatibility/test_golden_journals.py` to verify the fixture is
  readable, verifiable, and projectable.

Acceptance criteria:

- The fixture verifies with the local journal verifier.
- The SQLite projection rebuilds from the fixture.
- `assess_event_compatibility()` reports that the unknown event can be read
  without interpreting it as allowed, dispatched, observed, or verified.
- Documentation remains clear that unknown events are preserved, not trusted.

Suggested verification:

```bash
uv run pytest tests/compatibility/test_golden_journals.py
uv run pytest tests/domain/test_events.py
```

Out of scope:

- Adding a new schema namespace.
- Changing `actionlineage.dev/v1alpha1` compatibility policy.
- Treating a vendor event type as a supported core event.

## Candidate 4: Add One Failed-Prerequisite Troubleshooting Example

Suggested labels: `good first issue`, `docs`, `onboarding`.

Why it helps:

First-time evaluator failures should be actionable without broadening the
supported surface. One concrete failure example can reduce review friction.

Suggested scope:

- Add one short subsection to `docs/TROUBLESHOOTING.md`.
- Use an existing supported path such as unsupported Python version,
  prerelease resolution, read-only output directory, or installed-package
  contract-file expectations.
- Add or update assertions in `tests/release/test_release_readiness.py`.

Acceptance criteria:

- The example names the failed command shape.
- The fix is platform-safe or clearly scoped.
- The wording does not imply production deployment support.
- The example does not ask users to share secrets or production journals.

Suggested verification:

```bash
uv run pytest tests/release/test_release_readiness.py
uv run python scripts/check_claims_language.py .
```

Out of scope:

- Changing CLI behavior.
- Adding a new package manager support claim.
- Adding screenshots or generated artifacts.

## Candidate 5: Add A Run-ID Static-Console Export Fixture

Suggested labels: `good first issue`, `tests`, `console`.

Why it helps:

The static console is an onboarding and review artifact. Trace-ID exports are
well covered; a run-ID fixture would keep the alternate public selector path
equally easy to review.

Suggested scope:

- Add a focused case to `tests/console/test_static_console.py`.
- Run the deterministic demo and call the `projection export-console` CLI with
  `--run-id`.
- Assert the generated HTML includes the expected demo events and verification
  matrix content.

Acceptance criteria:

- The CLI exits successfully and writes the requested static HTML file.
- The result `event_count` matches the deterministic demo timeline.
- The generated HTML includes verified, unverified, and conflicting statuses.
- Wording still does not treat missing observations as evidence that no action
  occurred.
- The output still includes the restrictive Content Security Policy.

Suggested verification:

```bash
uv run pytest tests/console/test_static_console.py
uv run python scripts/check_claims_language.py .
```

Out of scope:

- Adding JavaScript frameworks.
- Changing canonical evidence semantics.
- Changing projection query behavior.
