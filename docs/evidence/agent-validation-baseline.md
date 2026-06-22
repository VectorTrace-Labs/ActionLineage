# Agent Validation Baseline Evidence

This deterministic report is generated from the development-only no-model Agent Validation Lab artifacts. It is local proof, not external validation and not a live-model reliability claim.

## Summary

| Field | Value |
| --- | --- |
| Schema | `actionlineage.dev/agent-validation-public-report-v0` |
| Source commit under evaluation | `7edc0c401100c6545e8340b9cf674c2a63d966b4` |
| Artifact root | `build/evals/public-alpha` |
| Scenarios | 11 scorecards for 11 registered scenarios |
| Failed scorecards | 0 |
| Seeds | `[0]` |
| Model adapters | `[{"adapter": "scripted", "model_id": null, "no_model": true}]` |
| Capability coverage | 47/47 declared capabilities |
| Tool descriptor hashes | 3 unique tool identities |
| Event types observed | 17 |
| Lifecycle transitions observed | 24 |
| Evidence-link statuses | `{"conflicting": 1, "timed_out": 1, "unverified": 3, "verified": 2}` |
| Contract scores | `{"failed": 1, "passed": 10}` |
| Detection scores | `{"matches": 8, "missing_rules": 0}` |
| Failure classes | `{"agent_failure": 1, "harness_failure": 1, "inconclusive_budget_exhausted": 1, "none": 6, "product_failure": 1, "provider_failure": 1}` |

Expected control scenarios intentionally preserve product, agent, harness, provider, and budget failure classes when those classes are the scenario objective. They do not represent unresolved release blockers when the suite passes.

## Scenario Results

| Scenario | Passed | Failure class | Seed | Event count | Verification statuses | Artifacts |
| --- | --- | --- | ---: | ---: | --- | --- |
| `AVL-001` | True | `none` | 0 | 11 | `["observed", "verified"]` | `build/evals/public-alpha/avl-001-scripted-seed-0/scorecard.json` |
| `AVL-002` | True | `none` | 0 | 10 | `["timed_out"]` | `build/evals/public-alpha/avl-002-scripted-seed-0/scorecard.json` |
| `AVL-003` | True | `none` | 0 | 6 | `["unverified"]` | `build/evals/public-alpha/avl-003-scripted-seed-0/scorecard.json` |
| `AVL-004` | True | `none` | 0 | 11 | `["conflicting", "observed"]` | `build/evals/public-alpha/avl-004-scripted-seed-0/scorecard.json` |
| `AVL-005` | True | `none` | 0 | 17 | `["observed", "unverified", "verified"]` | `build/evals/public-alpha/avl-005-scripted-seed-0/scorecard.json` |
| `AVL-006` | True | `none` | 0 | 13 | `["unverified"]` | `build/evals/public-alpha/avl-006-scripted-seed-0/scorecard.json` |
| `AVL-007` | True | `provider_failure` | 0 | 3 | `[]` | `build/evals/public-alpha/avl-007-scripted-seed-0/scorecard.json` |
| `AVL-008` | True | `inconclusive_budget_exhausted` | 0 | 3 | `[]` | `build/evals/public-alpha/avl-008-scripted-seed-0/scorecard.json` |
| `AVL-009` | True | `harness_failure` | 0 | 3 | `[]` | `build/evals/public-alpha/avl-009-scripted-seed-0/scorecard.json` |
| `AVL-010` | True | `agent_failure` | 0 | 3 | `[]` | `build/evals/public-alpha/avl-010-scripted-seed-0/scorecard.json` |
| `AVL-011` | True | `product_failure` | 0 | 9 | `["unverified"]` | `build/evals/public-alpha/avl-011-scripted-seed-0/scorecard.json` |

## Reproduction Commands

```bash
PYTHONPATH=evals uv run --group eval python -m actionlineage_evals validate-scenarios
PYTHONPATH=evals uv run --group eval python -m actionlineage_evals lint-scenarios
PYTHONPATH=evals uv run --group eval python -m actionlineage_evals coverage --strict
PYTHONPATH=evals uv run --group eval python -m actionlineage_evals check-boundaries
PYTHONPATH=evals uv run --group eval python -m actionlineage_evals run --scenario-path evals/scenarios --artifact-root build/evals/public-alpha --mode scripted --model-adapter scripted --seeds 1
PYTHONPATH=evals uv run --group eval python -m actionlineage_evals audit-artifacts build/evals/public-alpha
PYTHONPATH=evals uv run --group eval python -m actionlineage_evals public-report build/evals/public-alpha --json-output docs/evidence/agent-validation-baseline.json --markdown-output docs/evidence/agent-validation-baseline.md
```

## Limitations

- Development-only deterministic baseline; not a live-model reliability claim.
- Scripted adapter output is not treated as an authoritative product oracle.
- Generated run artifacts are reproducible under the artifact root and are not committed.
