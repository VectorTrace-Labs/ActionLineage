# ADR-0013: Canonicalization V1 Conformance Boundary

- Status: Proposed
- Date: 2026-06-24
- Owners: Marq Mercado

## Context

ADR-0001 defines `actionlineage.dev/json-deterministic-v0` as the current
domain serialization and redaction boundary. ADR-0002 uses those deterministic
bytes as the local journal hash input and requires each journal line to match
the writer's canonical bytes exactly.

That local boundary is now tested against semantic rewrites: reordered keys,
added whitespace, CRLF line endings, duplicate JSON keys, invalid UTF-8,
trailing JSON, multiple JSON values, and non-finite numeric tokens fail before
records are accepted into a verified snapshot.

The remaining gap is portability. Python's deterministic `json.dumps` behavior
is adequate for the current public-alpha writer and verifier, but it is not a
formal cross-language canonical JSON standard. Stronger claims about portable
hash input, descriptor hashes, signed records, external witnesses, or
multi-language producers require a versioned canonicalization contract with
conformance vectors.

## Decision drivers

- Preserve readability of existing `actionlineage.dev/v1alpha1` journals.
- Avoid changing local journal hash input without a migration ADR and fixtures.
- Avoid claiming RFC 8785/JCS or another standard before executable
  conformance evidence exists.
- Keep duplicate-key, non-finite-number, timestamp, escaping, and Unicode edge
  cases fail-closed and reviewable.
- Keep descriptor hashing, event hashing, release evidence, and future
  signatures aligned on named algorithm identifiers.
- Avoid adding a production dependency until standard-library behavior or a
  small audited implementation is proven insufficient.

## Options considered

### Keep `json-deterministic-v0` indefinitely

Pros:

- Already implemented and covered by current local journal tests.
- Does not alter existing event bytes or hash chains.
- Requires no new dependency.

Cons:

- It remains a project-local convention, not a portable canonical JSON
  standard.
- Other language implementations could disagree on number rendering, Unicode
  escaping, string normalization assumptions, or timestamp formatting.
- It limits future external signing and witness claims.

### Switch immediately to RFC 8785/JCS-style canonical JSON

Pros:

- Aligns with a published canonical JSON scheme.
- Better fit for multi-language producers and external verification.

Cons:

- Would change journal hash input and stored `integrity.canonicalization`
  values.
- Needs explicit migration behavior for existing `json-deterministic-v0`
  journals.
- Requires conformance vectors for numbers, strings, Unicode, escaping, and
  object-member ordering before it can protect evidence rather than merely
  look standard-compliant.
- May require a dependency or local implementation review.

### Define the v1 conformance boundary before adoption

Pros:

- Preserves existing public-alpha journals and tests.
- Makes the future standardization path explicit.
- Gives reviewers a concrete acceptance bar before stronger portability,
  external-signature, or multi-language claims.
- Lets implementation choose standard-library-only, audited local code, or a
  dependency only after vectors expose the real gaps.

Cons:

- Leaves `json-deterministic-v0` as the active journal format for now.
- Requires one more implementation slice before a v1 canonicalization label can
  be used in event hashes.

## Decision

Do not replace `actionlineage.dev/json-deterministic-v0` in this slice.

Define `actionlineage.dev/json-canonicalization-v1` as a planned
canonicalization boundary that may be adopted only after executable conformance
vectors and migration rules exist. The v1 implementation must either conform to
a reviewed standard such as RFC 8785/JCS or document every intentional
difference in a follow-up ADR.

Before any event, descriptor, checkpoint, release-evidence, or signature path
uses the v1 label, the repository must include conformance vectors covering at
least:

- Object member ordering, including nested objects and escaped member names.
- Duplicate object-key rejection before canonicalization.
- Unicode string preservation, escape handling, and control characters.
- Integer and decimal number rendering, including zero, negative zero
  handling, exponent forms, leading zeros, precision limits, and unsafe integer
  ranges.
- Rejection of `NaN`, `Infinity`, and `-Infinity` before persistence or hash
  input.
- Boolean and null values.
- Array ordering and nested mixed values.
- UTC timestamp representation used by the event model.
- UTF-8 output bytes with no byte order mark.
- Golden event, descriptor, and evidence-link examples with expected bytes and
  SHA-256 digests.

Adopting v1 for persisted events requires a migration ADR that answers:

- Whether the event schema changes from `v1alpha1`.
- Whether old `json-deterministic-v0` journals remain readable and verifiable.
- Whether mixed-canonicalization journals are allowed or rejected.
- How projections, anchors, archive manifests, external attestation sidecars,
  release evidence, descriptor hashes, and compatibility fixtures identify the
  algorithm used for each digest.
- How failed conformance or unsupported numeric values fail closed.

Until that work is complete, public wording may say local journals are
byte-canonical under `json-deterministic-v0`. It must not claim portable
cross-language canonical JSON, RFC 8785/JCS conformance, or stable
multi-language hash equivalence.

## Consequences

- Current public-alpha journal bytes and golden fixtures remain unchanged.
- Existing tests remain evidence for local deterministic verification, not for
  portable canonical JSON.
- Future canonicalization work starts with vectors and migration behavior before
  code changes to hash inputs.
- Any new dependency for canonicalization must go through the dependency policy
  with license, maintenance, security, and trusted-computing-base review.
- Descriptor hash and journal hash documentation must name which
  canonicalization label they use.

## Verification

- Release-readiness tests require this ADR and the public docs to keep
  `json-deterministic-v0` and planned v1 claims distinct.
- Existing journal tests continue to prove byte-canonical local verification for
  `json-deterministic-v0` records.
- Future v1 implementation tests must load checked-in conformance vectors and
  verify exact canonical bytes plus SHA-256 digests before v1 is used for
  persisted evidence.
