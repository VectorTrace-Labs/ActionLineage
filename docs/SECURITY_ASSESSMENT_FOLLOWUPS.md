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
- **Service ingest partial append failure**: local regression tests cover a
  multi-record service ingest where the first append commits and a later append
  fails. The service now returns HTTP 207 with `journal_committed: true`, a
  bounded failed outcome, and a rebuilt projection for the committed prefix.
- **Service ingest committed-prefix retry**: local regression tests cover
  retrying the same multi-record body after only its prefix committed. The retry
  reports the committed prefix as duplicate, imports the remaining suffix,
  rebuilds the projection, and avoids duplicate journal appends.
- **Service ingest process-crash recovery**: local subprocess regression tests
  cover a service process exiting after journal append and before projection
  rebuild. A restarted service reports `projection_stale`, rejects stale
  timeline reads, and repairs the projection on idempotent retry without adding
  a duplicate journal record.
- **Append checkpoint/index scope**: ADR-0011 keeps append indexes as future
  rebuildable caches rather than trusted evidence, and requires authenticated
  checkpoints to use anchor-style sidecars unless a future ADR changes the
  boundary.
- **Journal ingest benchmark tooling**: `scripts/benchmark_journal_ingest.py`
  generates synthetic journals and emits JSON timings for verified snapshots and
  duplicate idempotency scans. Tiny-count regression coverage keeps the script
  executable; 10k/100k benchmark artifacts are still local release/design-review
  work.
- **Capture digest scope**: local regression and property tests cover scoped
  capture digests for truncated text and byte values. Capture metadata now
  records `actionlineage.capture.v1/redaction-boundary` so bounded-content
  digests are not confused with plain external content hashes or signatures.
- **Aggregate capture limits**: local regression tests cover events that try to
  produce too many bounded capture markers or exceed the aggregate encoded
  captured-content budget. Redaction now fails closed before persistence when
  either limit is crossed.
- **Event-envelope capture preservation**: local regression tests cover tight
  capture settings that truncate payload content without corrupting
  `spec_version`, event type, timestamps, correlation, causality, principal,
  classification, or integrity control fields before serialization or journal
  append validation.
- **Observer digest scope**: local observer regressions cover body, expected
  body, and webhook signature digest scope fields. HTTP fixture observers now
  preserve digest strings for correlation while labeling them as observer
  metadata rather than raw bodies, signatures, or external trust roots.
- **Machine-readable export capture digest scope**: local export and case
  bundle regressions cover every export profile plus `case.json` and
  `events.ndjson`. Exported bounded-capture digests retain
  `actionlineage.capture.v1/redaction-boundary`; summary-only Markdown does not
  carry payload digest metadata.
- **Generated summary and demo-map capture scope**: local projection and release
  hardening regressions cover incident summaries and demo evidence-map artifacts
  that encounter bounded capture metadata. Generated summary labels preserve
  redaction-boundary digest scope as bounded notes and the demo-map generator
  redacts canaries before writing its JSON sidecar or SVG.
- **Public error detail redaction**: local CLI and service-mode regressions
  cover user-controlled identifiers flowing into JSON/HTTP error details.
  Public error serialization now redacts and bounds exception text before
  returning it to users, while Pydantic validation details remain generic.
- **Release smoke output redaction**: local release-hardening regressions cover
  subprocess stdout/stderr captured by the public quickstart smoke script,
  including timeout output. Smoke artifacts now redact canaries before writing
  bounded command output into release evidence JSON.
- **Core lower-level exception redaction**: local journal, projection, evidence
  ingestion, and service-mode regressions cover bearer-token and API-key
  canaries in journal storage-permission failures, service batch-import
  directory failures, projection schema/metadata exception details, and health
  issue messages/details. These core exception exits now redact and bound risky
  text before returning `JournalAppendError`, `ProjectionStateError` details, or
  service health JSON.

## Implemented before this slice

- **Ordinal service RBAC**: confirmed. ADR-0007 and implementation used a role
  rank ladder. Roles are now compatibility bundles of explicit capabilities,
  with no inheritance between `read`, `write`, and `export`.

## Confirmed or partially confirmed follow-ups

- **Journal scalability and append integrity**: partially confirmed. Appends
  verify the existing journal before write, preserving local integrity but
  requiring captured benchmark results before segmented checkpoint or
  append-index implementation. ADR-0011 requires future append indexes to remain
  rebuildable caches bound to verified journal state rather than trusted
  evidence; benchmark tooling now exists for verified snapshots and duplicate
  idempotency scans.
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
  digests at the redaction boundary. HTTP fixture observers label
  observer-supplied body and signature digests with explicit scope metadata. The
  default redaction policy covers common token, cookie, cloud-session, database
  URL, signed URL, webhook, and proxy-authorization field aliases, plus common
  inline assignment, signed URL parameter, and credential-bearing database URL
  forms. Bounded capture now enforces per-event capture-count and aggregate
  captured-content ceilings without corrupting event-envelope control fields.
  Machine-readable exporter, case-bundle, incident-summary, and demo-map
  artifacts that carry bounded capture metadata preserve redaction-boundary
  digest scope. Public CLI and service-mode error detail serialization redacts
  and bounds exception text before JSON/HTTP output, release smoke artifacts
  redact captured stdout/stderr before writing bounded command output, and core
  journal/ingestion/projection/health exception exits redact lower-level
  exception text.
  Broader digest-correlation review across release/network diagnostic scripts
  and future structured log surfaces remains open.
- **Container and deployment defaults**: partially confirmed. Runtime hardening
  should remain preview/local-ops scoped until container and Kubernetes defaults
  have executable validation.
- **Concurrency, idempotency, and batch semantics**: partially confirmed.
  Source ingestion and service-mode local journal writes have deterministic
  duplicate, conflict, partial-batch, projection-stale, and duplicate retry
  recovery tests, plus later-append storage failure handling after a committed
  prefix, retry completion for the remaining suffix, and subprocess crash
  recovery after append-before-projection. ADR-0011 preserves explicit partial
  success and defers any append index until benchmark evidence justifies a
  rebuildable cache. Remaining work includes a deliberate decision if future
  APIs need all-or-nothing transactional batch semantics instead of explicit
  partial success.
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
2. Run `scripts/benchmark_journal_ingest.py` at 10k, 100k, and feasible larger
   journals before proposing segmented journals or checkpoint indexes.
3. Draft ADRs for observer attestation policy, canonicalization v1, causal edge
   evolution, and external checkpoint trust roots.
4. Capture benchmark artifacts before implementing any ADR-0011 append-index
   cache.
5. Audit redaction digest behavior across release/network diagnostic scripts
   and any future structured log surfaces.
