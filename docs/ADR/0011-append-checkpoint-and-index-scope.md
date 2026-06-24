# ADR-0011: Append Checkpoint and Index Scope

- Status: Accepted
- Date: 2026-06-24
- Owners: Marq Mercado

## Context

Service-mode ingest now has executable recovery coverage for duplicate retries,
projection rebuild failures after committed appends, partial multi-record
commits, committed-prefix retries, and a subprocess crash after a journal append
commits before projection rebuild completes.

The remaining design pressure is whether to add an append index or authenticated
checkpoint to make replay and recovery faster or easier to reason about. This
decision must not weaken the product invariant that the append-only journal is
canonical evidence, projections are rebuildable query state, and local hash
chains are not tamper-proof without a trusted external root.

A local synthetic benchmark run on 2026-06-24 measured 10k, 100k, and 250k
record journals before any cache design. It showed linear-cost pressure for
full verified snapshots and duplicate idempotency scans: median verified
snapshot timings were 1.504702s, 16.369742s, and 41.759091s, while median
duplicate-idempotency scan timings were 1.519528s, 16.827593s, and 42.519948s.
This is local design-review evidence only. It does not prove production
throughput, does not authorize a trusted append index, and does not relax the
requirement that caches be rebuilt or ignored when they do not match verified
journal state.

## Decision drivers

- Keep the canonical event journal readable under `v1alpha1`.
- Avoid making optional service mode look like a production transaction log.
- Preserve explicit partial-success semantics for service batches.
- Avoid custom cryptographic primitives and new production dependencies.
- Keep indexes and projections rebuildable from a verified journal.
- Require external or separately protected trust roots before stronger
  durability or tamper-resistance claims.

## Options considered

### Transactional service batches

Pros:

- Familiar all-or-nothing API semantics for service clients.
- Easier client-side interpretation when a batch fails.

Cons:

- Conflicts with the current append-only local journal writer, which commits one
  complete canonical record at a time.
- Would require rollback, staging, or a new batch envelope before a public schema
  change is justified.
- Could hide already-committed evidence after a process crash or storage fault.

### Trusted append index

Pros:

- Could accelerate idempotency scans and replay recovery for large journals.
- Could expose a compact append checkpoint for service operators.

Cons:

- A trusted index can be mistaken for canonical evidence unless every read is
  bound back to verified journal bytes.
- Index corruption or staleness must fail closed and rebuild from the journal.
- Local benchmark data demonstrates linear verification and duplicate-scan cost
  pressure, but not a production requirement for a trusted index.

### Authenticated checkpoint sidecar

Pros:

- Can reuse existing journal anchors, optional HMAC signatures, anchor logs, Git
  statements, archive manifests, and external attestation sidecars.
- Does not require a journal event schema change.
- Can detect tail truncation or rewrite when the checkpoint is protected outside
  the journal bytes.

Cons:

- Still depends on protecting the key, anchor, log, Git ref, object lock, or
  external attestation outside ActionLineage.
- Does not replace per-record verification or projection row validation.
- Adds operator ceremony before there is benchmark evidence that it is needed
  for the default local alpha path.

### Rebuildable cache plus existing anchors

Pros:

- Preserves the current alpha trust model.
- Keeps idempotency and query acceleration as disposable cache concerns.
- Lets existing anchor and attestation machinery provide explicit trusted tail
  evidence when operators need it.

Cons:

- Large journals still require full verification scans before trusted reads and
  appends.
- Operators who want every append externally witnessed must build that workflow
  from anchors or external controls for now.

## Decision

Do not add a trusted append index or new checkpoint format to the public-alpha
service path yet.

Any future append index must be treated as a rebuildable cache. It may speed up
idempotency lookup or replay planning, but it must never be canonical evidence
and must not let a trusted read skip journal verification. A persisted index
must be bound to the verified journal source identity, journal byte digest,
record count, and terminal hash. If any value mismatches, ActionLineage must
ignore or rebuild the index rather than trusting it.

Any future authenticated append checkpoint must be a sidecar layered on the
existing anchor model or a successor ADR. The default shape is a trusted anchor
or anchor-log entry captured after a verified append or segment boundary, with
optional HMAC, Git, archive, or external attestation binding supplied by the
operator. It must not introduce raw payload copies, secret material, or a claim
that local evidence resists an attacker who can rewrite all local files and
trusted values.

Service-mode multi-record ingest remains explicitly partial. Recovery continues
to rely on the canonical journal, stale-projection detection, and idempotent
retry semantics until benchmark data justifies a rebuildable index.

Benchmark reports generated by `scripts/benchmark_journal_ingest.py` must carry
the `actionlineage.dev/journal-ingest-benchmark-analysis-v1` analysis block. The
analysis block records the measured operations, largest measured record count,
per-10k-record median timings, and a machine-readable decision boundary:
`trusted_append_index` is `not_allowed`, `future_append_index_scope` is
`rebuildable_cache_only`, and the append-only journal remains the canonical
evidence source.

## Consequences

- The measurement step is complete for 10k, 100k, and 250k synthetic local
  journals. A future cache proposal must now define target workloads,
  acceptance thresholds, stale/tamper/mismatched-journal tests, and rebuild
  semantics before implementation.
- Stronger durability claims require protected checkpoints or external
  attestations, not just a local cache.
- Existing `v1alpha1` journal event bytes remain unchanged.
- Optional service mode remains preview, with documented partial-success and
  retry recovery behavior.
- Future index work must include stale, tampered, mismatched-journal, and
  rebuild tests before it can influence trusted reads.

## Verification

- Service tests cover duplicate retry, partial HTTP 207, committed-prefix retry,
  projection-stale recovery, and subprocess crash recovery after append before
  projection rebuild.
- Projection tests cover journal source identity binding and fail-closed
  behavior for stale or mismatched projection metadata.
- Anchor tests cover unsigned anchors, optional HMAC signatures, anchor logs, Git
  statements, archive manifests, external attestation sidecars, and verified
  prefix recovery.
- Release-readiness tests require this ADR and the scorecard/follow-up docs to
  preserve the cache-versus-canonical boundary.
