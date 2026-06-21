# ADR-0004: Journal Anchors and Recovery

- Status: Accepted
- Date: 2026-06-21
- Owners: Marq Mercado

## Context

The local append-only journal is canonical evidence, but a local hash chain alone
cannot detect tail truncation or full rewrite unless a trusted record count or
last event hash exists outside the journal bytes being verified.

The 1.0 roadmap requires local anchoring, segment manifests, recovery helpers,
and precise integrity claims without introducing custom cryptography.

## Decision

Add `actionlineage.dev/journal-anchor-v1` anchors containing the journal path,
verified record count, last event hash, and creation time.

Add `actionlineage.dev/journal-segment-manifest-v1` manifests that wrap an
anchor for one journal segment. A single-segment manifest is sufficient for the
local 1.0 evidence path and leaves room for multi-segment archives later.

Add `actionlineage.dev/journal-anchor-log-v1` as a local append-only sidecar for
trusted anchors. Each log entry records the anchor, sequence, previous entry
hash, entry hash, and creation time. This provides transparency-log-style local
append evidence without changing canonical journal event bytes.

Add `actionlineage.dev/git-anchor-statement-v1` as a deterministic sidecar that
records an anchor file hash, repo-relative anchor path, Git ref, resolved commit,
and creation time. ActionLineage verifies that the anchor bytes match both the
local anchor file and the anchor blob stored in the recorded commit. It can also
verify that a caller-supplied ref still resolves to the recorded commit.

Add `actionlineage.dev/journal-archive-manifest-v1` as a local sidecar for
object-storage workflows. It records journal byte hash, size, verified record
count, last event hash, intended object URI, storage class, retention mode, and
creation time. Verification checks local bytes and trusted tail values only.

Use standard-library HMAC-SHA256 as an optional anchor signature over
deterministic anchor JSON with `signature` set to `null`. Signing keys are
caller-provided bytes and are never persisted by ActionLineage.

Add recovery helpers that locate the first verification issue and export the
verified prefix before that issue. Recovery never repairs or rewrites the
canonical journal in place.

## Consequences

- Anchors can detect tail truncation and full rewrites when the anchor is kept in
  a trusted location.
- Unsigned local anchors remain vulnerable to an attacker who can rewrite both
  the journal and anchor.
- HMAC-signed anchors depend on protecting the signing key outside
  ActionLineage.
- Local anchor logs improve append history checks but are still vulnerable to an
  attacker who can rewrite the journal, anchors, anchor log, and trusted tail
  values together.
- Git anchor statements do not mutate repositories or publish anchors. Their
  assurance depends on external Git controls such as protected refs, signed
  releases, or independent replication.
- Archive manifests do not upload objects or prove WORM/object-lock enforcement.
  Their assurance depends on deployment-controlled storage and retention
  configuration.
- Segment manifests do not alter journal event bytes and therefore preserve
  `v1alpha1` journal readability.
- Recovery outputs are new files; the original journal remains untouched.

## Verification

- Tests cover successful anchor verification, tail truncation detection,
  signature key missing, signature mismatch, anchor-log append and tamper
  detection, Git anchor statement creation and drift detection, archive manifest
  byte verification, segment manifest round trip, corrupt record location,
  verified-prefix export, and CLI anchor commands.
