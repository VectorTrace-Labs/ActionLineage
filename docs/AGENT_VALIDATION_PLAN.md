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
   development-only corpus and replayed in no-model CI. Empty corpora are
   allowed until a reviewed failure is added.
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

1. Keep the `upload-artifact` warning non-blocking and bounded. The workflow
   opts into Node 24 while retaining the accepted pinned action SHA; an explicit
   Node 24 `upload-artifact` release pin was not kept because it caused a
   workflow startup failure in GitHub Actions.
2. Add `AVL-007 provider-lifecycle-failure` as a deterministic no-model
   scenario that validates `provider_failure` classification without depending
   on a real provider outage.
3. Add a scorecard summary command for CI logs and local triage.
4. Require explicit reviewed manifests before replay bundles enter the
   regression corpus; unreviewed promotions remain candidates.
5. Run `AVL-002` once through Docker/Toxiproxy in the Docker eval lane so the
   declared timeout scenario has live disposable-environment coverage.

Acceptance commands for this phase:

```bash
PYTHONPATH=evals uv run --group eval python -m actionlineage_evals validate-scenarios
PYTHONPATH=evals uv run --group eval python -m actionlineage_evals coverage
PYTHONPATH=evals uv run --group eval python -m actionlineage_evals run \
  --scenario-path evals/scenarios \
  --artifact-root build/evals/local \
  --mode scripted \
  --model-adapter scripted \
  --seeds 1
PYTHONPATH=evals uv run --group eval python -m actionlineage_evals replay-regressions \
  --regression-dir evals/regressions \
  --artifact-root build/evals/regression-replay \
  --allow-empty
PYTHONPATH=evals uv run --group eval python -m actionlineage_evals summarize \
  build/evals/local
PYTHONPATH=evals uv run --group eval python -m actionlineage_evals docker-smoke
PYTHONPATH=evals uv run --group eval python -m actionlineage_evals run \
  --scenario-path evals/scenarios/AVL-002.yaml \
  --artifact-root build/evals/docker-avl-002 \
  --mode scripted \
  --model-adapter scripted \
  --seeds 1 \
  --use-docker
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
- `evals/regressions/README.md`
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

Scheduled lane:

- Trigger: default-branch `schedule` and `workflow_dispatch`.
- Permissions: `contents: read`, `models: read`.
- Uses GitHub Models through `ModelAdapter`.
- Prefer a narrowly scoped `GH_MODELS_TOKEN` Actions secret when organization
  policy blocks repository `GITHUB_TOKEN` model inference. GitHub Actions
  rejects secret names beginning with `GITHUB_`, so `GH_MODELS_TOKEN` is the
  repository secret name. Fall back to `GITHUB_TOKEN` when GitHub Models is
  enabled for the organization/repository.
- Uploads redacted artifacts with short retention.

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
- `AVL-001` replay passes from a captured replay bundle.
- Journal verification, projection rebuild, contract validation, detection
  matching, redaction scan, and capability coverage pass for all scripted
  scenarios.
- Failure classification preserves product, agent, harness, provider, and
  budget classes.
- Docker Compose lifecycle smoke passes when a Docker daemon is available.
- `AVL-002` runs through Docker/Toxiproxy in the Docker eval lane when a Docker
  daemon is available.
- Scorecard summaries report pass/fail, failure class, first failing scorer,
  and replay command.
- Regression corpus replay rejects unreviewed bundles.

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
