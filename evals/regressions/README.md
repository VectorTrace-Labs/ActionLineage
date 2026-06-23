# Agent Validation Regression Corpus

This directory is for reviewed, synthetic replay bundles promoted from dynamic
Agent Validation Lab failures.

Rules:

- Keep bundles small and deterministic.
- Do not commit raw secrets, real credentials, live cloud identifiers, or
  unredacted provider output.
- Commit only reviewed bundles that reproduce a meaningful product, agent,
  harness, provider, or budget failure classification.
- Require `manifest.json` to contain `"reviewed": true` before a bundle is
  replayed by CI.
- Require reviewed bundles to include reviewer, review reason, source run,
  review timestamp, and failure-class metadata.
- Require reviewed bundles to include replay, provenance, triage, oracle,
  journal, transcript, tool-call, minimized-transcript, and minimization-report
  artifacts.
- Run artifact audit before reviewed promotion. Promotion must fail if canaries
  or credential-shaped values are found.
- Treat `evals/regressions/_candidates/` as local review staging only; do not
  rely on candidates in CI.
- Replay the corpus without model calls:

```bash
PYTHONPATH=evals uv run --group eval python -m actionlineage_evals replay-regressions \
  --regression-dir evals/regressions \
  --artifact-root build/evals/regression-replay
```

Use `--allow-empty` only for isolated tests of the replay command itself. The
committed corpus is expected to contain at least one reviewed bundle.
