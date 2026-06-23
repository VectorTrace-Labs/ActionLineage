# Security Hardening

This guide records release-grade security gates and resource bounds for public
ActionLineage releases.

## Executable Gates

Run these checks in CI and before release:

```bash
uv run python scripts/check_claims_language.py .
uv run python scripts/secret_scan.py .
uv run python scripts/generate_sbom.py --output build/actionlineage-sbom.json
uv run python scripts/check_dependency_licenses.py \
  --output build/actionlineage-license-report.json
uv run python scripts/generate_release_provenance.py \
  --dist-dir dist \
  --output build/actionlineage-release-provenance.json
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
artifacts in GitHub Actions and generates GitHub artifact attestations;
package-index publication uses the configured Trusted Publisher records
described in `docs/PUBLISHING.md`.
The release review index is generated from local release-candidate manifest
evidence and verifies listed artifact hashes; it is a navigation aid for
reviewers, not a signed attestation or publication event.

After `build/release-candidate/manifest.json` exists, generate the reviewer
index with:

```bash
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
| Detection regex | bounded by rule parser and tests | `SequenceRule` validation |
| Journal append | one canonical event per line | `LocalJournal.append` |
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

## Supply Chain

- Keep core dependencies small and documented.
- Keep adapter dependencies behind optional extras.
- Run `pip-audit` for known third-party advisories.
- Generate an SBOM for release candidates.
- Generate a dependency license report and fail on unknown or denied direct
  dependency licenses.
- Generate a local release provenance manifest for built artifacts.
- Generate a release proof review index from the local candidate manifest.
- Generate GitHub artifact attestations from the release workflow before
  describing release assets as attested.
- Review licenses before adding dependencies.
- Do not add generated SBOM files to source control unless they are intentional
  release artifacts.
