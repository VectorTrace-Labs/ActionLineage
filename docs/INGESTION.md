# Source-Neutral Ingestion

ActionLineage ingestion accepts normalized evidence records from adapters without
requiring the domain core to depend on MCP, OpenTelemetry, model providers, HTTP
frameworks, or cloud SDKs.

## Boundary objects

The public ingestion SDK lives under `actionlineage.evidence` and is also
exported from the package root:

- `EvidenceRecord`: one idempotent source record that normalizes into one event.
- `NormalizedAction`: a transport-neutral action such as `file.read` or
  `http.send`.
- `NormalizedResource`: a resource touched by an action or observation.
- `ToolIdentity`: name, descriptor hash, adapter, and version evidence.
- `DelegatedIdentity`: initiating, executing, credential, and scope evidence.
- `ObservationRecord`: independently observed resource or environment evidence.
- `VerificationRecord`: evidence-link based verification evidence.
- `EvidenceSourceAdapter`: protocol for adapters that collect `EvidenceRecord`
  objects.

## Batch import

Use `import_evidence_batch()` to normalize, redact, and append records to the
canonical journal:

```python
from actionlineage import EvidenceRecord, EventType, import_evidence_batch

records = [
    EvidenceRecord(
        idempotency_key="run-1-intent",
        event_type=EventType.AGENT_INTENT_RECORDED,
        payload={"intent": "inspect workspace"},
        sort_key="000",
    )
]

result = import_evidence_batch(records, normalizer=normalizer, journal=journal)
```

Records are imported in deterministic order by `sort_key`, then
`idempotency_key`. The importer writes `payload.ingest.idempotency_key`,
`payload.ingest.source_kind`, and a versioned
`payload.ingest.record_fingerprint` so replayed batches can be detected against
an existing journal and same-key/different-record conflicts fail explicitly.

The journal remains the redaction boundary. Pass the desired redaction policy to
the journal before importing evidence.

## Idempotency and failure behavior

- Duplicate idempotency keys with the same fingerprint are skipped and reported
  as `duplicate`.
- Duplicate idempotency keys with a different fingerprint are reported as
  `conflict` and are not appended.
- Imported records return the persisted event ID.
- Import failures are reported per record with redacted error messages.
- A failed record does not silently become successful evidence.

Use `import_evidence_batch_atomically()` with `LocalJournal` when concurrent
service-style writers need the idempotency scan, sequence assignment, and append
to happen under one local journal lock. It still reports partial success per
record; it does not make a multi-record transaction or a production service
deployment claim.

## Adapter guidance

Adapters should implement `EvidenceSourceAdapter.collect()` and return
source-neutral records. Adapter code may depend on protocol or framework
libraries, but `domain`, `journal`, `projection`, and core ingestion models must
not import those optional dependencies.

Adapters should prefer metadata and digests over full content, and must not pass
raw passwords, private keys, bearer tokens, API keys, session cookies, or
authorization headers into payloads unless a redaction policy is already in
place and tested.
