# Copilot Review Instructions

ActionLineage is a public-alpha, vendor-neutral evidence and detection plane for
tool-using agents. Reviews should prioritize correctness, auditability, clear
security boundaries, and truthful release claims.

When reviewing pull requests:

- Treat Copilot review as advisory. Do not imply that an AI review approves,
  authorizes, or replaces maintainer judgment.
- Verify that the domain core remains independent of MCP, OpenTelemetry,
  model-provider SDKs, FastAPI, and cloud SDKs.
- Check that a successful tool response is not treated as proof that a side
  effect occurred.
- Preserve separate requested, authorized, dispatched, acknowledged, observed,
  verified, unverified, timed-out, conflicting, and not-dispatched outcomes.
- Require explicit corroborating evidence before code or docs call an outcome
  verified.
- Watch for proof-of-absence wording. Missing observations must be described as
  missing observations only.
- Check redaction boundaries before persistence, tracing, logging, exporting,
  and error serialization. Do not allow raw secrets, authorization headers,
  session cookies, bearer tokens, private keys, API keys, or passwords to be
  persisted.
- Preserve `actionlineage.dev/v1alpha1` journal readability and compatibility
  unless an accepted ADR documents a migration.
- Keep policy enforcement, MCP, OpenTelemetry, service mode, exporters, cloud
  observers, and deployment surfaces optional or preview unless the maturity
  docs say otherwise.
- Reject public claims that are not tied to implementation, tests, demo
  evidence, external validation, or an explicit maturity label.
- For release or packaging changes, check the release workflow, publishing
  docs, maturity docs, and package-manager docs together.
- For security-sensitive changes, look for positive, denied, malformed-input,
  timeout/failure, redaction-leakage, replay/idempotency, ordering, and
  compatibility tests as applicable.

Expected local verification for Python changes:

```bash
uv run ruff check .
uv run ruff format --check .
uv run mypy src
uv run pytest
```

For dependency changes, also expect:

```bash
uv lock
uv run pip-audit
```
