# ADR-0012: Observer Attestation Policy

- Status: Proposed
- Date: 2026-06-24
- Owners: Marq Mercado

## Context

ActionLineage treats tool acknowledgements, observations, and verification as
separate evidence states. ADR-0006 defines the minimum corroboration threshold
for calling an outcome `verified`, including independent observer evidence,
post-action readback evidence, and reviewed fixture oracle evidence.

The current public alpha has observer records with trust labels, producer
identity, limitations, and redacted observed state. That is useful for local
demos and fixture-backed review, but it is not enough to prove that a producer
is independent from the tool, principal, host, network path, cloud account, or
control plane involved in the side effect. Without a structured attestation
policy, public wording can overstate observer independence.

## Decision drivers

- Preserve the invariant that acknowledgement is not side-effect proof.
- Avoid promoting fixture-backed or self-reported evidence to production
  independence.
- Make observer independence reviewable without adding live collectors to the
  domain core.
- Keep `actionlineage.dev/v1alpha1` journals readable until a versioned model
  change is approved.
- Avoid custom cryptography or vendor-specific attestation requirements in the
  core package.
- Keep missing, unavailable, timed-out, and conflicting observations explicit.

## Options considered

### Trust labels only

Pros:

- Already implemented in local observer outcomes and external sensor
  declarations.
- Simple for fixture-backed tests and demos.

Cons:

- A label such as `external` or `trusted` does not explain whether the producer
  shares credentials, host control, network path, storage, or administrative
  authority with the subject action.
- A compromised tool, host, or account could produce both the side effect and
  the observation while still carrying a favorable trust label.
- It does not give reviewers enough information to distinguish fixture oracle,
  post-action readback, independent observer, and self-reported evidence.

### Require cryptographic remote attestation for all independent observers

Pros:

- Stronger for high-assurance production sensors when paired with protected
  keys, signed software identity, and externally verified statements.
- Gives a clear technical basis for some independence claims.

Cons:

- Out of scope for the public alpha and the local deterministic demo.
- Would pull hardware, cloud, or vendor-specific trust roots into the core
  model too early.
- Still would not prove semantic independence by itself; operators must also
  evaluate credentials, account ownership, network location, and blind spots.

### Structured attestation policy plus maturity labels

Pros:

- Keeps the current alpha honest while preserving a path for stronger observer
  evidence.
- Lets fixtures, post-action readbacks, external feeds, and future live sensors
  declare different independence properties.
- Keeps cryptographic attestation optional and layered behind future ADRs or
  adapter-specific documentation.
- Does not change existing event schema bytes in this slice.

Cons:

- Requires a future versioned model or declaration format before runtime code
  can enforce the policy mechanically.
- Operators still need to review and maintain the declarations for their
  environment.

## Decision

Use a structured observer attestation policy as the next design boundary, but
do not change the public `v1alpha1` event schema in this slice.

An observer may be described as an `independent_observer` only when a reviewed
declaration, adapter configuration, fixture manifest, or future versioned model
records at least:

- Observer identity and producer identity.
- Collection method and data source.
- Subject action types and resource types it can corroborate.
- Independence boundaries from the subject tool, principal, credential,
  execution host, network path, storage plane, and administrative control plane.
- Known shared dependencies and blind spots.
- Failure, timeout, delay, replay, and clock-skew behavior.
- Tamper and retention assumptions for the observation source.
- Redaction and digest scopes for captured content.
- Whether evidence is fixture oracle, post-action readback, external sensor
  feed, self-reported, or independently produced live telemetry.
- Review date, policy version, and owner.

If those declarations are missing, incomplete, stale, contradictory, or outside
their stated scope, ActionLineage must not upgrade the evidence to an
unqualified independent-observer claim. It may still record the observation with
explicit limitations, lower confidence, `post_action_readback`,
`fixture_oracle`, `self_reported`, or `unknown` corroboration as appropriate.

Fixture-backed observers remain suitable for local demos, CI, and regression
tests. They can satisfy demo contracts only within their declared fixture
scope. Live cloud, Kubernetes, EDR, eBPF, process, network, file, or endpoint
collectors remain preview until their declarations, failure modes, redaction
behavior, and operational trust roots have executable validation.

Cryptographic remote attestation, signed sensor statements, WORM retention, or
managed evidence storage may strengthen a future observer declaration, but none
of them is required by this ADR and none of them alone proves semantic
independence.

## Consequences

- Public docs should say "independent or explicitly identified corroborating
  evidence" unless the observer has a reviewed independence declaration.
- Current local observers keep their existing event representation and
  limitations.
- Future observer model work should introduce a versioned declaration or policy
  object before expanding production independence claims.
- Future tests should cover stale declarations, missing declarations, shared
  control-plane conflicts, self-reported evidence, timeout/unavailable states,
  and redaction leakage.
- External sensor integrations remain preview until this policy is represented
  in executable configuration and validated against fixtures or live-review
  evidence.

## Verification

- Release-readiness tests require this ADR and observer documentation to keep
  the attestation boundary visible.
- Existing observer tests continue to cover observed, unverified, timed-out,
  unavailable, ambiguous, and conflicting outcomes without proof-of-absence
  wording.
- Future implementation tests must prove that evidence outside a declaration's
  scope cannot be upgraded to an unqualified `independent_observer` claim.
