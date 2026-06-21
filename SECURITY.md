# Security Policy

## Supported Versions

Security fixes are applied to the latest public alpha release and to `main`.
Public compatibility guarantees are documented in `docs/COMPATIBILITY.md`.

## Reporting a Vulnerability

Report suspected vulnerabilities privately through GitHub private vulnerability
reporting or to the project owner before opening a public issue. Include:

- Affected version or commit.
- Reproduction steps or a minimized fixture.
- Whether secrets, credentials, journal integrity, redaction, policy behavior,
  or adapter execution are affected.
- Any evidence that a finding crosses from a disposable projection or export
  into the canonical journal.

Do not include live credentials or third-party private data in reports. Use
deterministic fixtures whenever possible.

## Security Boundaries

ActionLineage provides investigation-ready local evidence, redaction boundaries,
and deterministic integrity checks. It does not provide a hardened kernel,
remote attestation, universal prevention, or proof that an unobserved side
effect did not occur.

Core security invariants:

- Redaction occurs before persistence, export, telemetry, logging, and error
  serialization.
- The append-only journal is canonical local evidence.
- Projections, consoles, and telemetry exports are rebuildable or disposable.
- A tool acknowledgement is not side-effect verification.
- Policy enforcement is optional adapter behavior.

## Release Security Gates

Before a public alpha release, run:

```bash
uv run ruff check .
uv run ruff format --check .
uv run mypy src
uv run pytest
uv run python scripts/check_claims_language.py .
uv run python scripts/secret_scan.py .
uv run python scripts/generate_sbom.py --output build/actionlineage-sbom.json
uv run pip-audit
```

The public repository should also have GitHub code scanning, Dependabot alerts,
Dependabot security updates, secret scanning, push protection, and private
vulnerability reporting enabled.
