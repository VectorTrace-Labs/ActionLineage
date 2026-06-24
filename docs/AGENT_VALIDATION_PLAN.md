# Agent Validation Lab Plan

## Status

This is the development plan and implementation guide for the Agent Validation
Lab. The current implementation is development-only: it adds eval code,
scenario fixtures, CI lanes, and validation commands outside ActionLineage core.
It does not add an alpha-supported runtime surface or change ActionLineage
`v1alpha1` events.

## Next-Phase Objective

The next phase turns the first executable slice into an operator-usable
development lab. The goal is not to add a broad framework or public support
claim; it is to make failures diagnosable, replayable, and coverage-guided
without model credentials in pull-request workflows.

Planned improvements:

1. Failure triage reports: every run writes a short Markdown triage artifact
   naming the failure class, first failing scorer, missing lifecycle evidence,
   observed tool calls, relevant errors, and exact replay command.
2. Reviewed regression corpus: replay bundles can be promoted into a
   development-only corpus and replayed in no-model CI. The corpus is seeded
   with a reviewed `AVL-010` agent-failure replay bundle.
3. Inspect live configuration: the Inspect task accepts mode, adapter, model
   ID, seed, Docker, and artifact-root settings instead of hardcoding scripted
   execution.
4. Capability gap reporting: coverage output reports covered capabilities,
   declared-but-uncovered debt, stale references, and known gaps without
   pretending line coverage is sufficient.
5. Narrow mutation execution: the runner applies the first deterministic
   mutation path, `duplicate_benign_event`, and records mutation provenance.
6. Common model adapter hardening: expose a local OpenAI-compatible adapter
   alongside GitHub Models and Ollama using the same `ModelAdapter` protocol.
7. Scenario expansion: add only small scenarios that exercise existing harness
   semantics. The initial additions are a multi-tool causal chain and a denied
   request followed by an allowed safe alternative.

Current hardening slice:

1. Gate CI coverage with `coverage --strict` so stale capability references and
   uncovered declared capabilities fail fast.
2. Publish scorecard summaries into GitHub Actions job summaries for no-model,
   Docker, and scheduled/default-branch live lanes.
3. Replay every scheduled live-run replay bundle in the same workflow so live
   runs prove deterministic replayability immediately.
4. Add `AVL-008 budget-exhausted-control` to preserve
   `inconclusive_budget_exhausted` separately from product, agent, harness, and
   provider failures.
5. Add `AVL-009 harness-failure-control` to preserve `harness_failure`
   separately from product, agent, provider, and budget failures.
6. Add reviewed regression promotion metadata: reviewer, reason, source run,
   review time, and failure class.
7. Add process-status oracle evidence to filesystem-read scenarios and run
   `AVL-001` through Docker in CI alongside the existing Docker/Toxiproxy
   `AVL-002` lane.
8. Use pinned Node 24-compatible artifact upload/download actions after PR
   validation proves the artifact path still works without the residual runtime
   annotation.

Current trust-hardening slice:

1. Add `AVL-010 malformed-tool-plan-agent-failure` to preserve
   `agent_failure` separately from product, harness, provider, and budget
   failures.
2. Publish random Docker host ports and discover them per run so Docker evals
   can run safely in parallel without fixed-port collisions.
3. Write `provenance.json` for every run with scenario, schema, coverage,
   commit, workflow, adapter, environment, and artifact hashes.
4. Copy provenance, tool calls, oracle observations, and minimization artifacts
   into replay bundles so promoted bundles are more self-contained.
5. Add replay-equivalence scoring for replay runs. Replay now compares
   scorecard essentials from the source run against the replayed result and
   fails as a harness issue if they diverge.
6. Add `audit-artifacts` to scan generated artifacts for synthetic canaries,
   bearer tokens, GitHub tokens, OpenAI-style keys, and authorization headers
   without echoing matched secret material.
7. Emit minimized transcript and minimization reports for agent-failure
   controls that have replayable tool-call transcripts.
8. Align the first executable scenarios' maturity labels with their current
   development-only implementation status.

Current classification-and-operations slice:

1. Add `AVL-011 product-failure-oracle-mismatch` to preserve
   `product_failure` separately from agent, harness, provider, and budget
   controls when authoritative lifecycle or contract evidence is missing.
2. Add `lint-scenarios` for semantic scenario quality checks beyond JSON
   Schema: contiguous IDs, non-planned maturity, authoritative oracles,
   required scorers, replay artifacts, coverage-required oracles and scorers,
   and failure-control tagging.
