# AVL-010 malformed-tool-plan-agent-failure

- verdict: passed
- mode: scripted
- seed: 0
- failure_class: agent_failure
- first_failing_scorer: none

## Errors

- agent_error: `AgentExecutionError` agent requested safe_files.read without required path

## Lifecycle

- event_count: 3
- missing_event_types: []
- missing_verification_statuses: []
- forbidden_statuses_present: []
- observed_verification_statuses: []

## Tool Calls

- request_index=0 name=safe_files.read argument_keys=['purpose'] safe_fields={}

## Replay

```bash
PYTHONPATH=evals uv run --group eval python -m actionlineage_evals replay \
  build/evals/regression-seed/avl-010-scripted-seed-0/replay-bundle
```

## Artifacts

- scorecard: `build/evals/regression-seed/avl-010-scripted-seed-0/scorecard.json`
- transcript: `build/evals/regression-seed/avl-010-scripted-seed-0/transcript.json`
- tool_calls: `build/evals/regression-seed/avl-010-scripted-seed-0/tool-calls.json`
- journal: `build/evals/regression-seed/avl-010-scripted-seed-0/journal.jsonl`
- oracle_observations: `build/evals/regression-seed/avl-010-scripted-seed-0/oracle-observations.jsonl`
- provenance: `build/evals/regression-seed/avl-010-scripted-seed-0/provenance.json`
- replay_equivalence: `build/evals/regression-seed/avl-010-scripted-seed-0/replay-equivalence.json`
- minimization_report: `build/evals/regression-seed/avl-010-scripted-seed-0/minimization-report.json`
- replay_bundle: `build/evals/regression-seed/avl-010-scripted-seed-0/replay-bundle`

Authoritative pass/fail comes from scorers and oracles, not model output.
