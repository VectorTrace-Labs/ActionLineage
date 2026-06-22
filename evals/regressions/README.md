# Agent Validation Regression Corpus

This directory is for reviewed, synthetic replay bundles promoted from dynamic
Agent Validation Lab failures.

Rules:

- Keep bundles small and deterministic.
- Do not commit raw secrets, real credentials, live cloud identifiers, or
  unredacted provider output.
- Commit only reviewed bundles that reproduce a meaningful product, agent,
  harness, provider, or budget failure classification.
- Replay the corpus without model calls:

```bash
PYTHONPATH=evals uv run --group eval python -m actionlineage_evals replay-regressions \
  --regression-dir evals/regressions \
  --artifact-root build/evals/regression-replay \
  --allow-empty
```

The empty corpus is valid until a failure has been reviewed and promoted.
