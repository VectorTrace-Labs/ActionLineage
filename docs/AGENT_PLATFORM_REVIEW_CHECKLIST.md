# Agent Platform Review Checklist

Last reviewed: 2026-06-22.

Use this checklist when evaluating whether an agent platform, gateway, MCP
server, tool runtime, or observer can integrate with ActionLineage. It is an
integration review aid, not a statement that a listed platform is supported.

## Platform Mapping

For each tool surface, identify:

- tool name and canonical descriptor hash;
- delegated identity and principal type;
- request source and causal parent event;
- policy or approval decision, if any;
- dispatch boundary;
- acknowledgement response;
- independently observed side effect, if available;
- verification method and limitations;
- redaction policy before persistence and export.

## Lifecycle Semantics

Confirm the integration can preserve these states without collapsing them into
a single success or failure value:

- requested;
- authorized;
- dispatched;
- acknowledged;
- observed;
- verified;
- unverified;
- timed out;
- conflicting;
- denied or not dispatched;
- unknown.

If a platform cannot observe a state directly, record that limitation rather
than inventing evidence.

## Descriptor And Identity Checks

- Descriptor hashes must be stable for semantically identical tool descriptors.
- Descriptor drift should be detectable and reviewable.
- Principal identity should distinguish human, agent, service, scheduler, and
  external subjects when the upstream platform provides that context.
- Adapter metadata should not introduce provider-specific logic into the domain
  core.

## Observer And Verification Checks

- Observer identity, collection method, source timestamp, ingestion timestamp,
  confidence, evidence digest, and limitations should be recorded when known.
- Verification should cite the evidence event that corroborates the subject.
- Missing observations should remain missing observations.
- Conflicting observer evidence should preserve both sides.

## Privacy And Export Checks

- Run synthetic secret canaries through persistence, projection, case export,
  graph export, static console, telemetry mapping, and evaluation artifacts.
- Do not send live secrets or private customer data through public fixtures.
- Keep optional SDKs behind extras and away from core imports.

## Fit Decision

Classify the integration proposal as one of:

- local fixture only;
- preview adapter or observer;
- alpha-supported core path;
- blocked pending schema or policy decision;
- out of scope for the public alpha.

Any proposal that changes public schemas, event names, CLI flags, policy
semantics, or maturity labels requires owner approval before implementation.
