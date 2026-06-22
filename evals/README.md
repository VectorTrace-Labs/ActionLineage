# ActionLineage Agent Validation Lab

This directory contains the development-only ActionLineage Agent Validation Lab.
The lab is not part of the alpha-supported runtime and is not packaged as an
ActionLineage production dependency.

Current contents:

- `CAPABILITY_COVERAGE.yaml`: lifecycle and capability coverage map.
- `SCENARIO_SCHEMA.json`: JSON Schema for eval scenario manifests.
- `scenarios/`: the first four executable scenario fixtures.
- `actionlineage_evals/`: dev-only runner, adapters, oracles, scorers, replay,
  minimization, and Inspect task glue.
- `docker/`: disposable local receiver and Toxiproxy Compose environment.

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
- Implementation remains narrow and scenario-driven even though the first four
  scenarios are executable.

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
PYTHONPATH=evals uv run --group eval python -m actionlineage_evals docker-smoke
```

Scheduled GitHub Models runs use the same interface with `--mode live
--model-adapter github_models`. Local Ollama runs use `--model-adapter ollama`.
Both stay bounded by scenario budgets.

## Artifact Policy

Generated eval outputs should go under `build/evals/<run-id>/` or `/tmp`.
Committed fixtures under `evals/replay/` or `evals/regression/` must be small,
synthetic, reviewed, redacted, and reproducible.
