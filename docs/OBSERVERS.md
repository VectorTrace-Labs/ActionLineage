# Observers And Verification

Observers produce evidence about side effects independently from tool
acknowledgements. They do not authorize tool execution.

## Implemented Local Observers

- `FilesystemObserver`: observes local file state, conflicts, timeout, and
  unavailable states.
- `MockHttpReceiverObserver`: records deterministic fixture HTTP receipts.
- `HttpServerLogObserver`: records fixture HTTP access-log metadata and request
  body digests.
- `HttpResponseReadbackObserver`: records fixture response status, ETag, and
  body digest readbacks.
- `WebhookReceiptObserver`: records fixture webhook deliveries by digest and
  delivery metadata without storing raw request bodies.
- `ProcessObserver`: records local process exit/status evidence.
- `SqliteReadbackObserver`: performs local SQLite readback for database-record
  side effects with strict identifier validation.
- `AwsCloudTrailObserver`: interprets CloudTrail-style S3 object-write fixtures.
- `GcpAuditLogObserver`: interprets GCP Audit Log-style Cloud Storage fixtures.
- `AzureActivityObserver`: interprets Azure Activity Log-style Blob fixtures.
- `KubernetesAuditObserver`: interprets Kubernetes audit-log resource-change
  fixtures.
- `ExternalSensorFeedObserver`: normalizes reviewed external OS, EDR, eBPF,
  network, process, and file sensor records into redacted observation outcomes.

These observers are designed for local demos, CI, and fixture-backed tests. They
are not a claim that ActionLineage can observe every side effect in a production
environment.

SQLite readback is a post-action observation. A matching row can corroborate a
database write; a missing database leaves the outcome unverified. For expected
deletions, the observer records that no matching row was returned at query time
without using proof-of-absence language.

Webhook receipts are fixture observations for local testing and demos. They
store delivery IDs, status codes, body digests, and optional signature digests,
not raw webhook bodies or authorization headers. Missing delivery receipts leave
the outcome unverified.

HTTP server-log observations are also fixture-backed. They record URL, method,
status code, optional request ID, and optional body digest. They do not store raw
request bodies, cookies, or authorization headers.

HTTP response readbacks are fixture observations of a post-action response.
They record URL, status code, optional ETag, and optional body digest. They do
not store raw response bodies.

Fixture HTTP receiver, server-log, response-readback, and webhook observers
preserve caller-supplied digest strings for local correlation and add explicit
scope fields such as `body_digest_scope`,
`expected_body_digest_scope`, and `signature_digest_scope`. These scopes
identify the digest as observer fixture metadata, not a raw body, signature
verification result, or external trust root.

When HTTP receiver, server-log, response-readback, or webhook observers find
multiple equally plausible fixture records, they return `unverified` with an
`ambiguous_candidate_count` and a limitation that the correlation remains
ambiguous. They do not promote a duplicated or simultaneous-looking record set
to `observed` or `verified` without a unique match.

Cloud and Kubernetes observers are fixture-first. They validate local JSON
examples without credentials, cluster access, or API calls. Live AWS, GCP,
Azure, and Kubernetes collection adapters remain optional runtime work and must
preserve the same trust/limitation fields.

External sensor declarations describe producer identity, sensor family,
capabilities, trust level, and known blind spots for feeds such as EDR, eBPF,
OS audit, network, process, or file telemetry. Core code normalizes already
reviewed records and redacts observed state. It does not install agents, load
kernel programs, or collect live endpoint telemetry.

## Verification Helpers

`verify_observation()` maps observer outcomes into side-effect verification
payloads:

- Observed evidence becomes `side_effect.verified` when corroborated by an
  independent observer, post-action readback, or fixture oracle.
- Missing or unavailable evidence remains `side_effect.unverified`.
- Ambiguous evidence remains `side_effect.unverified` until a unique
  corroborating record can be identified.
- Timeout becomes `side_effect.timed_out`.
- Conflict becomes `side_effect.conflict_detected`.

`self_reported_verification()` records explicitly identified self-reported tool
evidence with lower confidence and `unverified` status.

## Claims Language

Use "no observation was recorded" or "the outcome remains unverified." Do not say
that absence of an observation proves absence of a side effect.

## Production Guidance

Production observers should document:

- Observer identity.
- Trust boundary.
- Failure and timeout behavior.
- Corroboration type.
- Known blind spots.
- Whether the observer can be tampered with by the same principal that executed
  the tool.
