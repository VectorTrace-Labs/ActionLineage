# Security Architecture Assessment Follow-ups

This note tracks the current hardening assessment from the public-alpha
security review. It is intentionally scoped to actionable repository follow-up
and does not expand ActionLineage into a generic tracing platform.

## Implemented in this hardening slice

- **Deep immutability of verified state**: confirmed. `EventEnvelope.payload`
  previously froze the top-level Pydantic model but left nested dictionaries
  and lists mutable. Payloads are now recursively frozen at validation time and
  thawed only for deterministic JSON serialization.
- **Projection-to-journal binding**: confirmed. SQLite query and export paths
  could read a projection without proving it still matched the canonical
  verified journal. Projection-backed reads now verify source journal identity,
  verified record count, terminal hash, row count, event hashes, and canonical
  event JSON before returning evidence.
- **Ordinal service RBAC**: confirmed. ADR-0007 and implementation used a role
  rank ladder. Roles are now compatibility bundles of explicit capabilities,
  with no inheritance between `read`, `write`, and `export`.

## Confirmed or partially confirmed follow-ups

- **Journal scalability and append integrity**: partially confirmed. Appends
  verify the existing journal before write, preserving local integrity but
  requiring performance benchmarks before segmented checkpoints or append-index
  changes. Crash-consistency fault injection should be expanded before changing
  durability behavior.
- **Observer independence**: partially confirmed. Observer records carry trust
  labels and limitations, but independence is not yet the result of a structured
  attestation policy. This requires an ADR and versioned model work.
- **External trust root**: confirmed as future work. Local hash chains and local
  anchors remain local tamper evidence only. Remote witness, KMS/HSM signing,
  transparency log, or WORM storage support needs a checkpoint ADR before code.
- **Canonicalization v1**: partially confirmed. The current deterministic JSON
  boundary is documented as interim. A cross-language canonicalization standard
  or byte-level specification requires conformance vectors and migration notes.
- **Causality model evolution**: confirmed as schema-evolution work. Current
  sequence handling still couples source sequence and journal order. Multi-parent
  causal edges require a versioned schema change or migration path.
- **Input limits and redaction**: partially confirmed. Existing redaction and
  size controls need structural-depth, collection-count, attachment-count, and
  digest-correlation review across all sinks.
- **Container and deployment defaults**: partially confirmed. Runtime hardening
  should remain preview/local-ops scoped until container and Kubernetes defaults
  have executable validation.
- **Concurrency, idempotency, and batch semantics**: partially confirmed. Source
  ingestion has idempotency tests, but service-level concurrent duplicate and
  partial-batch semantics need deterministic API tests and documentation.
- **Tenant isolation**: partially confirmed. Tenant-aware authorization
  primitives exist, but end-to-end tenant isolation across storage, projections,
  exports, logs, caches, and anchors is not demonstrated.
- **Protected kernel boundary**: partially confirmed. Core imports are tested,
  but an explicit kernel boundary ADR and import-boundary tests should cover
  anchoring, observer policy, projection contracts, and query/export trust
  boundaries.
- **Generated release evidence**: follow-up. Manual scorecards should be backed
  by a commit-bound evidence manifest before stronger release claims.
- **External validation**: follow-up. Independent review, partner integrations,
  and a conflict-demonstration case study remain product-validation work.

## Next implementation order

1. Add projection-state checks to any future non-SQLite read APIs before those
   APIs are exposed.
2. Benchmark append verification at 10k, 100k, and feasible larger journals
   before proposing segmented journals or checkpoint indexes.
3. Draft ADRs for observer attestation policy, canonicalization v1, causal edge
   evolution, and external checkpoint trust roots.
4. Expand service ingestion tests for concurrency, idempotency conflicts,
   projection rebuild failure after append, and partial batch responses.
5. Audit input structural limits and redaction digest behavior across journal,
   projection, export, logs, exceptions, and test snapshots.