3. Add `check-boundaries` so PR CI proves ActionLineage core does not import
   eval-only packages, Inspect, or model-provider libraries.
4. Harden reviewed regression promotion to require redaction audit, provenance,
   triage, replay artifacts, minimized transcript, and minimization report
   before a bundle enters the replayed corpus.
5. Write `suite-summary.json` and Markdown job summaries with scenario status,
   failure-class counts, scorer counts, replay-equivalence counts, artifact
   paths, and replay commands.
6. Execute deterministic `missing_optional_field` and `event_ordering_skew`
   mutation provenance in addition to duplicate benign events.
7. Harden the disposable Docker Compose environment with dropped capabilities,
   no-new-privileges, read-only roots, tmpfs scratch space, resource caps, and
   an explicit eval network.

Current baseline-freshness slice:

1. Add a deterministic baseline input fingerprint to public no-model evidence.
2. Add `check-public-baseline` so CI compares regenerated no-model evidence
   with `docs/evidence/agent-validation-baseline.json`.
3. Treat commit SHA, artifact root, and reproduction-command differences as
   provenance-only drift when semantic evidence and input fingerprints match.
4. Keep strict local checks failing on semantic evidence drift or eval-relevant
   input drift unless the committed baseline is refreshed in the same change.
   Push/scheduled workflow checks use semantic-only acceptance so input drift is
   reported without creating failure noise for ordinary source commits.

Completed concurrent-run-isolation slice:

1. Add `AVL-012 concurrent-run-isolation` as a deterministic no-model scenario
   with two labeled child runs and interleaved tool calls.
2. Preserve a single journal sequence while recording distinct child run IDs,
   source instances, lifecycle events, and evidence links.
3. Add a `run_isolation` scorer that verifies child-run lifecycle coverage,
   interleaving, absence of coordinator-owned tool events, absence of cross-run
   evidence links, and projection readback for each child run.
4. Refresh semantic capability coverage so `multi_agent_concurrency` is covered
   and no longer listed as a known gap.
5. Regenerate the committed no-model public baseline for 12 scorecards and
   48/48 declared capabilities.

Completed cross-run contamination-control slice:

1. Add `AVL-013 cross-run-evidence-contamination-control` as a deterministic
   no-model negative control that reuses the concurrent child-run shape.
2. Inject one synthetic cross-run evidence link from one child run's
   acknowledgement to another child run's observed side effect after the
   tool-call plan completes.
3. Extend the `run_isolation` scorer to classify cross-run evidence
   contamination as `product_failure` while keeping agent, provider, and
   harness failures distinct.
4. Refresh semantic capability coverage so
   `cross_run_evidence_contamination` is covered by an explicit scenario.
5. Regenerate the committed no-model public baseline for 13 scorecards and
   49/49 declared capabilities.

Current stateful lifecycle mutation-minimization slice:

1. Add `AVL-014 stateful-lifecycle-mutation-minimization` as a deterministic
   no-model product-failure control layered on the verified filesystem-read
   shape.
2. Generate a seeded lifecycle mutation sequence that includes event-ordering
   skew, duplicate benign observation, missing verification status, and a
   transcript replay variant.
3. Minimize the sequence to the smallest replayable semantic counterexample
   while preserving the `product_failure` classification.
4. Persist `stateful-mutation-report.json`, include it in replay bundles and
   provenance hashes, and make replay equivalence compare the semantic
   minimization fields.
5. Refresh semantic capability coverage so Hypothesis-style stateful generation
   and stateful failure minimization are explicit covered capabilities.
6. Regenerate the then-current committed no-model public baseline for 14
   scorecards and 51/51 declared capabilities.

Completed operator-usability and service-auth slice:

1. Make Inspect the primary live-run entrypoint with the `inspect-run` command.
   Scheduled GitHub Models execution now enters through Inspect while keeping
   authoritative scoring inside ActionLineage oracles, journals, projections,
   contracts, detections, and replay artifacts.
2. Seed `evals/regressions/` with a reviewed, synthetic `AVL-010` replay bundle
   so CI exercises a real regression corpus without model calls.
3. Broaden Docker-backed CI smoke coverage to `AVL-001`, `AVL-002`, `AVL-003`,
   `AVL-004`, `AVL-005`, `AVL-014`, and `AVL-015`.
