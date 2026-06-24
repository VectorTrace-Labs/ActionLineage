# Security Hardening

This guide records release-grade security gates and resource bounds for public
ActionLineage releases.

## Executable Gates

Run these checks in CI and before release:

```bash
uv run python scripts/check_claims_language.py .
uv run python scripts/secret_scan.py .
uv run --all-extras python scripts/generate_sbom.py --output build/actionlineage-sbom.json
uv run --all-extras python scripts/check_dependency_licenses.py \
  --output build/actionlineage-license-report.json
uv run python scripts/generate_release_provenance.py \
  --dist-dir dist \
  --output build/actionlineage-release-provenance.json
uv run python scripts/check_release_consistency.py \
  --dist-dir dist \
  --output build/release-consistency-offline.json
uv run pip-audit
gh workflow run release.yml -f publish_target=none
```

The claim-language scan catches unsupported public claims. The secret scan is a
high-confidence repository guard and does not replace dedicated enterprise
secret scanning. The SBOM generator emits a lightweight JSON inventory from
`pyproject.toml` and installed package metadata. The dependency license check is
a local metadata allowlist/denylist gate for direct project dependencies; it is
review evidence, not legal advice. The release provenance generator emits a
local manifest with artifact hashes. The `release.yml` workflow builds release
artifacts in GitHub Actions, generates an offline release-consistency report,
and generates GitHub artifact attestations; package-index publication uses the
configured Trusted Publisher records described in `docs/PUBLISHING.md`.
The release-candidate manifest is generated from local artifact bytes and
evidence summaries. The release review index is generated from that manifest and
verifies listed artifact hashes; when release-consistency reports are
manifest-listed, the index summarizes their counts and non-passing checks. It is
a navigation aid for reviewers, not a signed attestation or publication event.

After the release-candidate artifact directory exists, generate the manifest and
reviewer index with explicit gate rows for the audit evidence you want listed:

```bash
uv run python scripts/write_release_candidate_manifest.py \
  --artifact-root build/release-candidate \
  --dist-dir build/release-candidate/dist \
  --gate "ruff_check|PASS|uv run ruff check ." \
  --output build/release-candidate/manifest.json
uv run python scripts/write_release_review_index.py \
  --manifest build/release-candidate/manifest.json \
  --output build/release-candidate/REVIEW_INDEX.md
```

## Resource Bounds

Default local bounds:

| Area | Bound | Enforcement |
| --- | --- | --- |
| String capture | 4096 characters | `RedactionPolicy.max_string_length` |
| Bytes capture | 4096 bytes | `RedactionPolicy.max_bytes_length` |
| Capture digest | scoped SHA-256 over redaction-boundary content | `actionlineage.capture.v1/redaction-boundary` digest scope |
| Sensitive field aliases | common token, cookie, cloud session, database URL, signed URL, webhook secret, and proxy authorization field names | `RedactionPolicy.sensitive_field_names` |
| Credential-bearing text | bearer tokens, key-value secret assignments, signed URL parameters, and common credential-bearing database URLs | `RedactionPolicy.patterns` |
| Observer fixture digests | caller-supplied strings with explicit fixture scopes | `actionlineage.observer.body-digest.v1`, `actionlineage.observer.signature-digest.v1` |
| JSON nesting depth | 64 levels | `validate_json_value`, `normalize_json`, `RedactionPolicy.max_json_depth` |
| JSON object members | 4096 members per object | `validate_json_value`, `normalize_json`, `RedactionPolicy.max_object_members` |
| JSON array items | 4096 items per array | `validate_json_value`, `normalize_json`, `RedactionPolicy.max_array_length` |
| Detection regex | bounded by rule parser and tests | `SequenceRule` validation |
| Journal append | one byte-canonical event plus `\n` per line | `LocalJournal.append`, `verify_journal` |
| Projection rebuild | verified journals only | `rebuild_projection` |
| Replay mutation | deterministic fixed seed | `Lineage Lab` replay API |
| Static console context file | 64 KiB | `load_console_context` |
| Static console notes | 50 items | `console_context_from_dict` |
| Static console saved views | 50 items | `console_context_from_dict` |

Large deployments should set tighter adapter-specific capture limits before
collecting production evidence.

## Adversarial Fixtures

Security regression fixtures live in `tests/fixtures/adversarial/` and cover:

- Prompt-injection causal chains.
- Descriptor drift.
- Malformed adapter payloads.
- Replayed approvals.
- Conflicting observer evidence.
- Oversized payloads.

Fixtures are intentionally local and deterministic. They do not require live
cloud credentials, model providers, or internet access.

Component-local security regressions also cover static console context
rendering: hostile note and saved-view fields are escaped, secret-like canaries
are redacted, and annotations remain non-canonical review metadata.

Journal append failure regressions cover preflight read failures and simulated
write failures such as disk-full or permission errors. These paths fail as
`JournalAppendError`, avoid echoing event payload canaries in the public error
message, and release the local sidecar lock.

## Supply Chain

- Keep core dependencies small and documented.
- Keep adapter dependencies behind optional extras.
- Run `pip-audit` for known third-party advisories.
- Generate an SBOM for release candidates.
- Generate a dependency license report and fail on unknown or denied direct
  dependency licenses.
- Generate a local release provenance manifest for built artifacts.
- Generate an offline release-consistency report for built artifacts.
- Generate a release-candidate manifest from the local artifact bundle.
- Generate a release proof review index from the local candidate manifest.
- Generate GitHub artifact attestations from the release workflow before
  describing release assets as attested.
- Review licenses before adding dependencies.
- Do not add generated SBOM files to source control unless they are intentional
  release artifacts.
