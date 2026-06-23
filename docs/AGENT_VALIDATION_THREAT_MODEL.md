# Agent Validation Lab Threat Model

## Status

This threat model covers the development-only Agent Validation Lab. It does not
change the ActionLineage product threat model, event schema, or alpha release
surface.

## Security Objective

The lab should dynamically evaluate tool-using agents without turning agent
claims, provider responses, or tool acknowledgements into authoritative
security conclusions. It should preserve enough provenance to classify failures,
replay dynamic runs, and promote reviewed regressions while keeping model
credentials and synthetic sensitive material out of persisted artifacts.

## Assets

- Model and provider credentials used by scheduled or local runs.
- Synthetic prompts, system instructions, and agent transcripts.
- Tool descriptors, descriptor hashes, and tool-call arguments.
- Docker Compose configuration, images, service logs, and isolated volumes.
- Toxiproxy proxy definitions, toxics, timing, and seeds.
- Oracle observations and expected world state.
- ActionLineage journals, projections, contracts, detections, and scorecards.
- Replay bundles and minimized regression fixtures.
- Capability coverage metadata.
- Synthetic redaction canaries.
- Synthetic service-mode auth tokens and service-auth oracle decisions.

## Trust Boundaries

1. GitHub Actions workflow context to model provider.
2. Inspect harness to model adapter.
3. Model adapter to agent adapter.
4. Agent adapter to scenario tools.
5. Scenario tools to Docker Compose services.
6. Tool runtime to ActionLineage journal writer.
7. Docker environment to independent world-state oracles.
8. Journal/projection/contract/detection outputs to scenario scorers.
9. Live transcripts to replay and minimization tooling.
10. Pull-request code to scheduled default-branch model runs.

## Adversaries

- Malicious contributor attempting to exfiltrate model credentials through CI.
- Malicious or compromised model producing unsafe or misleading tool calls.
- Agent prompt injection embedded in scenario fixtures.
- Tool implementation that acknowledges success without producing a side effect.
- Fault-injection or Docker harness bug that misreports environment state.
- Provider outage, throttling, or model behavior drift.
- Contributor adding a scenario, detection, or replay fixture that hides a
  product regression.
- Local host attacker able to alter development artifacts.

## Threats And Controls

### T1: Agent Determines Pass/Fail

Risk: The agent reports success and the harness accepts that report.

Controls:

- Scorers read oracle observations, journals, projections, contracts, detections,
  and replay artifacts.
- Agent final text is recorded only as transcript evidence.
- The scenario schema requires explicit oracle and scorer declarations.

### T2: Tool Acknowledgement Treated As Side-Effect Evidence

Risk: A successful tool response is scored as if the environment changed.

Controls:

- Lifecycle scorer requires separate acknowledged, observed, and verified facts.
- Scenarios must declare expected observation and verification status.
- Receiver, filesystem, process, SQLite, and Toxiproxy oracles are independent of
  agent text.

### T3: Failure Classes Collapse Together

Risk: Product, agent, harness, and provider failures are reported as one generic
  eval failure.

Controls:

- Scorers emit one failure class from the approved vocabulary:
  `product_failure`, `agent_failure`, `harness_failure`, `provider_failure`, or
  `inconclusive_budget_exhausted`.
- Provider exceptions, timeout, rate limit, and budget events are recorded
  separately from journal or oracle mismatches.
- Harness health checks run before agent execution and after teardown.

### T4: Model Credentials Exposed To Untrusted Pull Requests

Risk: PR code obtains `GITHUB_TOKEN` model permissions or repository secrets.

Controls:

- PR lane uses `pull_request`, `contents: read`, and zero model requests.
- Scheduled no-model lane runs trusted default-branch code with zero model
  requests and produces deterministic public-report artifacts.
- Scheduled model lane runs only on default-branch trusted code with
  `models: read`, and skips live-model execution unless the explicit
  `GH_MODELS_TOKEN` secret is configured.
- Optional `GH_MODELS_TOKEN` secrets are only passed to scheduled or manually
  dispatched default-branch live-model jobs.
- Do not use `pull_request_target` for eval execution.
- Do not check out untrusted PR code in a privileged workflow.
- Artifacts from untrusted jobs are treated as untrusted input.

### T5: Eval Dependencies Enter Core Trusted Computing Base

Risk: Inspect AI, model clients, Docker helpers, or Toxiproxy clients become
runtime dependencies of the evidence plane.

Controls:

- Eval dependencies are isolated in the uv `eval` dependency group.
- Existing runtime dependencies and runtime extras are not changed.
- Import-boundary validation asserts core modules do not import eval packages.
- `check-boundaries` parses Python imports instead of relying on ad hoc text
  search, and treats model-provider libraries as eval-only at the core
  boundary.

### T6: Replay Lacks Provenance

