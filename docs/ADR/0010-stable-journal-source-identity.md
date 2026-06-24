# ADR-0010: Stable Journal Source Identity

- Status: Accepted
- Date: 2026-06-24
- Owners: Marq Mercado

## Context

SQLite and optional PostgreSQL projections are disposable query indexes rebuilt
from the append-only local journal. Projection reads require an explicit journal
path, but the previous projection source identity used a normalized local file
path. That made harmless journal moves look like source mismatches and made the
identity less useful as evidence metadata.

The local journal hash chain remains local tamper evidence. This decision must
not imply storage resistance against a fully privileged local rewrite, an
external trust root, or a durable journal UUID.

## Decision drivers

- Keep the append-only journal canonical.
- Keep projections rebuildable and disposable.
- Require callers to supply the journal path for trusted projection reads.
- Let byte-identical verified journals move without forcing a rebuild.
- Fail closed when a projection was built from different verified journal bytes.
- Avoid custom cryptography and avoid new production dependencies.

## Options considered

### Path-based source identity

Pros:

- Simple and reviewable.
- Detects accidental use of a different local path.

Cons:

- Fails after legitimate file moves.
- Does not identify the verified journal bytes.
- Encourages path metadata to carry more trust than it deserves.

### Random journal UUID

Pros:

- Stable across path moves.
- Easy to compare.

Cons:

- Requires a new persisted journal-side identifier or sidecar.
- Does not prove the indexed bytes match the supplied journal.
- Needs migration semantics for existing journals.

### Verified snapshot fingerprint

Pros:

- Uses already-verified local evidence.
- Binds the journal byte digest, verified record count, and terminal event hash.
- Survives path moves for byte-identical journals.
- Fails closed for changed journal contents.
- Requires no schema or event-format change.

Cons:

- Still local tamper evidence only; an attacker who can rewrite the journal and
  projection can recompute it.
- Legacy path-identity projections require rebuild before trusted reads.

## Decision

Use a namespaced `actionlineage.dev/journal-source-identity-v1` digest computed
over a deterministic JSON preimage containing:

- `version`
- `journal_sha256`
- `record_count`
- `terminal_hash`

Projection rebuilds store that digest as `source_journal_identity`, along with
the identity version and journal byte digest. The stored `source_journal_path`
remains audit metadata only. Projection reads still require an explicit journal
path; the supplied journal is verified, its source identity is recomputed, and
the projection fails closed if the identity, byte digest, record count, terminal
hash, or projected rows do not match.

Legacy `local-file:` projection identities are not upgraded in place. Trusted
reads report rebuild-required.

## Consequences

- A moved or copied byte-identical journal can be used with an existing
  projection when explicitly supplied by the caller.
- A different journal at the same path no longer passes because the content
  fingerprint changes.
- Existing path-identity projections must be rebuilt.
- The identity is not an external checkpoint, signature, WORM guarantee, or
  claim that local evidence resists a fully privileged rewrite.

## Verification

- SQLite projection tests cover moved byte-identical journal paths.
- SQLite projection tests cover changed source journal content.
- SQLite projection tests cover legacy path identity rebuild-required behavior.
- SQLite projection tests cover source byte-digest metadata tampering.
- PostgreSQL projection tests assert source identity metadata uses the stable
  journal source identity version.
