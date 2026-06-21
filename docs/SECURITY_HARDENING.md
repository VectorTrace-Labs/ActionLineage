# Security Hardening

This guide records release-grade security gates and resource bounds for public
ActionLineage releases.

## Executable Gates

Run these checks in CI and before release:

```bash
uv run python scripts/check_claims_language.py .
uv run python scripts/secret_scan.py .
uv run python scripts/generate_sbom.py --output build/actionlineage-sbom.json
uv run python scripts/generate_release_provenance.py \
  --dist-dir dist \
  --output build/actionlineage-release-provenance.json
uv run pip-audit
```

The claim-language scan catches unsupported public claims. The secret scan is a
high-confidence repository guard and does not replace dedicated enterprise
secret scanning. The SBOM generator emits a lightweight JSON inventory from
`pyproject.toml` and installed package metadata. The release provenance
generator emits an unsigned local manifest with artifact hashes; it does not
replace signed release artifacts or hosted attestations.

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
- Generate an unsigned local release provenance manifest for built artifacts.
- Review licenses before adding dependencies.
- Do not add generated SBOM files to source control unless they are intentional
  release artifacts.
