# Security Architecture Assessment Follow-ups

This note tracks the current hardening assessment from the public-alpha
security review. It is intentionally scoped to actionable repository follow-up
and does not expand ActionLineage into a generic tracing platform.

## Adversarially verified in this hardening slice

- **Immutable verified event payload views**: local regression tests cover
  ordinary mutation, `dict.__setitem__`, `dict.update`, `list.append`,
  `list.__setitem__`, caller alias mutation, and Pydantic
  `model_copy(update=...)`/`model_construct(...)` paths. `EventEnvelope.payload`
  now uses immutable `Mapping`/sequence containers that do not subclass mutable
  built-ins, and returns mutable JSON only through explicit serialization
  boundaries as defensive copies.
- **SQLite projection binding for verified reads**: local regression tests cover
  every projected column that can influence selection, ordering, interpretation,
  or output, including selector fields, timestamps, sequence, parent IDs,
  verification status, evidence-link IDs, event JSON, hashes, record numbers,
  and unexpected SQLite runtime types. Projection-backed reads now use an
  explicit caller-supplied journal path, a read-only SQLite connection,
  `PRAGMA query_only`, one read transaction for verification and query, complete
  row verification from the same deterministic derivation used for insertion,
  and a terminal journal-state recheck before returning current results.
- **Read-only projection verification and health**: local regression tests cover
  missing and incomplete projection databases and assert verification does not
  create files, tables, metadata, or migrations on read paths.
- **Public result defensive copies**: local regression tests cover mutable
  nested observer state, external sensor records, extension-pack metadata, pack
  compatibility metadata, and service-health details. These public result
  boundaries now return defensive copies so caller mutation of one result object
  cannot change subsequent renders from the same trusted object.
- **Service ingestion idempotency and partial outcomes**: local regression tests
  cover service-level replay, same-key/different-record conflicts, concurrent
  duplicate requests released through a barrier, partial-batch HTTP 207
  responses, and projection rebuild failure after a committed journal append.
  The service now scans idempotency fingerprints, assigns journal sequences, and
  appends under the local journal lock, then reports stale projections without
  rolling back or hiding the canonical append.
- **Strict journal record parsing**: local regression tests cover exact
  canonical byte equality, duplicate JSON keys across envelope and nested
  security value objects, reordered keys, added whitespace, CRLF line endings,
  invalid UTF-8, trailing JSON, multiple JSON values, and non-finite numeric
  tokens. Journal verification now rejects byte-different semantic rewrites
  before accepting a record into a verified snapshot.
- **Case bundle publication**: local regression tests cover manifest file
  digests, verified journal/projection binding, POSIX `0700` directory and
  `0600` file modes under a permissive umask, cleanup after injected write,
  staging-directory sync, and publish failures, and preservation of an existing
  valid bundle. Case export now stages privately and publishes with an atomic
  directory rename instead of writing loose files directly into the final path.
- **Service role/capability boundary**: local regression tests cover immutable
  static token mappings, JWT capability-only credentials, and tenant decisions
  that reject capability-only principals. Capability grants authorize explicit
  capability checks but no longer satisfy global or tenant role checks.
- **Service ingest retry recovery**: local regression tests cover the case where
  a journal append commits but projection rebuild fails. Retrying the same
  idempotency key now reports a duplicate and rebuilds the projection instead
  of leaving the query surface stale.
- **Capture digest scope**: local regression and property tests cover scoped
  capture digests for truncated text and byte values. Capture metadata now
  records `actionlineage.capture.v1/redaction-boundary` so bounded-content
  digests are not confused with plain external content hashes or signatures.

## Implemented before this slice

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
- **Stable journal identity**: locally confirmed for projections. ADR-0010
  defines `actionlineage.dev/journal-source-identity-v1`, a path-independent
  digest over the verified journal byte digest, record count, and terminal event
  hash. Verified projection reads still require an explicit caller-supplied
  journal path, allow moved byte-identical journals, fail closed for changed
  journal contents, and force rebuild for legacy `local-file:` identities. This
  remains local tamper evidence, not a journal UUID, signature, WORM guarantee,
  or externally anchored checkpoint identity.
- **Canonicalization v1**: partially confirmed. Local journal records are now
  byte-canonical under the current deterministic serializer, but that serializer
  remains an interim `json-deterministic-v0` boundary. A cross-language
  canonicalization standard such as RFC 8785/JCS still requires conformance
  vectors for Unicode, numbers, timestamps, escaping, duplicate keys, and schema
  versions before stronger portability claims.
- **Causality model evolution**: confirmed as schema-evolution work. Current
  sequence handling still couples source sequence and journal order. Multi-parent
  causal edges require a versioned schema change or migration path.
- **Input limits and redaction**: partially confirmed. Non-finite JSON numbers
  are rejected at the event and redaction boundaries. Event validation,
  normalization, and redaction now enforce default JSON nesting-depth,
  object-member, and array-length limits. Bounded capture metadata uses scoped
  digests at the redaction boundary. Attachment-count limits and broader
  digest-correlation review for observer-supplied body digests remain open.
- **Container and deployment defaults**: partially confirmed. Runtime hardening
  should remain preview/local-ops scoped until container and Kubernetes defaults
  have executable validation.
- **Concurrency, idempotency, and batch semantics**: partially confirmed.
  Source ingestion and service-mode local journal writes have deterministic
  duplicate, conflict, partial-batch, projection-stale, and duplicate retry
  recovery tests. Remaining work includes process-crash fault injection,
  authenticated append indexes or checkpoints for stronger replay recovery, and
  a deliberate decision if future APIs need all-or-nothing transactional batch
  semantics instead of explicit partial success.
- **Tenant isolation**: partially confirmed. Tenant-aware authorization
  primitives exist, but end-to-end tenant isolation across storage, projections,
  exports, logs, caches, and anchors is not demonstrated.
- **Protected kernel boundary**: partially confirmed. Core imports are tested,
  but an explicit kernel boundary ADR and import-boundary tests should cover
  anchoring, observer policy, projection contracts, and query/export trust
  boundaries.
- **Case bundle signatures and long-running recovery**: follow-up. Case bundle
  manifests reserve future external signature/checkpoint fields but do not sign
  artifacts or prove WORM/object-lock behavior. Longer-running crash and
  filesystem fault injection should be added before stronger durability claims.
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
4. Add deeper service ingestion crash/fault injection around process restart
   after append and storage errors during multi-record batches.
5. Audit attachment-count limits and redaction digest behavior across journal,
   projection, export, logs, exceptions, and test snapshots.
