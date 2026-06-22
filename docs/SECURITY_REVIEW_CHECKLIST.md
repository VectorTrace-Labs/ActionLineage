# Security Review Checklist

Last reviewed: 2026-06-22.

Use this checklist for non-sensitive public review and maintainer-led release
review. It does not replace private vulnerability reporting. Sensitive findings
should follow `SECURITY.md`.

## Scope

Review the alpha-supported surfaces first:

- event envelope and schema compatibility;
- redaction boundary;
- local journal integrity and recovery;
- SQLite projection rebuild;
- contract validation;
- case, graph, incident, and static-console exports;
- deterministic demo evidence.

Preview surfaces such as service mode, MCP interception, cloud observers,
Postgres projection, Kubernetes, OpenTelemetry, and GHCR publication should be
reviewed as preview unless a future maturity update changes that label.

## Required Invariants

- Raw passwords, private keys, bearer tokens, API keys, session cookies, and
  authorization headers are not persisted.
- Redaction occurs before persistence, export, telemetry, logging, and error
  serialization.
- A denied call is not forwarded downstream.
- Policy failure is never silently converted to allow.
- Acknowledgement, observed, verified, unverified, timed-out, conflicting,
  unknown, and not-dispatched outcomes stay distinct.
- Model output is never the authoritative product pass or fail oracle.

## Review Areas

### Redaction And Privacy

- Check normal persistence, validation errors, exception text, logs, exports,
  dead-letter paths, and Agent Validation artifacts.
- Use synthetic canaries, not live secrets.
- Confirm static console, graph, case, and incident exports do not reintroduce
  sensitive values after redaction.

### Journal Integrity And Recovery

- Review append behavior, hash-chain verification, anchors, archive manifests,
  truncated records, malformed records, duplicate import, and projection rebuild.
- Confirm docs describe local trust assumptions without implying stronger
  guarantees than implemented.

### Correlation And Verification

- Look for simultaneous similar actions, retries, duplicate acknowledgements,
  reused identifiers, out-of-order observations, one-to-many effects, and
  conflicting timestamps.
- Confirm ambiguity is represented honestly rather than reduced to a confident
  match without evidence.

### Rendered Output Safety

- Check HTML escaping, Content Security Policy, link handling, hostile
  filenames, malicious event text, Unicode edge cases, oversized fields, and
  absence of automatic external-resource loading.

### Supply Chain

- Confirm runtime dependencies stay small and optional surfaces remain behind
  extras.
- Review workflow permissions, pinned actions, Trusted Publishing paths,
  artifact attestations, SBOM generation, dependency audit, and secret scanning.

### Service And Deployment Boundaries

- Treat service mode and deployment assets as preview.
- Do not infer tenant isolation, operational hardening, or production readiness
  unless those controls are implemented, tested, and documented.

## Local Commands

```bash
uv sync --locked --all-extras
uv run ruff check .
uv run ruff format --check .
uv run mypy src
uv run pytest
uv run pytest --cov=actionlineage --cov-branch --cov-report=term
uv run python scripts/check_claims_language.py .
uv run python scripts/secret_scan.py .
uv run pip-audit
```

Add focused tests for any finding before broadening the suite. Do not weaken an
invariant or maturity label to make a check pass.