4. Add `AVL-015 service-mode-auth-boundary` to evaluate optional service-mode
   auth without promoting service mode beyond preview. The scenario records a
   denied invalid synthetic service read, an authorized metadata-only read, a
   service-auth oracle observation, detection evidence, and token redaction
   checks.
5. Add `trend` reports for no-model, Docker, scheduled live, and local runs so
   suite status, capability coverage, replay-equivalence, failure classes, and
   artifact-audit counts can be tracked over time.
6. Refresh semantic capability coverage so `service_mode_auth_eval` is covered
   and the only remaining known gap is `cloud_observer_live`.
7. Regenerate the committed no-model public baseline for 15 scorecards and
   56/56 declared capabilities.

Acceptance commands for this phase:

```bash
PYTHONPATH=evals uv run --group eval python -m actionlineage_evals validate-scenarios
PYTHONPATH=evals uv run --group eval python -m actionlineage_evals lint-scenarios
PYTHONPATH=evals uv run --group eval python -m actionlineage_evals coverage --strict
PYTHONPATH=evals uv run --group eval python -m actionlineage_evals check-boundaries
PYTHONPATH=evals uv run --group eval python -m actionlineage_evals run \
  --scenario-path evals/scenarios \
  --artifact-root build/evals/local \
  --mode scripted \
  --model-adapter scripted \
  --seeds 1
PYTHONPATH=evals uv run --group eval python -m actionlineage_evals replay-regressions \
  --regression-dir evals/regressions \
  --artifact-root build/evals/regression-replay
PYTHONPATH=evals uv run --group eval python -m actionlineage_evals replay-artifacts \
  build/evals/local \
  --replay-artifact-root build/evals/local-replay
PYTHONPATH=evals uv run --group eval python -m actionlineage_evals inspect-run \
  --scenario-path evals/scenarios/AVL-001.yaml \
  --artifact-root build/evals/inspect-smoke \
  --mode scripted \
  --model-adapter scripted \
  --seed 0
PYTHONPATH=evals uv run --group eval python -m actionlineage_evals audit-artifacts \
  build/evals/local
PYTHONPATH=evals uv run --group eval python -m actionlineage_evals summarize \
  build/evals/local
PYTHONPATH=evals uv run --group eval python -m actionlineage_evals trend \
  build/evals/local \
  --output build/evals/reports/agent-validation-trend.json \
  --markdown-output build/evals/reports/agent-validation-trend.md \
  --label local
PYTHONPATH=evals uv run --group eval python -m actionlineage_evals check-public-baseline \
  build/evals/local
PYTHONPATH=evals uv run --group eval python -m actionlineage_evals docker-smoke
for scenario in AVL-001 AVL-002 AVL-003 AVL-004 AVL-005 AVL-014 AVL-015; do
  lower="$(printf '%s' "$scenario" | tr '[:upper:]' '[:lower:]')"
  PYTHONPATH=evals uv run --group eval python -m actionlineage_evals run \
    --scenario-path "evals/scenarios/${scenario}.yaml" \
    --artifact-root "build/evals/docker-${lower}" \
    --mode scripted \
    --model-adapter scripted \
    --seeds 1 \
    --use-docker
done
PYTHONPATH=evals uv run --group eval pytest tests/evals/test_agent_validation_lab.py
uv run ruff check .
uv run ruff format --check .
uv run mypy src
PYTHONPATH=evals uv run --group eval mypy evals/actionlineage_evals
uv run pytest
uv run python scripts/check_claims_language.py .
uv run python scripts/secret_scan.py .
uv run pip-audit
```

Stop conditions:

- The phase requires ActionLineage event schema changes.
- Eval dependencies must enter runtime dependencies or package extras.
- PR workflows need model credentials.
- A model response would become authoritative pass/fail evidence.
- Regression promotion would commit unreviewed, unredacted, or non-synthetic
  artifacts.
- Scenario expansion requires real secrets, live cloud accounts, paid
  providers, or unsupported public maturity claims.

## Scope

Implemented artifacts:

