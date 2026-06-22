# Agent Validation Evidence

Last reviewed: 2026-06-22.

This page records the current deterministic, no-model Agent Validation Lab
evidence for public-alpha review. The lab is a development-only evaluation
surface. It is not packaged as a runtime dependency. Model output is not
authoritative product evidence.

Generated eval artifacts belong under `build/evals/` or `/tmp` and are not
committed by default. The committed evidence here is a concise summary of the
commands, counts, controls, and limitations needed for independent reruns.

## Reproduction Commands

```bash
PYTHONPATH=evals uv run --group eval python -m actionlineage_evals validate-scenarios
PYTHONPATH=evals uv run --group eval python -m actionlineage_evals lint-scenarios
PYTHONPATH=evals uv run --group eval python -m actionlineage_evals coverage --strict
PYTHONPATH=evals uv run --group eval python -m actionlineage_evals check-boundaries
PYTHONPATH=evals uv run --group eval python -m actionlineage_evals run \
  --scenario-path evals/scenarios \
  --artifact-root build/evals/public-alpha \
  --mode scripted \
  --model-adapter scripted \
  --seeds 1
PYTHONPATH=evals uv run --group eval python -m actionlineage_evals audit-artifacts \
  build/evals/public-alpha
PYTHONPATH=evals uv run --group eval python -m actionlineage_evals summarize \
  build/evals/public-alpha \
  --format markdown
```

## Current No-Model Baseline

| Evidence | Current result |
| --- | --- |
| Scenario validation | 11 scenarios: `AVL-001` through `AVL-011` |
| Scenario lint | 0 issues |
| Capability coverage | 47/47 declared capabilities covered |
| Eval import boundary | No ActionLineage core imports from eval-only packages |
| Scripted no-model suite | 11 scorecards, 0 failed |
| Artifact audit | 236 files scanned, 0 leaks |
| Replay equivalence in the scripted baseline | 0/0 because replay is a separate command path |

Failure-class counts from the scripted baseline:

| Failure class | Count | Meaning |
| --- | ---: | --- |
| `none` | 6 | Positive or benign scenarios without modeled failure controls |
| `provider_failure` | 1 | Expected provider-failure control (`AVL-007`) |
| `inconclusive_budget_exhausted` | 1 | Expected budget-exhaustion control (`AVL-008`) |
| `harness_failure` | 1 | Expected harness-failure control (`AVL-009`) |
| `agent_failure` | 1 | Expected agent-failure control (`AVL-010`) |
| `product_failure` | 1 | Expected product-failure oracle-mismatch control (`AVL-011`) |

Every listed control is expected to pass as a control scenario. The counts are
not evidence that live model providers are reliable, and they do not promote the
Agent Validation Lab beyond `Local-proof` maturity.

## Scenario Index

| Scenario | Scripted baseline role |
| --- | --- |
| `AVL-001` | Verified filesystem read |
| `AVL-002` | Acknowledged HTTP send with timed-out or unverified side effect |
| `AVL-003` | Policy denied and not dispatched with redaction canary |
| `AVL-004` | Descriptor drift detection |
| `AVL-005` | Conflicting observer evidence |
| `AVL-006` | Replay and mutation robustness |
| `AVL-007` | Provider-failure control |
| `AVL-008` | Budget-exhaustion control |
| `AVL-009` | Harness-failure control |
| `AVL-010` | Agent-failure control |
| `AVL-011` | Product-failure oracle-mismatch control |

## Known Gaps

The strict coverage report still records explicit known gaps:

| Gap | Reason |
| --- | --- |
| `cloud_observer_live` | Live cloud observers remain outside development-only eval scope. |
| `multi_agent_concurrency` | Deferred until the single-agent vertical slice is deterministic. |
| `service_mode_auth_eval` | Optional service mode is preview and not required for the first lab slice. |

These gaps are not alpha-supported capabilities. Keep them labeled as planned,
preview, or external-validation work unless a future owner-approved phase
changes the release scope.
