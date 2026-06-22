# ActionLineage Agent Validation Lab

This directory contains the development-only ActionLineage Agent Validation Lab.
The lab is not part of the alpha-supported runtime and is not packaged as an
ActionLineage production dependency.

Current contents:

- `CAPABILITY_COVERAGE.yaml`: lifecycle and capability coverage map.
- `SCENARIO_SCHEMA.json`: JSON Schema for eval scenario manifests.
- `scenarios/`: executable scenario fixtures.
- `actionlineage_evals/`: dev-only runner, adapters, oracles, scorers, replay,
  minimization, and Inspect task glue.
- `docker/`: disposable local receiver and Toxiproxy Compose environment.
- `regressions/`: reviewed replay bundles promoted from meaningful dynamic
  failures.

Eval code may import ActionLineage public APIs. ActionLineage core code must not
import from this directory.

## Design Principles

- Agents do not determine authoritative pass/fail results.
- Product, agent, harness, provider, and budget failures stay distinguishable.
- Tool acknowledgements are not treated as side-effect evidence.
- Dynamic failures are promotable to deterministic replay fixtures.
- Pull-request workflows do not expose model credentials to untrusted code.
- Eval dependencies stay outside ActionLineage core dependencies.
- Every live run records enough provenance for replay.
- Capability and lifecycle coverage matter more than line coverage.
- Local and remote models use a common adapter interface.
- Implementation remains narrow and scenario-driven even as the executable
  scenario set grows.

## Commands

Use the eval dependency group and keep `evals/` on `PYTHONPATH`:

```bash
PYTHONPATH=evals uv run --group eval python -m actionlineage_evals validate-scenarios
PYTHONPATH=evals uv run --group eval python -m actionlineage_evals coverage
PYTHONPATH=evals uv run --group eval python -m actionlineage_evals run \
  --scenario-path evals/scenarios \
  --artifact-root build/evals/local \
  --mode scripted \
  --model-adapter scripted
PYTHONPATH=evals uv run --group eval python -m actionlineage_evals replay \
  build/evals/local/avl-001-scripted-seed-0/replay-bundle
PYTHONPATH=evals uv run --group eval python -m actionlineage_evals replay-regressions \
  --regression-dir evals/regressions \
  --artifact-root build/evals/regression-replay \
  --allow-empty
PYTHONPATH=evals uv run --group eval python -m actionlineage_evals summarize \
  build/evals/local \
  --format text
PYTHONPATH=evals uv run --group eval python -m actionlineage_evals docker-smoke
```

Scheduled GitHub Models runs use the same interface with `--mode live
--model-adapter github_models`. In GitHub Actions, the adapter first reads a
model-specific `GH_MODELS_TOKEN` secret, then falls back to the workflow
`GITHUB_TOKEN`. GitHub Actions rejects secret names beginning with `GITHUB_`, so
`GH_MODELS_TOKEN` is the repository secret name. The secret is only passed to the
scheduled or manually dispatched default-branch job; pull-request jobs remain
no-model and secret-free. Local Ollama runs use `--model-adapter ollama`. Local
OpenAI-compatible chat-completions servers use `--model-adapter
openai_compatible` with `OPENAI_COMPATIBLE_BASE_URL` or
`OPENAI_COMPATIBLE_CHAT_COMPLETIONS_URL`. All live adapters stay bounded by
scenario budgets.

Every scenario run writes:

- `scorecard.json`: machine-readable scorer results.
- `triage.md`: human-readable failure summary and replay command.
- `mutation-sequence.json`: deterministic mutation provenance.
- `replay-bundle/`: transcript and journal material for no-model replay.

The scheduled GitHub Models lane runs the first six scenarios. `AVL-007` is a
deterministic no-model provider-failure control, so it runs in the scripted and
replay lanes rather than calling a live provider.

## Artifact Policy

Generated eval outputs should go under `build/evals/<run-id>/` or `/tmp`.
Committed fixtures under `evals/replay/` or `evals/regressions/` must be small,
synthetic, reviewed, redacted, and reproducible. Reviewed regression bundles
must include `"reviewed": true` in `manifest.json`; unreviewed promoted
failures are candidates and are not replayed by CI.
