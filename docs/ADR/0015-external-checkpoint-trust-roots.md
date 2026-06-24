# ADR-0015: External Checkpoint Trust Roots

- Status: Proposed
- Date: 2026-06-24
- Owners: Marq Mercado

## Context

ActionLineage currently provides local journal hash chains, local anchors,
optional HMAC-signed anchors, local anchor logs, Git anchor statements, archive
manifests, and external-attestation sidecars. These artifacts bind local journal
bytes, record counts, terminal event hashes, and derived statements, but they do
not by themselves prove that an external service, protected key, WORM store,
timestamp authority, or transparency log enforced a trust root.

The public-alpha trust model must stay precise: local evidence is
tamper-evident relative to trusted roots supplied to verification, but it is not
resistant to an attacker who can rewrite all local artifacts and trusted values.
Stronger rollback, deletion, timestamp, or witness claims need a versioned
checkpoint trust-root model before code or marketing claims expand.

## Decision drivers

- Keep the append-only journal canonical.
- Avoid custom cryptographic primitives.
- Keep external trust roots optional and outside the domain core dependency
  graph.
- Require algorithm, key, witness, timestamp, and retention identifiers to be
  explicit and versioned.
- Preserve operation during external service outages without silently weakening
  local evidence.
- Make key rotation, revocation, replay, rollback, and verification failure
  semantics reviewable before implementation.

## Options considered

### Treat existing local anchors as external checkpoints

Pros:

- Already implemented and tested.
- No new schema or dependency.

Cons:

- Overstates local evidence. Local anchors are only as strong as the place the
  operator protects them.
- Does not identify external keys, transparency entries, object-lock state,
  timestamp authorities, or witnesses.

### Add one vendor-specific KMS or object-storage integration

Pros:

- Could produce useful production evidence quickly for one environment.

Cons:

- Pulls provider-specific trust assumptions into the public API too early.
- Does not generalize to HSMs, transparency logs, independent witnesses, or
  timestamp authorities.
- Risks making preview deployment artifacts look alpha-supported.

### Define a provider-neutral checkpoint declaration and verification contract

Pros:

- Keeps the trust-root contract explicit before adapters are implemented.
- Allows KMS/HSM, transparency log, trusted timestamp, WORM/object lock, Git,
  and independent witness integrations to share one evidence model.
- Keeps provider SDKs out of the domain core.

Cons:

- Requires a later implementation slice and external validation before stronger
  production claims are supported.

## Decision

Do not add a new external checkpoint implementation in this slice.

Future external checkpoint support must use a versioned provider-neutral
checkpoint declaration and verification result before any stronger trust-root
claim is made. The declaration must bind at least:

- Canonical journal identity: byte digest, verified record count, terminal event
  hash, canonicalization label, and source identity.
- Checkpoint scope: full journal, segment, append boundary, release artifact, or
  case bundle.
- Trust-root kind: KMS/HSM signature, trusted timestamp, transparency log,
  WORM/object-lock retention, independent witness, protected Git ref, or another
  explicitly reviewed kind.
- Trust-root identity: key ID, certificate or key digest, log ID, witness ID,
  object-store retention policy, Git remote/ref, timestamp authority, and
  verifier policy version where applicable.
- Statement bytes or statement digest, signature or inclusion-proof algorithm,
  creation time, claimed trusted time, expiration or retention horizon, and
  revocation status.
- Verification status, verification time, verifier identity/version, failure
  mode, and limitations.

The verifier contract must fail closed for mismatched journal bytes, stale or
wrong terminal hashes, unsupported algorithms, unknown trust-root kinds,
expired or revoked keys, missing inclusion proofs, retention-policy mismatch,
clock/timestamp ambiguity, and unavailable external services when a caller asks
for current external verification.

Outage behavior must be explicit. Local journal verification can still succeed
when an external verifier is unavailable, but the external checkpoint status
must be `unknown`, `stale`, or `unverified`; it must not be silently converted
to verified.

Implementation remains behind an ADR and executable tests. No provider SDK,
cloud account, HSM, timestamp authority, transparency log, or WORM storage
dependency belongs in the domain core.

## Consequences

- Existing anchors, archive manifests, Git statements, and external-attestation
  sidecars remain local or operator-supplied evidence.
- Public wording must not claim WORM enforcement, external timestamping,
  hardware-backed signing, transparency-log inclusion, or independent witnessing
  until implementations and verification tests exist.
- Future implementation can add provider adapters without changing the
  append-only event journal bytes.
- Release evidence and case bundles may reserve checkpoint fields, but a
  `null` or missing external checkpoint remains an explicit limitation.

## Verification

- Release-readiness tests require this ADR and public docs to keep local anchors
  separate from future external checkpoint trust roots.
- Existing anchor and archive tests continue to prove local binding behavior
  only.
- Future implementation tests must use deterministic fixtures for key rotation,
  revocation, inclusion proof mismatch, timestamp drift, WORM retention mismatch,
  witness disagreement, external-service outage, and rollback detection before
  external checkpoint support is described as alpha-supported.
