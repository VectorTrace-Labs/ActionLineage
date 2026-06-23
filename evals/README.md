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
PYTHONPATH=evals uv run --group eval python -m actionlineage_evals lint-scenarios
PYTHONPATH=evals uv run --group eval python -m actionlineage_evals coverage --strict
PYTHONPATH=evals uv run --group eval python -m actionlineage_evals check-boundaries
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
PYTHONPATH=evals uv run --group eval python -m actionlineage_evals replay-artifacts \
  build/evals/local \
  --replay-artifact-root build/evals/local-replay
PYTHONPATH=evals uv run --group eval python -m actionlineage_evals audit-artifacts \
  build/evals/local
PYTHONPATH=evals uv run --group eval python -m actionlineage_evals summarize \
  build/evals/local \
  --format markdown
PYTHONPATH=evals uv run --group eval python -m actionlineage_evals docker-smoke
PYTHONPATH=evals uv run --group eval python -m actionlineage_evals check-public-baseline \
  build/evals/local
```

Scheduled no-model runs execute on the trusted default branch and generate a
public-report artifact from deterministic scripted scorecards. Scheduled GitHub
Models runs use the same interface with `--mode live --model-adapter
github_models`, but the workflow skips all live-model execution unless the
explicit `GH_MODELS_TOKEN` secret is configured. GitHub Actions rejects secret
names beginning with `GITHUB_`, so `GH_MODELS_TOKEN` is the repository secret
name. Pull-request jobs remain no-model and secret-free. Local Ollama runs use
`--model-adapter ollama`. Local OpenAI-compatible chat-completions servers use
`--model-adapter openai_compatible` with `OPENAI_COMPATIBLE_BASE_URL` or
`OPENAI_COMPATIBLE_CHAT_COMPLETIONS_URL`. All live adapters stay bounded by
scenario budgets.

Every scenario run writes:

- `scorecard.json`: machine-readable scorer results.
- `provenance.json`: scenario, schema, coverage, commit, workflow, adapter,
  environment, and artifact hashes.
- `triage.md`: human-readable failure summary and replay command.
- `mutation-sequence.json`: deterministic mutation provenance.
- `replay-bundle/`: transcript and journal material for no-model replay.

Every suite run also writes `suite-summary.json`, a compact trendable report
with scenario status, failure-class counts, stable failure fingerprints, and
scorer pass/fail counts. GitHub Actions job summaries render the same
scorecards as Markdown with replay commands for quick triage.

`check-public-baseline` regenerates the deterministic public baseline report
from a no-model artifact root and compares it with
`docs/evidence/agent-validation-baseline.json`. It ignores expected
provenance-only changes such as commit SHA and artifact root, but fails on
semantic evidence drift or changes to the eval-relevant input digest unless the
committed baseline is refreshed.

The scheduled GitHub Models lane runs the first six scenarios. `AVL-007` is a
deterministic no-model provider-failure control, `AVL-008` is a budget
exhaustion control, `AVL-009` is a harness-failure control, and `AVL-010` is an
agent-failure control. `AVL-011` is a product-failure oracle-mismatch control.
`AVL-012` is a concurrent child-run isolation control that checks run IDs,
evidence links, and projection readbacks for interleaved tool calls. These
deterministic controls run in scripted and replay lanes rather than calling a
live provider.

Replay runs include a `replay_equivalence` scorer. It compares semantic
scorecard essentials from the source run with the replayed run, while ignoring
path-specific details such as rebuilt projection filenames and hash-chain tails
that legitimately differ by run mode.

Docker runs use per-run Compose project names and randomly published host
ports. The environment controller records the published ports in
`environment.json`, and the tool oracles use those discovered URLs for receiver
and Toxiproxy calls. This avoids local fixed-port collisions when multiple
Docker evals run at the same time. Compose services also run with dropped Linux
capabilities, `no-new-privileges`, read-only root filesystems, tmpfs scratch
space, resource caps, and an explicit eval network.

`lint-scenarios` performs semantic checks that JSON Schema cannot express:
contiguous IDs, non-planned maturity for implemented fixtures, authoritative
oracles, required scorers, replay artifacts, coverage-required oracles and
scorers, and explicit `failure-classification` tagging for expected failure
controls. `check-boundaries` parses ActionLineage core imports and fails if core
imports eval-only packages or model-provider libraries.

## Artifact Policy

Generated eval outputs should go under `build/evals/<run-id>/` or `/tmp`.
Committed fixtures under `evals/replay/` or `evals/regressions/` must be small,
synthetic, reviewed, redacted, and reproducible. Reviewed regression bundles
must include `"reviewed": true` in `manifest.json` plus reviewer, review
reason, source run, review time, and failure-class metadata; unreviewed
promoted failures are candidates and are not replayed by CI.

Artifact audits use:

```bash
PYTHONPATH=evals uv run --group eval python -m actionlineage_evals audit-artifacts \
  build/evals/local
```

The audit reports pattern names and paths only; it does not echo matched secret
or canary material.

Reviewed promotion uses:

```bash
PYTHONPATH=evals uv run --group eval python -m actionlineage_evals promote-regression \
  build/evals/local/avl-010-scripted-seed-0/replay-bundle \
  --reviewed \
  --reviewed-by security-platform \
  --reason "synthetic agent-failure minimized regression control" \
  --source-run local-development
```

Reviewed promotion requires replay, provenance, triage, oracle, journal,
transcript, tool-call, minimized-transcript, and minimization-report artifacts
and runs an artifact audit before copying the bundle into the replayed corpus.
Unminimized bundles can still be staged as candidates for review, but CI will
not replay them as reviewed regressions.
