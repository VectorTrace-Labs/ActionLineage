# Journal Integrity, Anchors, and Recovery

## Local hash chain

Every persisted journal event includes:

- `integrity.previous_event_hash`
- `integrity.event_hash`
- `integrity.canonicalization`

Verification recomputes each event hash over canonical event bytes with
`event_hash` set to `null`, then checks that each record links to the prior
record hash.

Journal verification is byte-canonical. Every stored record must be exactly the
deterministic serialized event bytes followed by one `\n`. Formatting-only
rewrites such as reordered keys, added whitespace, `\r\n` line endings, trailing
bytes, or multiple JSON values on one line fail verification as
`noncanonical_record` or `parse_error`. Duplicate JSON object keys, invalid
UTF-8, and non-finite numeric tokens are rejected during parsing before a record
can become verified evidence.

This is tamper-evident relative to the journal bytes and any trusted anchor. It
is not tamper-proof, forensically complete, or resistant to an attacker who can
rewrite both the journal and all trusted anchors.

## Append durability and incomplete records

The local writer serializes append attempts with a kernel-backed advisory lock
on a stable sidecar lock file, verifies the existing journal before writing,
requires the incoming
`causality.sequence` to equal the next record index, writes one canonical JSON
record plus a newline terminator, flushes, and calls `fsync()` on the journal
file.

If the journal directory cannot be prepared, the existing journal cannot be
read for preflight verification, or the append write/flush/fsync operation
raises an operating-system I/O error such as a permission or disk-space failure,
append fails with `JournalAppendError`. The public error message is bounded and
does not include event payload data. The local sidecar lock is released on these
failure paths.

A journal record is complete only when the newline terminator is present. If an
append is interrupted after partial bytes are visible but before the terminator,
verification reports `truncated_record` at that record and stops at the prior
verified prefix. ActionLineage does not repair or truncate the source journal in
place; use verified-prefix export to copy the records that verified before the
first issue.

The lock file stores non-secret owner metadata while held, including PID,
hostname, process-start identity, acquisition time, application version, and
operation name. The file itself is not an ownership sentinel; process
termination releases the advisory lock without requiring manual deletion. A
malformed or foreign-host metadata record is not deleted based on unsafe
guesswork.

The lock is a local advisory lock, not a distributed lock. Filesystems, network
mounts, container volumes, or backup tools that do not honor local advisory lock
semantics need deployment-specific controls before relying on concurrent
writers.

Verified snapshots read and verify from one open file descriptor while holding
a shared journal lock. They return the immutable event tuple captured during
that verification pass and record verification status, verified count, terminal
hash, and failure details. Security-sensitive consumers should use verified
snapshots rather than raw parsing helpers.

## Trusted anchors

Use `create_journal_anchor()` or the CLI to capture a trusted root:

```bash
uv run actionlineage journal create-anchor evidence.jsonl evidence.anchor.json
uv run actionlineage journal verify-anchor evidence.jsonl evidence.anchor.json
```

An anchor records the verified record count and last event hash. Verification
with an anchor detects tail truncation and full rewrites that would otherwise
produce a self-consistent local chain.

## Optional HMAC signatures

The Python API can create HMAC-SHA256 signed anchors by passing a `signing_key`.
The key is never persisted. Signed anchor verification requires the same trusted
key.

The CLI accepts signing keys only through a file path so the secret is not placed
directly in shell arguments:

```bash
printf '%s' "$ACTIONLINEAGE_ANCHOR_KEY" > anchor.key
uv run actionlineage journal create-anchor evidence.jsonl evidence.anchor.json \
  --signing-key-file anchor.key
uv run actionlineage journal verify-anchor evidence.jsonl evidence.anchor.json \
  --signing-key-file anchor.key
```

Protect the key file outside ActionLineage. The anchor records only the
signature algorithm and signature, never the key bytes.

## Local anchor log

For teams that want a simple append target before introducing external anchor
infrastructure, append trusted anchors to a local anchor log:

```bash
uv run actionlineage journal append-anchor-log evidence.anchor.json anchors.log
uv run actionlineage journal verify-anchor-log anchors.log
```

Each anchor-log record has its own `previous_entry_hash` and `entry_hash`, so
middle-record mutation, deletion, duplication, and reorder are detectable during
log verification. Tail truncation still requires a trusted expected record count
or last entry hash:

```bash
uv run actionlineage journal verify-anchor-log anchors.log \
  --expected-record-count 3 \
  --expected-last-entry-hash sha256:...
```

This is still local evidence. It is not a public transparency log and does not
protect against an attacker who can rewrite the journal, anchors, anchor log,
and trusted expected values together.

## Git anchor statements

For teams that already protect release repositories or signed refs, a Git anchor
statement can tie an anchor file to bytes committed in a Git object:

```bash
uv run actionlineage journal create-anchor evidence.jsonl evidence.anchor.json
git add evidence.anchor.json
git commit -m "Anchor ActionLineage journal"
uv run actionlineage journal create-git-anchor-statement \
  evidence.anchor.json evidence.anchor.git.json \
  --repo . \
  --ref HEAD
uv run actionlineage journal verify-git-anchor-statement \
  evidence.anchor.json evidence.anchor.git.json \
  --repo . \
  --ref HEAD
```

The statement records the anchor file hash, the repo-relative anchor path, the
Git ref requested at creation time, and the resolved commit. Verification checks
the current anchor bytes, the anchor blob stored in the recorded commit, and,
when `--ref` is provided, that the ref still resolves to the recorded commit.

ActionLineage does not create commits, tags, notes, or pushes. A Git statement is
only as strong as the external controls protecting the repository, ref, and
statement artifact.

## External attestation sidecars

For teams using a hardware key, timestamp authority, remote attestation service,
or transparency-log-style append target outside ActionLineage, create a sidecar
that binds trusted anchor bytes to the external statement digest:

```bash
uv run actionlineage journal create-external-attestation \
  evidence.anchor.json evidence.attestation.json \
  --statement-file statement.bin \
  --attester reviewed-hsm \
  --attestation-type hardware_key \
  --statement-reference hsm://cluster/key/statement/1
uv run actionlineage journal verify-external-attestation \
  evidence.anchor.json evidence.attestation.json \
  --statement-file statement.bin
```

Verification checks that the sidecar still matches the local anchor bytes and,
when a statement file is provided, that the statement digest matches the sidecar.
ActionLineage does not implement hardware-backed signing, remote attestation
protocols, or external transparency-log verification. Those controls remain in
the external system; the sidecar records the relationship for investigation and
release review.

## Archive manifests

For object-storage workflows, create a local archive manifest before or after a
separate upload process:

```bash
uv run actionlineage journal create-archive-manifest \
  evidence.jsonl evidence.archive.json \
  --object-uri s3://evidence-bucket/evidence.jsonl \
  --retention-mode governance
uv run actionlineage journal verify-archive-manifest evidence.archive.json
```

The manifest records the journal byte hash, size, verified record count, last
event hash, intended object URI, storage-class label, and retention-mode label.
Verification checks local journal bytes and trusted tail values. ActionLineage
does not upload the journal, configure bucket policy, or prove object-lock
enforcement; those controls belong to the deployment environment.

## Segment manifests

`JournalSegmentManifest` wraps a trusted anchor for one segment. The current
local implementation uses one segment per journal; future archive tooling can
create multiple segment manifests without changing event bytes.

## Append indexes and checkpoints

ADR-0011 keeps append indexes out of the trusted public-alpha service path. A
future append index may speed up idempotency lookup or replay planning, but it
must be treated as a rebuildable cache bound back to a verified journal source
identity, byte digest, record count, and terminal hash. A stale or mismatched
index must be ignored or rebuilt rather than trusted.

Authenticated append checkpoints should use the existing anchor, optional HMAC,
anchor-log, Git statement, archive manifest, or external-attestation sidecar
model unless a future ADR changes that boundary. Local checkpoints do not make
the journal resistant to an attacker who can rewrite every local artifact and
trusted value.

## Recovery

Use verified-prefix export when a journal fails verification:

```bash
uv run actionlineage journal export-verified-prefix evidence.jsonl verified-prefix.jsonl
```

The command writes records verified before the first detected issue. It does not
modify, repair, truncate, or delete the original journal. The output path must
be different from the source journal path; in-place recovery is rejected before
any output file is opened.

## Retention

Canonical journals should be retained or archived explicitly. Projection
databases are disposable and may be deleted, compacted, or rebuilt from verified
journals. Do not silently compact canonical journals.