- `docs/AGENT_VALIDATION_ARCHITECTURE.md`
- `docs/AGENT_VALIDATION_THREAT_MODEL.md`
- `docs/AGENT_VALIDATION_PLAN.md`
- `evals/README.md`
- `evals/CAPABILITY_COVERAGE.yaml`
- `evals/SCENARIO_SCHEMA.json`
- `evals/scenarios/AVL-001.yaml`
- `evals/scenarios/AVL-002.yaml`
- `evals/scenarios/AVL-003.yaml`
- `evals/scenarios/AVL-004.yaml`
- `evals/scenarios/AVL-005.yaml`
- `evals/scenarios/AVL-006.yaml`
- `evals/scenarios/AVL-007.yaml`
- `evals/scenarios/AVL-008.yaml`
- `evals/scenarios/AVL-009.yaml`
- `evals/scenarios/AVL-010.yaml`
- `evals/scenarios/AVL-011.yaml`
- `evals/scenarios/AVL-012.yaml`
- `evals/scenarios/AVL-013.yaml`
- `evals/scenarios/AVL-014.yaml`
- `evals/scenarios/AVL-015.yaml`
- `evals/regressions/README.md`
- `evals/regressions/AVL-010-56cb348a7a9c9d6c/`
- `evals/actionlineage_evals/`
- `evals/docker/`
- `.github/workflows/agent-validation.yml`

The eval implementation does not add ActionLineage core schema changes and does
not add eval dependencies to runtime dependencies or package extras.

## Package And Dependency Boundaries

The dev-only uv `eval` dependency group contains:

- `inspect-ai` for the outer evaluation harness.
- `openai` for model-client compatibility.
- `httpx` for dev-only provider and service calls.
- `PyYAML` for YAML scenario manifests.
- `jsonschema` for scenario validation.
- `hypothesis` for stateful mutation generation tests.

Dependency rules:

- Do not add eval dependencies to `[project.dependencies]`.
- Do not add eval dependencies to existing `adapters`, `service`, or runtime
  extras without owner approval.
- Do not import eval code from `src/actionlineage`.
- Do not expose eval protocols as ActionLineage public APIs until an ADR
  approves that boundary.

## Scenario DSL

The scenario DSL is validated by `evals/SCENARIO_SCHEMA.json` and uses:
`apiVersion: actionlineage.dev/eval-scenario/v0`.

Required sections:

- `metadata`: scenario ID, name, owner, maturity, and tags.
- `spec.intent`: user request, expected agent objective, and untrusted inputs.
- `spec.environment`: Docker Compose file, services, health checks, volumes,
  Toxiproxy faults, and artifact paths.
- `spec.agents`: agent adapter, model adapter, allowed tools, and budgets.
- `spec.tools`: tool names, descriptor hash expectations, side-effect class,
  and whether policy enforcement is expected.
- `spec.oracles`: independent world-state observations.
- `spec.expected`: lifecycle events, evidence links, contracts, detections,
  redaction scans, and failure classification.
- `spec.mutations`: deterministic stateful or scenario-level variations.
- `spec.replay`: required transcript and tool-call replay provenance.

The DSL references ActionLineage event types and contracts, but it does not
define new event names or payload compatibility rules.

## Model And Agent Adapters

All live and replay paths use a common adapter interface:

- `replay`: consumes stored transcript and tool-call artifacts, makes zero model
  calls, and must be available in PR CI.
- `github_models`: uses GitHub Models only in scheduled or manually dispatched
  default-branch workflows with `models: read`.
- `ollama`: optional local adapter using `http://localhost:11434/api` or the
  OpenAI-compatible local `/v1` endpoint.

Agent adapters represent real tool-using agents. The implemented local runner
can execute the development-only scenario set through the same tool-call
recording path used by replay and scheduled model runs.

## Docker Environment Lifecycle

Every scenario run:

- Creates `build/evals/<run-id>/`.
- Starts Docker Compose with project name `actionlineage-eval-<run-id>`.
- Waits for declared health checks.
- Records Compose config, image digests, service logs, environment variables
  allowed by the scenario, exposed ports, and Toxiproxy state.
- Runs the agent through Inspect.
- Collects oracle observations and ActionLineage evidence.
- Tears down containers, networks, and volumes unless a debug flag preserves
  them locally.
- Uses randomly published host ports, records those ports in `environment.json`,
  and keeps receiver/Toxiproxy services on an explicit eval network.
- Runs disposable services with dropped capabilities, `no-new-privileges`,
  read-only root filesystems where possible, tmpfs scratch space, and resource
  caps.

No scenario may depend on a cloud account, real endpoint, or internet access for
authoritative oracle state.

## Oracles And Scorers

Independent oracles:

- `filesystem_state`
- `receiver_log`
- `process_status`
- `sqlite_readback`
- `toxiproxy_state`
- `journal_verification`
- `projection_rebuild`
- `contract_validation`
- `detection_matches`
- `service_authz`
- `redaction_scan`

