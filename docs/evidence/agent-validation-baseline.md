# Agent Validation Baseline Evidence

This deterministic report is generated from the development-only no-model Agent Validation Lab artifacts. It is local proof, not external validation and not a live-model reliability claim.

## Summary

| Field | Value |
| --- | --- |
| Schema | `actionlineage.dev/agent-validation-public-report-v0` |
| Source commit under evaluation | `a95e034f903ec959bd02722e1ffe804b1a222196` |
| Artifact root | `build/evals/public-alpha` |
| Baseline input digest | `sha256:af62d9ea7671d99b7a5be4cffae00e978c47d2064d0a287a1e071181925e88f0` (76 files) |
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

| Scenario | Passed | Failure class | Failure fingerprint | Seed | Event count | Verification statuses | Artifacts |
| --- | --- | --- | --- | ---: | ---: | --- | --- |
| `AVL-001` | True | `none` | `none` | 0 | 11 | `["observed", "verified"]` | `build/evals/public-alpha/avl-001-scripted-seed-0/scorecard.json` |
| `AVL-002` | True | `none` | `none` | 0 | 10 | `["timed_out"]` | `build/evals/public-alpha/avl-002-scripted-seed-0/scorecard.json` |
| `AVL-003` | True | `none` | `none` | 0 | 6 | `["unverified"]` | `build/evals/public-alpha/avl-003-scripted-seed-0/scorecard.json` |
| `AVL-004` | True | `none` | `none` | 0 | 11 | `["conflicting", "observed"]` | `build/evals/public-alpha/avl-004-scripted-seed-0/scorecard.json` |
| `AVL-005` | True | `none` | `none` | 0 | 17 | `["observed", "unverified", "verified"]` | `build/evals/public-alpha/avl-005-scripted-seed-0/scorecard.json` |
| `AVL-006` | True | `none` | `none` | 0 | 13 | `["unverified"]` | `build/evals/public-alpha/avl-006-scripted-seed-0/scorecard.json` |
| `AVL-007` | True | `provider_failure` | `sha256:2baf53740b8ab6aa80364c7def88860682153464c33609556dec19af7b600dde` | 0 | 3 | `[]` | `build/evals/public-alpha/avl-007-scripted-seed-0/scorecard.json` |
| `AVL-008` | True | `inconclusive_budget_exhausted` | `sha256:e71246fa43067d8093578e354182e2b202b5c28e04d75aee69c11fa26a73a40e` | 0 | 3 | `[]` | `build/evals/public-alpha/avl-008-scripted-seed-0/scorecard.json` |
| `AVL-009` | True | `harness_failure` | `sha256:207ad15e149f593e0428118f0772a840a9049040bca303b5744704eac105f0ee` | 0 | 3 | `[]` | `build/evals/public-alpha/avl-009-scripted-seed-0/scorecard.json` |
| `AVL-010` | True | `agent_failure` | `sha256:49c4a8b8c58037223399e06ccdcab42ad86292b6702b74014a70c91c69ea8869` | 0 | 3 | `[]` | `build/evals/public-alpha/avl-010-scripted-seed-0/scorecard.json` |
| `AVL-011` | True | `product_failure` | `sha256:8891ee6f780dc5edc97d26c4b6d3c65bc7f0176f6ed2546119389a41ace2976a` | 0 | 9 | `["unverified"]` | `build/evals/public-alpha/avl-011-scripted-seed-0/scorecard.json` |

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
