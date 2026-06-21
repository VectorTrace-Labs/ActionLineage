# Acceptance Tests

Each test must be executable. Documentation-only evidence does not satisfy an acceptance criterion.

## Core event model

- **AT-EVT-001**: Every event validates against the JSON schema and typed model.
- **AT-EVT-002**: Unknown fields are handled according to the documented compatibility policy.
- **AT-EVT-003**: Root events may omit `parent_event_id`; non-root action events may not.
- **AT-EVT-004**: IDs remain stable through serialization/deserialization.
- **AT-EVT-005**: Timestamps are UTC and canonicalized.

## Evidence lifecycle

- **AT-EVD-001**: Neutral evidence-plane event types validate against the JSON schema and typed model.
- **AT-EVD-002**: A tool acknowledgement is not interpreted as side-effect observation or verification.
- **AT-EVD-003**: Verified side effects require an explicit evidence link to corroborating evidence.
- **AT-EVD-004**: Unknown, unverified, timed-out, and conflicting outcomes are representable.
- **AT-EVD-005**: Absence of an observation is not described as proof of absence.
- **AT-EVD-006**: Timeline and incident export expose verification status and evidence-link IDs when present.
- **AT-EVD-007**: A blocked or denied tool execution is represented as not dispatched rather than as a downstream failure.

## Redaction

- **AT-RED-001**: Bearer-token fixture never appears in journal, structured logs, traces, API output, or test snapshots.
- **AT-RED-002**: Configured sensitive JSON paths are redacted before hashing and persistence.
- **AT-RED-003**: Oversized payloads are truncated with an explicit metadata marker and digest.
- **AT-RED-004**: Redaction failure cannot silently persist the original raw value.

## Journal integrity

- **AT-JRN-001**: A valid journal verifies successfully.
- **AT-JRN-002**: Mutating one byte in an event fails verification at the correct record.
- **AT-JRN-003**: Deleting, inserting, duplicating, or reordering an event fails verification when trusted anchors make those changes observable.
- **AT-JRN-004**: The query projection can be deleted and rebuilt from a verified journal.
- **AT-JRN-005**: Concurrent writes preserve a deterministic sequence or fail visibly.
- **AT-JRN-010**: A Git anchor statement verifies committed anchor bytes and reports anchor mutation or ref drift without mutating repository history.
- **AT-JRN-011**: External attestation sidecars bind anchor bytes to external statement digests and report anchor or statement mismatches without implementing custom cryptography.

## Optional MCP adapter

- **AT-MCP-001**: Tool descriptors exposed upstream are functionally equivalent to downstream descriptors.
- **AT-MCP-002**: Canonically equivalent descriptors produce the same hash.
- **AT-MCP-003**: A meaningful schema/description change produces a different hash and a drift event.
- **AT-MCP-004**: A denied tool call never reaches the downstream mock server when enforcement is enabled.
- **AT-MCP-005**: Timeout and malformed-result paths produce explicit failed or unverified events.

## Optional policy adapter

- **AT-POL-001**: `allow`, `deny`, `require_approval`, and `dry_run` are all represented and tested.
- **AT-POL-002**: Policy bundle and rule versions are included in every decision.
- **AT-POL-003**: Evaluator timeout follows the configured fail behavior.
- **AT-POL-004**: An approval cannot be reused outside its action, target, scope, or expiration.

## Deterministic demo

- **AT-DEMO-001**: One command starts the local evidence-plane scenario.
- **AT-DEMO-002**: The timeline records agent intent and delegated identity.
- **AT-DEMO-003**: The timeline records tool execution requested, authorized, dispatched, and acknowledged states separately.
- **AT-DEMO-004**: The demo includes an acknowledged tool response that remains unverified until corroborating evidence appears.
- **AT-DEMO-005**: The demo includes at least one side effect verified by an independent or explicitly identified observer.
- **AT-DEMO-006**: The demo produces identical normalized evidence across repeated runs except documented nondeterministic fields.

## Lineage Contracts

- **AT-CON-001**: A valid demo timeline satisfies its contract.
- **AT-CON-002**: Removing a required field identifies the exact requirement and affected event.
- **AT-CON-003**: Breaking a required parent-child or evidence-link relationship fails validation.
- **AT-CON-004**: An invalid integrity chain fails the contract.
- **AT-CON-005**: A contract can require verified, unverified, timed-out, or conflicting outcomes.

## Lineage Lab