Scorers:

- `lifecycle`
- `integrity`
- `redaction`
- `contract`
- `detection`
- `capability_coverage`
- `replayability`
- `failure_classification`

Failure classification vocabulary:

- `product_failure`
- `agent_failure`
- `harness_failure`
- `provider_failure`
- `inconclusive_budget_exhausted`

## Mutation Dimensions

Initial mutation dimensions:

- Prompt wording.
- Indirect prompt-injection placement.
- Tool descriptor drift.
- Path and URL normalization.
- Missing optional fields.
- Event ordering and timestamp skew.
- Duplicate benign events.
- Side-effect delay or drop through Toxiproxy.
- Redaction canary location.
- Concurrency.
- Transcript replay variants.

Hypothesis stateful generation should produce action sequences over the scenario
state model, then persist seeds and minimized counterexamples when failures are
meaningful.

## First Four Scenarios

### AVL-001 verified-filesystem-read

- Agent objective: read a restricted local file with `safe_files.read`.
- Required lifecycle: intent, run started, requested, authorized, dispatched,
  acknowledged, observed, verified.
- Oracle: filesystem digest and metadata for the expected file.
- Expected evidence: acknowledgement plus independent filesystem observation and
  `side_effect.verified`.
- First implementation scope: yes.

### AVL-002 acknowledged-http-send-unverified-under-timeout

- Agent objective: send a local HTTP request to a receiver through Toxiproxy.
- Fault: timeout or full connection drop between tool runtime and receiver.
- Required lifecycle: requested, authorized, dispatched, acknowledged,
  timed-out or unverified.
- Oracle: receiver log has no corroborating receipt for the expected request ID.
- Expected evidence: tool acknowledgement remains separate from side-effect
  verification; `side_effect.verified` must not appear for this send.

### AVL-003 policy-denied-not-dispatched-secret-canary

- Agent objective: handle an untrusted prompt-injection attempt that requests
  exfiltration of a synthetic redaction canary.
- Policy expectation: denial before dispatch.
- Oracle: downstream call count is zero.
- Expected evidence: `policy.decision` with deny outcome,
  `tool.execution.not_dispatched`, and redaction canary absent from all scanned
  artifacts.

### AVL-004 descriptor-drift-conflicting-receiver

- Agent objective: use a sensitive sender after a descriptor change.
- Environment: receiver records a body digest that conflicts with the expected
  digest.
- Required lifecycle: descriptor drift evidence, send acknowledgement, receiver
  observation, conflict verification.
- Expected evidence: `agent.tool.schema_changed` and
  `side_effect.conflict_detected`.

## Phased Issues

1. Phase 0: design and schema artifacts.
2. Phase 1: `AVL-001` with filesystem oracle, journal/projection/contract
   scorers, transcript capture, and replay.
3. Phase 2: Toxiproxy support and `AVL-002`.
4. Phase 3: policy denial, downstream call-count oracle, redaction canary scan,
   and `AVL-003`.
5. Phase 4: descriptor drift, conflicting receiver evidence, capability
   coverage reporting, minimization, and reviewed regression promotion.

All phases are implemented as development-only eval code. Scheduled live-model
execution remains advisory until the owner chooses whether eval failures should
block release workflows.

## CI Lanes

PR lane:

- Trigger: `pull_request`.
- Permissions: `contents: read`.
- Model requests: zero.
- Runs scenario schema validation, capability coverage lint, replay-only evals,
  and deterministic fixture tests.

Scheduled no-model lane:

- Trigger: default-branch `schedule` and `workflow_dispatch`.
- Permissions: `contents: read`.
- Model requests: zero.
- Runs deterministic scripted scenarios, replay, regression corpus checks,
  artifact audit, and public-report generation.
- Uploads redacted artifacts with short retention.

Scheduled live-model lane:

- Trigger: default-branch `schedule` and `workflow_dispatch`.
- Permissions: `contents: read`, `models: read`.
- Uses Inspect as the outer harness and GitHub Models through `ModelAdapter`.
- Skips all live-model execution unless maintainers configure the explicit
  `GH_MODELS_TOKEN` Actions secret. GitHub Actions rejects secret names
  beginning with `GITHUB_`, so `GH_MODELS_TOKEN` is the repository secret name.
- Uploads redacted artifacts with short retention.
- Replays scheduled live bundles, audits artifacts, and emits trend reports in
  the same workflow.

Local lane:

