# Project Charter

## Mission

Make tool-using agent activity attributable, inspectable, and investigation-ready by correlating intent, execution, delegated identity, and independently observed side effects.

## Product statement

ActionLineage is a vendor-neutral evidence and detection plane for tool-using agents. It records causal lineage across agent intent, tool execution, delegated identity, observations, and verification evidence so security teams can investigate agent-driven activity and test detection robustness.

MCP interception and policy enforcement are optional adapters. They can produce valuable evidence, but the append-only local journal and neutral event model are the product center.

## Primary users

- Detection and response engineers investigating agent-driven activity.
- Security platform engineers defining telemetry and response requirements.
- Agent platform engineers who need auditable tool execution.
- Product security engineers threat-modeling tool, identity, and observation boundaries.

## Core use cases

1. Reconstruct an agent action from intent through acknowledgement, observation, and verification.
2. Distinguish requested, authorized, dispatched, acknowledged, observed, verified, unknown, timed-out, and conflicting outcomes.
3. Explain which identity, credential scope, and adapter produced or corroborated evidence.
4. Identify tool schema or descriptor changes after approval or registration.
5. Validate that required telemetry exists before an agent integration ships.
6. Test whether detections survive realistic event variation and missing evidence.

## Public release success criteria

- The default demo runs locally with one documented command.
- The demo does not require a model API key, cloud account, or internet access.
- Every event validates against a versioned schema and typed model.
- The journal integrity verifier detects deletion, insertion, reordering, and mutation.
- Secret-like fixture values are redacted before persistence and export.
- The user can query one complete causal timeline by trace ID or run ID.
- The timeline distinguishes tool acknowledgement from independently observed and verified side effects.
- The repository includes architecture, threat model, acceptance tests, release
  checklist, security policy, privacy model, and reproducible evidence.

## Non-goals

- A universal agent framework.
- A complete SIEM, SOAR, DLP, or identity platform.
- A hard security boundary against a compromised operating system or root user.
- Automatic interpretation of arbitrary natural-language policy.
- Kernel-level side-effect correlation.
- Claims that absence of an observation proves absence of a side effect.
- Replacing SIEM, SOAR, DLP, IAM, sandboxing, or endpoint-security platforms.

## Differentiation

The project should not be marketed as “logging for agents.” Its distinctive value is the combination of:

- Causal lineage across intent, principals, tools, credentials, observations, and side effects.
- Explicit separation between requested, acknowledged, observed, and verified outcomes.
- Append-only local evidence with deterministic integrity verification.
- Telemetry requirements as code.
- Adversarial testing of detection and evidence robustness.
- Optional enforcement adapters that can deny actions without making enforcement the core product identity.

## Split criteria

A module may become a separate repository only when at least two of these are true:

- It has independent users who do not need ActionLineage Core.
- It requires an independent release cadence.
- It has stable public interfaces and separate maintainers.
- Its dependency graph meaningfully conflicts with the core project.
- Separating it reduces contributor friction more than it increases integration cost.
