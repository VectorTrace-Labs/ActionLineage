# ADR-0002: Local Journal Hash Chain

- Status: Accepted
- Date: 2026-06-21
- Owners: Marq Mercado

## Context

Prompt 03 introduces the first local evidence journal. The journal needs
deterministic integrity verification for mutation, insertion, deletion,
duplication, reordering, and concurrent append behavior. Digital signatures,
hardware-backed anchoring, query projection, and network storage are out of
scope.

ADR-0001 defines the current deterministic JSON serialization and redaction
boundary. The journal needs a concrete hash input that avoids recursive
`event_hash` calculation while binding the previous hash into each record.

## Decision drivers

- Security
- Correctness
- Auditability
- Deterministic tests
- No new production dependency

## Options considered

### Hash the persisted event with `event_hash` set to null

Before append, the event is redacted and canonicalized. The journal computes
SHA-256 over the canonical persisted event with `integrity.event_hash` set to
`null` and `integrity.previous_event_hash` set to the prior record's hash. The
event is then written with both integrity fields populated.

Pros:

- Avoids recursive hashes.
- Binds all non-`event_hash` fields into the digest.
- Keeps redaction before hashing and persistence.
- Can be verified from the local journal alone for in-file mutations and
  reordering.

Cons:

- Tail truncation needs a trusted expected record count or last hash.
- A local attacker who can rewrite all bytes and anchors can build a new valid
  chain.

### Hash only payload and selected metadata

Pros:

- Smaller hash input.

Cons:

- Easier to accidentally omit security-relevant fields.
- Does not satisfy the event-envelope integrity expectation.

## Decision

Use the persisted redacted event with `integrity.event_hash` set to `null` as the
event hash input. Include `integrity.previous_event_hash` in the hash input. Use
SHA-256 and store hashes as `sha256:<hex>`.

The local journal writer uses a sidecar lock file and append/fsync writes. It
requires each event's `causality.sequence` to equal the next journal record
index. Concurrent attempts with stale or duplicate sequence numbers fail visibly.

Verification reports a machine-readable result containing `ok`,
`records_verified`, `last_event_hash`, and structured issues. Verification can
optionally compare a trusted expected record count and trusted last hash.

## Consequences

- Valid journals verify deterministically across runs.
- Mutation, insertion, middle deletion, duplication, and reordering fail
  verification.
- Tail deletion is only detectable when the verifier receives a trusted expected
  record count or last hash.
- The local hash chain must not be described as tamper-proof.
- Future signature or external anchoring work can reuse `last_event_hash` as an
  anchor value without changing the local journal record format.

## Verification

- `AT-JRN-001` covers successful verification of a valid journal.
- `AT-JRN-002` covers mutation detection at the affected record.
- `AT-JRN-003` covers deletion, insertion, duplication, and reordering.
- `AT-JRN-005` covers concurrent append behavior by requiring deterministic
  sequence order or visible failure.