- **AT-LAB-001**: A fixed seed reproduces the same mutation sequence.
- **AT-LAB-002**: A failing case is minimized and saved as a fixture.
- **AT-LAB-003**: Benign fixtures remain below the configured false-positive threshold.
- **AT-LAB-004**: The scorecard reports detection survival, evidence completeness, and latency.

## Public API and compatibility

- **AT-API-001**: Public Python imports for events, normalization, journal, projection,
  contracts, detections, and lab replay are documented and covered by import tests.
- **AT-API-002**: Event explanation output identifies causal parents, children, and evidence
  links without exposing redacted payload material.
- **AT-COMPAT-001**: The documented `v1alpha1` compatibility policy is enforced by tests.
- **AT-COMPAT-002**: Golden journals from accepted baseline, evidence-plane, and legacy
  `agent.tool.*` fixtures validate, verify, and rebuild projections.
- **AT-COMPAT-003**: Evidence-link payload conventions validate without adding envelope-level
  fields.
- **AT-COMPAT-004**: Future journal segments and manifests preserve readability of supported
  single-file journals.

## Source-neutral ingestion

- **AT-ING-001**: Stable ingestion records normalize into valid neutral lifecycle events.
- **AT-ING-002**: Batch import validates, redacts, deterministically orders, persists, and
  reports partial failures.
- **AT-ING-003**: Replayed batches with the same idempotency keys do not duplicate canonical
  evidence.
- **AT-ING-004**: Local, file, HTTP, MCP-mapped, and external JSON sources use the neutral
  ingestion boundary without importing optional adapter dependencies into core modules.

## Investigation export

- **AT-EXP-001**: Expanded incident export includes principals, delegated credentials, tool
  descriptors, resources, verification matrix, conflicts, unknowns, limitations, and detection
  hits.
- **AT-EXP-002**: Timeline filters for principal, tool, resource, verification status,
  sensitivity, trust, event type, time range, and descriptor hash are deterministic.
- **AT-EXP-003**: Case bundle export produces redacted JSON, NDJSON, Markdown, and sanitized
  evidence artifacts with stable timeline order.
- **AT-EXP-004**: Grounded summaries include limitations and event IDs and do not call a
  model provider.
- **AT-EXP-005**: Investigation graph export includes deterministic event, causal,
  evidence-link, principal, tool, resource, and verification-status relationships without
  introducing a new canonical store.

## Detection engine 1.0

- **AT-DET-001**: Versioned detection rules include metadata, severity, tags, rationale,
  references, and required evidence quality.
- **AT-DET-002**: Bounded expressions handle equality, membership, prefix/suffix, constrained
  regex, numeric/time comparison, existence, and unknown semantics.
- **AT-DET-003**: Sequence rules support grouping, windows, ordered and unordered stages,
  suppression, and deduplication.
- **AT-DET-004**: Alert export references the exact evidence that satisfied each rule stage.
- **AT-DET-005**: Built-in starter rules pass positive, benign, ambiguous, duplicate,
  out-of-order, timeout, and performance fixtures.

## Contracts 1.0

- **AT-CON-006**: The formal contract schema covers required events, fields, causal links,
  evidence links, latency, integrity, descriptor identity, and detection coverage.
- **AT-CON-007**: `contract validate`, `contract explain`, `contract init`, and `contract test`
  commands produce deterministic output.
- **AT-CON-008**: CI output is machine-readable and identifies exact failed requirements.
- **AT-CON-009**: Control-dependency validation fails when a detection relies on missing
  observation or verification evidence.
- **AT-CON-010**: MCP, HTTP, filesystem, cloud object, and restricted-exfiltration examples
  validate or fail as documented.

## Lab 1.0

- **AT-LAB-005**: Canonical journals and scenario manifests replay deterministically.
- **AT-LAB-006**: Every mutation strategy declares the semantic property it preserves.
- **AT-LAB-007**: Minimized counterexamples are reproducible and saved as reviewed fixtures.
- **AT-LAB-008**: Scorecards report survival, false positives, fragility, latency, and evidence
  completeness.
- **AT-LAB-009**: Positive, benign, ambiguous, adversarial, regression, and public-example
  corpora are addressable by tests.

## Adapter runtime

- **AT-ADAPT-001**: Core modules do not import optional MCP, OpenTelemetry, service, cloud, or
  model-provider dependencies.