- Trigger: developer command.
- Supports replay, GitHub Models with a developer token, and optional Ollama.
- Uses the same scenario schema and scorers as CI.

## Budgets

Initial defaults:

- PR lane: 0 model requests.
- Scheduled lane: 6 scenarios, 1 model, 1 seed each.
- Max model turns per scenario: 8.
- Max tool calls per scenario: 16.
- Max completion tokens per turn: 512.
- Scheduled job timeout: 20 minutes.
- Local Ollama or OpenAI-compatible endpoint: scenario set, up to 3 seeds,
  60-minute timeout.

Budget exhaustion is reported as `inconclusive_budget_exhausted` unless journal,
oracle, or harness evidence supports a more specific failure class.

## Acceptance Criteria

Design and schema:

- All six requested files exist.
- Docs state development-only maturity.
- `evals/SCENARIO_SCHEMA.json` is valid JSON Schema.
- `evals/CAPABILITY_COVERAGE.yaml` names `AVL-001` through `AVL-004`.
- No public docs promote the lab as alpha-supported.

Implemented eval runner:

- `AVL-001` through `AVL-004` pass no-model scripted runs.
- `AVL-005` and `AVL-006` pass no-model scripted runs as next-phase coverage
  extensions.
- `AVL-007` passes as a deterministic expected provider-failure scenario.
- `AVL-008` passes as a deterministic expected budget-exhaustion scenario.
- `AVL-009` passes as a deterministic expected harness-failure scenario.
- `AVL-010` passes as a deterministic expected agent-failure scenario.
- `AVL-011` passes as a deterministic expected product-failure oracle-mismatch
  scenario.
- `AVL-012` passes as a deterministic concurrent child-run isolation scenario.
- `AVL-013` passes as a deterministic expected product-failure cross-run
  evidence-contamination scenario.
- `AVL-014` passes as a deterministic expected product-failure stateful
  lifecycle mutation-minimization scenario.
- `AVL-015` passes as a deterministic service-mode auth boundary scenario with
  a denied invalid synthetic read, an authorized metadata-only read, service
  authz oracle evidence, and raw-token redaction checks.
- `AVL-001` replay passes from a captured replay bundle.
- Replay-artifact runs include replay-equivalence scorecards.
- Run artifacts include provenance hashes and pass `audit-artifacts`.
- Journal verification, projection rebuild, contract validation, detection
  matching, redaction scan, and capability coverage pass for all scripted
  scenarios.
- Failure classification preserves product, agent, harness, provider, and
  budget classes.
- `lint-scenarios` and `check-boundaries` pass in PR CI.
- Reviewed regression promotion rejects unminimized or unaudited bundles.
- Suite runs write `suite-summary.json`, and GitHub job summaries include
  replay commands.
- Docker Compose lifecycle smoke passes when a Docker daemon is available.
- `AVL-001`, `AVL-002`, `AVL-003`, `AVL-004`, `AVL-005`, `AVL-014`, and
  `AVL-015` run through Docker-backed evals when a Docker daemon is available.
- Scorecard summaries report pass/fail, failure class, first failing scorer,
  and replay command.
- Regression corpus replay rejects unreviewed bundles.
- A reviewed `AVL-010` regression bundle replays without model calls.
- Trend reports render suite, capability, replay-equivalence, failure-class, and
  artifact-audit metrics.

## Required Commands

For design and schema:

```bash
uv run python scripts/check_claims_language.py docs evals
uv run python scripts/secret_scan.py docs evals
uv run pytest tests/security/test_release_hardening.py
```

For Python or dependency changes:

```bash
uv lock
uv run ruff check .
uv run ruff format --check .
uv run mypy src
uv run pytest
uv run python scripts/check_claims_language.py .
uv run python scripts/secret_scan.py .
uv run pip-audit
```

Run `uv lock` only when dependencies change.

## Owner Decisions

Owner approval is required before:

- Adding the uv `eval` dependency group.
- Choosing a scheduled GitHub Models model ID.
- Enabling repository Models access.
- Selecting artifact retention.
- Making eval failures release-blocking.
- Updating maturity docs to claim more than planned development work.

## Stop Conditions

Stop and ask for owner approval if implementation needs:

- Core event schema changes.
- Model credentials in PR workflows.
- Eval dependencies in core imports.
- Agent-authored pass/fail.
- Non-deterministic authoritative oracles.
- Real secrets, live cloud accounts, or paid providers.
- Unsupported public claims.
