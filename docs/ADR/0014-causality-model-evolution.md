# ADR-0014: Causality Model Evolution Boundary

- Status: Proposed
- Date: 2026-06-24
- Owners: Marq Mercado

## Context

The public `actionlineage.dev/v1alpha1` event envelope stores one
`causality.parent_event_id`, one `causality.root_event_id`, and one integer
`causality.sequence`. The local journal currently requires
`causality.sequence` to equal the journal record index. This makes the public
alpha simple and deterministic, but it also couples producer/source ordering to
journal position and prevents explicit representation of multi-parent causal
relationships.

Real agent investigations need more than one causal edge in several common
cases:

- A tool action can be caused by both a prompt-derived intent and a policy
  approval.
- A verifier result can depend on a subject event, an observer event, and a
  reviewed attestation declaration.
- A detection can cite multiple ordered stages, suppression facts, and
  conflicting evidence.
- A replay or imported source can preserve a producer sequence that differs from
  the local journal append order.

Changing this casually would alter schema compatibility, projection columns,
graph/export behavior, detection semantics, contract validation, and journal
hash input. A boundary ADR is needed before implementation.

## Decision drivers

- Preserve readability of existing `v1alpha1` journals.
- Keep the append-only journal position deterministic and auditable.
- Avoid weakening the current root/parent invariant for public-alpha events.
- Support future typed, multi-parent causal edges without ambiguous ordering.
- Keep cycles, missing parents, and out-of-order imported evidence fail-closed
  or explicitly represented.
- Avoid using payload-only conventions as a substitute for a schema migration
  once causal edges become part of the envelope contract.

## Options considered

### Keep the single parent forever

Pros:

- No schema migration.
- Existing projection, graph, explanation, and contract code stays simple.

Cons:

- Multi-factor causality must be hidden in payloads or duplicated events.
- Tool actions that depend on approvals, observations, or multiple prior reads
  become harder to investigate.
- Producer sequence and journal position remain conflated.

### Add ad hoc payload-level edge arrays in `v1alpha1`

Pros:

- Backward-compatible with the strict envelope.
- Can be prototyped without changing journal fields.

Cons:

- Payload conventions are easy for consumers to ignore or interpret
  inconsistently.
- Projection and graph exports could disagree on which edge set is
  authoritative.
- A payload-only convention would not solve the current journal-position versus
  producer-sequence coupling.

### Version the causality envelope

Pros:

- Makes causal edges an explicit schema contract.
- Allows separate journal position, producer/source sequence, and typed causal
  edges.
- Gives migrations, projections, detections, and exports one authoritative
  source of causal truth.

Cons:

- Requires a schema migration ADR and compatibility fixtures.
- Requires projection and export changes before mixed-version evidence can be
  trusted.
- Requires cycle and missing-parent validation semantics.

## Decision

Do not change `actionlineage.dev/v1alpha1` causality in this slice.

Future causal-edge evolution must use a versioned schema change or migration ADR
before any envelope-level causal edge is written to persisted evidence. The
future model must separate at least:

- Local journal position used for append ordering and hash-chain verification.
- Producer or source sequence when supplied by an imported system.
- Root lineage identifier semantics.
- A typed set of causal edges with edge IDs, source event ID, target event ID,
  edge type, producer, confidence or verification status where applicable, and
  limitations.

The migration ADR must decide whether the next schema version replaces
`parent_event_id`, preserves it as a compatibility primary edge, or carries both
single-parent and multi-edge views. It must also define how `v1alpha1` journals
are read, how projections index both versions, whether mixed-version journals
are allowed, and how detections, contracts, incident exports, graph exports, and
static console views select canonical causal edges.

Before implementation, checked-in acceptance tests must cover:

- Root events and documented root-event types.
- One-parent compatibility for current `v1alpha1` evidence.
- Multi-parent edges with distinct edge types.
- Missing parent references.
- Cycles and self edges.
- Out-of-order parent/child arrival in imported evidence.
- Producer sequence that differs from journal record order.
- Projection rebuild and verified reads across mixed evidence where allowed.
- Detection, contract, explanation, graph, and case-bundle rendering of the
  same edge set.

## Consequences

- Current public-alpha journals remain readable and keep the existing
  single-parent `causality` object.
- The current `causality.sequence` remains journal record position, not a
  general source sequence.
- Any public claim of typed multi-parent causality remains planned until a
  schema migration and executable tests land.
- Payload-level experiments may be used only as clearly labeled preview data,
  not as authoritative envelope causality.
- Future implementations must include migration notes and compatibility
  fixtures before changing event bytes or hash input.

## Verification

- Release-readiness tests require this ADR and public docs to keep
  single-parent `v1alpha1` causality separate from future typed multi-parent
  causal edges.
- Existing domain, journal, projection, console, detection, and contract tests
  continue to cover the current single-parent behavior.
- Future implementation tests must prove the edge cases listed in the Decision
  section before multi-parent causality is described as supported.