- **AT-ADAPT-002**: Optional MCP runtime maps downstream calls into neutral lifecycle events.
- **AT-ADAPT-003**: Telemetry exporter failure does not drop or replace local journal evidence.
- **AT-ADAPT-004**: File and webhook sinks export only redacted evidence.
- **AT-ADAPT-005**: Framework adapters preserve transport-neutral tool identity.

## Observer suite

- **AT-OBS-001**: Filesystem observations record trust, limitations, and verification status.
- **AT-OBS-002**: HTTP receiver, callback, log, and readback observations can corroborate or
  fail to corroborate a tool acknowledgement.
- **AT-OBS-003**: Process observations record explicit status without overclaiming side effects.
- **AT-OBS-004**: Cloud observer fixtures validate without requiring cloud credentials.
- **AT-OBS-005**: Timeout, unavailable, self-reported, low-confidence, and conflicting outcomes
  are represented without proof-of-absence language.
- **AT-OBS-006**: External OS, EDR, eBPF, network, process, and file sensor feeds are
  represented through reviewed declarations, redacted observed state, trust labels, and
  limitations without adding live collectors to core.

## Operations and UI

- **AT-OPS-001**: Projection compaction and journal archive behavior never silently compact
  canonical journals.
- **AT-OPS-002**: Optional service mode exposes ingest, query, export, health, contract, and
  detection endpoints behind explicit extras.
- **AT-OPS-003**: Optional service auth and RBAC enforce read, write, admin, and export scopes.
- **AT-OPS-004**: Optional Postgres projection rebuilds from canonical journal evidence.
- **AT-OPS-005**: Backup, restore, sizing, health, and degraded-mode procedures are executable.
- **AT-OPS-006**: Journal archive manifests verify local journal bytes and trusted tail values
  without claiming object-lock enforcement.
- **AT-OPS-007**: Tenant-scoped service authorization requires both global service roles and
  per-tenant role bindings, and denies missing tenants or bindings explicitly.
- **AT-UI-001**: Optional console timeline and event-detail views render deterministic demo data.
- **AT-UI-002**: Optional console evidence graph preserves causal and evidence-link direction.
- **AT-UI-003**: Optional console verification matrix distinguishes verified, unverified,
  timed-out, and conflicting outcomes.
- **AT-UI-004**: Optional console case export preserves redaction and no-proof-by-absence wording.
- **AT-UI-005**: Desktop bundle export writes a deterministic static console entrypoint and
  manifest for optional native shells without adding a desktop runtime to core.

## Security and release

- **AT-SEC-001**: Public exceptions and error output do not leak raw payloads or redacted values.
- **AT-SEC-002**: Reports and docs do not claim proof of absence, tamper-proof behavior,
  forensic completeness, or universal security.
- **AT-SEC-003**: Redaction canaries are absent from every telemetry and export sink.
- **AT-SEC-004**: Security policy, vulnerability disclosure, and privacy model are documented.
- **AT-SEC-005**: Secret scanning, dependency audit, SBOM, and license checks run in CI or the
  release checklist.
- **AT-SEC-006**: Fuzz/property tests cover redaction, serialization, schema parsing, detection
  expressions, contracts, and importers.
- **AT-SEC-007**: Adversarial fixtures cover prompt-injection chains, descriptor drift,
  malformed adapter payloads, replayed approvals, conflicting observers, and oversized payloads.
- **AT-SEC-008**: Payload size, journal append, projection rebuild, detection evaluation, and
  replay mutation have documented resource bounds.
- **AT-REL-001**: Export mapping golden files are deterministic.
- **AT-REL-002**: Deployment artifacts, when in scope, pass local smoke tests.
- **AT-REL-003**: Version progression and package metadata match the release stage.
- **AT-REL-004**: Package extras keep optional dependencies out of the core install.
- **AT-REL-005**: API, CLI, schema, tutorial, migration, FAQ, and examples docs are tested where
  executable.
- **AT-REL-006**: Community templates cover adapters, detections, contracts, compatibility, and
  security reports.
- **AT-REL-007**: The release checklist verifies CI, audit status, SBOM, signed artifacts,
  changelog, migration notes, and demo output.
- **AT-REL-008**: Extension-pack manifests validate local artifact kinds, safe paths,
  duplicate entries, and optional SHA-256 checksums without executing pack contents.
- **AT-REL-009**: The OpenTelemetry semantic-convention proposal remains aligned with
  redacted exporter attributes and does not claim upstream standardization.
