# Threat Model

## Security objective

ActionLineage should make agent-driven tool activity attributable and investigation-ready without becoming a new source of credential leakage or false assurance.

## Assets

- Human and service identities.
- Agent and model identities.
- Delegated credentials and scopes.
- Tool descriptors and schema versions.
- Tool inputs, acknowledgements, observations, and side-effect evidence.
- Evidence links and verification status.
- Optional policy bundles and decisions.
- Audit journal and integrity anchors.
- Restricted or confidential data classifications.
- Detection rules, contracts, and scenario ground truth.

## Trust boundaries

1. Human/client to agent/orchestrator.
2. Agent/orchestrator to ActionLineage adapter.
3. Adapter to downstream tool or protocol runtime.
4. Adapter to optional policy evaluator.
5. Adapter to journal and query projection.
6. Observer/verifier to journal.
7. Adapter to telemetry exporter.
8. Administrator/contributor to scenario, detection, and contract repositories.

## Adversaries

- Malicious content author performing indirect prompt injection.
- Compromised or malicious tool server.
- Tool publisher changing a descriptor after approval or registration.
- Attacker with a stolen session or delegated token.
- Insider attempting to misuse an agent or erase evidence.
- Contributor introducing a malicious rule, fixture, dependency, or code change.
- Host-level attacker able to modify local files and processes.

## Threats and required controls

### T1: Indirect prompt injection drives unauthorized tool use

Controls:

- Preserve the causal link from untrusted resource read to subsequent action.
- Classify source data and destination trust.
- Record requested, authorized, dispatched, acknowledged, observed, and verified states separately.
- Allow optional policy adapters to deny high-risk transitions before dispatch.
- Include deterministic attack fixtures.

### T2: Confused deputy or authorization scope expansion

Controls:

- Record initiating principal, effective principal, credential identity, and effective scopes separately.
- Do not accept token passthrough as an implicit authorization model.
- Bind policy decisions and verification evidence to exact action, target, scope, and expiration where applicable.

### T3: Tool poisoning, shadowing, or rug pull

Controls:

- Canonicalize and hash complete tool descriptors when available.
- Emit descriptor-change evidence.
- Support protected tools that require reapproval in enforcement adapters.
- Do not trust display name alone as identity.

### T4: Mistaking acknowledgement for side-effect proof

Controls:

- Treat tool success as acknowledgement only.
- Require independent or explicitly identified corroborating evidence for `verified`.
- Represent unverified, timed-out, unknown, and conflicting outcomes.
- Do not treat absence of observation as proof of absence.

### T5: SSRF through HTTP-capable tools or OAuth discovery

Controls:

- Validate URL scheme and resolved destination in HTTP-capable adapters.
- Block link-local, loopback, private, and reserved ranges by default except explicit local demo allowlists.
- Revalidate redirects and consider DNS rebinding/TOCTOU.
- Keep the default demo on a private local mock boundary.

### T6: Session hijacking or replay

Controls:

- Bind session identifiers to authenticated context where available.
- Use nonce/idempotency keys for approval and action execution.
- Record sequence and timing.
- Reject stale or duplicated approval artifacts in enforcement adapters.

### T7: Data exfiltration through telemetry

Controls:

- Redact before journal, logs, traces, and error reporting.
- Maintain a denylist and structured sensitive-field annotations.
- Bound payload sizes.
- Capture hashes and metadata when full content is unnecessary.
- Test canary secrets across every sink.

### T8: Audit journal tampering

Controls:

- Canonical serialization and per-event hash chaining.
- Independent verification command.
- Optional signed or externally anchored roots in a later milestone.
- Documentation that a local attacker capable of rewriting journal and root can defeat an unanchored chain.

### T9: Policy bypass on evaluator failure

Controls:

- Keep enforcement optional and adapter-scoped.
- Use explicit fail behavior per tool risk class when an adapter enforces policy.
- No silent default allow.
- Emit degraded-mode events and health status.
- Test timeouts and malformed decisions.

### T10: Detection or evidence brittleness

Controls:

- Positive and benign fixtures.
- Lineage Lab mutation testing.
- Reproducible seeds and minimized counterexamples.
- Rule versioning and quality metrics.
- Contract checks for required observations and verification links.

## Out of scope

- Protecting evidence from a fully compromised kernel or root administrator.
- Guaranteeing model intent or correctness.
- Preventing all prompt-injection techniques.
- Comprehensive content classification or enterprise DLP.
- Hardware-backed signing or remote attestation.
- Proving that an unobserved side effect did not occur.
- Replacing endpoint security, DLP, IAM, SIEM, SOAR, or sandboxing controls.

## Security claims language

Use precise terms:

- Say **tamper-evident under a verified hash chain and trusted root**, not tamper-proof.
- Say **verified by the named observer or fixture**, not “proved universally.”
- Say **redacts configured and detected secret patterns**, not “never stores secrets.”
- Say **supports investigation-ready evidence**, not “forensically complete.”
- Say **no observation was recorded**, not “the side effect did not happen.”
