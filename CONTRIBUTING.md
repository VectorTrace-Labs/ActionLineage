# Contributing

## Before opening a pull request

- Read `AGENTS.md`, the charter, architecture, and threat model.
- Open or reference an issue for nontrivial behavior.
- Keep the change narrowly scoped.
- Add tests and documentation with behavior changes.
- Add an ADR for durable architecture, schema, integrity, or failure-semantics decisions.

## Development

```bash
uv sync --all-extras
uv run pre-commit install
uv run ruff check .
uv run ruff format --check .
uv run mypy src
uv run pytest
```

## Pull requests

Describe:

- Problem and solution.
- Security impact.
- Tests run.
- Public API/schema changes.
- Rollback or compatibility considerations.

Never include real incident data, credentials, internal tool schemas, proprietary code, or employer-confidential architecture.