Risk: A dynamic failure cannot be reproduced or reviewed.

Controls:

- Replay bundles include scenario, seed, mutation sequence, model metadata,
  generation parameters, prompt hashes, tool descriptors, transcript, tool
  calls, oracle observations, journal, projection, contract and detection
  outputs, Docker metadata, and Toxiproxy timeline.
- Minimized counterexamples preserve failure classification before promotion.

### T7: Synthetic Sensitive Data Leaks

Risk: Canaries or secret-shaped fixture values are persisted in journals,
transcripts, logs, exports, or error output.

Controls:

- Redaction scorer scans every artifact produced by a run.
- Scenario schema requires canary identifiers and artifact scan scopes when a
  redaction canary is used.
- Replay bundles store redacted tool arguments and digests rather than raw
  sensitive values.
- `AVL-015` treats synthetic service-token values as canaries so journals,
  transcripts, replay bundles, Inspect logs, and errors fail redaction scoring
  if raw token material is persisted.

### T8: Harness Or Oracle Bugs Create False Confidence

Risk: The lab incorrectly passes a broken product behavior.

Controls:

- Oracles declare trust boundaries and limitations.
- Scenario scorecards include harness health, oracle collection status, and
  inconclusive outcomes.
- Negative control scenarios intentionally induce oracle mismatches.
- `AVL-011` intentionally induces a missing verified oracle condition and must
  classify it as `product_failure` with no agent, provider, or harness error.
- `AVL-012` intentionally interleaves two child runs and must keep run IDs,
  evidence links, and projection readbacks isolated from the coordinator and
  from each other.
- `AVL-013` intentionally injects one cross-run evidence link between child
  runs and must classify the contamination as `product_failure` through the
  `run_isolation` scorer.
- `AVL-014` intentionally generates and minimizes a seeded lifecycle mutation
  sequence and must classify the missing verification-status counterexample as
  `product_failure` through the `stateful_mutation_minimization` scorer.
- `AVL-015` exercises optional service-mode auth boundaries outside the runtime
  dependency path: invalid synthetic credentials must be denied before dispatch,
  authorized synthetic reads must be corroborated by the service-auth oracle,
  and raw token values must stay out of artifacts.
- Replays must run without model calls and produce deterministic scorer output.
- Replay-equivalence checks compare source and replay scorecard essentials so a
  replay cannot silently drift while still reporting a local pass.
- Run provenance records scenario, schema, coverage, workflow, adapter, and
  artifact hashes for later attribution.
- Artifact audits scan generated outputs for canaries and provider credential
  patterns without echoing the matched value.
- Semantic scenario linting fails missing oracles, missing replay artifacts,
  stale coverage references, and untagged expected-failure controls.

### T9: Fault Injection Causes Ambiguous Results

Risk: Toxiproxy faults make provider, harness, and product timeouts hard to
distinguish.

Controls:

- Toxics are declared in the scenario manifest and recorded in run artifacts.
- Provider calls are outside the Docker network fault path unless explicitly
  declared.
- Product-facing network faults are tied to expected timed-out or unverified
  evidence statuses.
- Disposable Compose services use random host ports, explicit eval networks,
  dropped capabilities, no-new-privileges, read-only roots where possible, tmpfs
  scratch space, and resource caps to reduce local blast radius.

### T10: Scenario Or Detection Drift Weakens Coverage

Risk: New scenarios appear comprehensive but stop exercising key lifecycle or
capability states.

Controls:

- `evals/CAPABILITY_COVERAGE.yaml` maps capabilities to scenarios.
- Coverage gaps are explicit scenario-plan debt.
- Promotion of a scenario to a blocking lane requires owner-reviewed coverage
  metadata and replay fixtures.
- Reviewed regression promotion requires redaction audit, provenance, triage,
  replay artifacts, minimized transcript, and minimization report before a
  bundle enters the replayed corpus.
- Suite summaries and trend reports provide failure-class, scorer,
  replay-equivalence, coverage, and artifact-audit counts for CI review.

## Claims And Limitations

- The lab is development-only until implementation and maturity docs say
  otherwise.
- Passing an eval means the named scenario and named oracles satisfied their
  expected evidence checks under recorded limitations.
- Missing observations leave outcomes unknown, unverified, timed out, or
  inconclusive.
- The lab does not replace human review, external security review, endpoint
  controls, or production deployment validation.

## Stop Conditions

Stop implementation and ask for owner approval if a change would:

- Add eval dependencies to core runtime dependencies.
- Change `actionlineage.dev/v1alpha1` event compatibility.
- Give model credentials to untrusted pull-request code.
- Let an agent or model decide authoritative pass/fail.
- Require real secrets, live cloud accounts, paid model providers, or external
  infrastructure for the default eval path.
- Promote planned or preview behavior as alpha-supported.
