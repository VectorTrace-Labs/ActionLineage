# Tools and Primary Resources

Review current versions before implementation. Prefer specifications and official documentation over blog posts.

## Codex workflow

- Codex documentation: https://developers.openai.com/codex
- Prompting: https://developers.openai.com/codex/prompting
- AGENTS.md behavior: https://developers.openai.com/codex/guides/agents-md
- Sandboxing: https://developers.openai.com/codex/concepts/sandboxing
- Worktrees: https://developers.openai.com/codex/app/worktrees
- Sample configuration: https://developers.openai.com/codex/config-sample

## Agent and tool protocols

- Model Context Protocol specification: https://modelcontextprotocol.io/specification/latest
- MCP security best practices: https://modelcontextprotocol.io/docs/tutorials/security/security_best_practices
- Official MCP Python SDK: https://github.com/modelcontextprotocol/python-sdk
- MCP Inspector: https://github.com/modelcontextprotocol/inspector
- JSON-RPC 2.0: https://www.jsonrpc.org/specification

## Telemetry and schemas

- OpenTelemetry: https://opentelemetry.io/docs/
- OpenTelemetry Python: https://opentelemetry.io/docs/languages/python/
- OpenTelemetry GenAI semantic conventions: https://github.com/open-telemetry/semantic-conventions/tree/main/docs/gen-ai
- OCSF schema: https://github.com/ocsf/ocsf-schema

## Policy and testing

- Open Policy Agent: https://www.openpolicyagent.org/docs
- Hypothesis: https://hypothesis.readthedocs.io/
- Pytest: https://docs.pytest.org/
- Pydantic: https://docs.pydantic.dev/
- FastAPI: https://fastapi.tiangolo.com/
- uv: https://docs.astral.sh/uv/
- Ruff: https://docs.astral.sh/ruff/
- mypy: https://mypy.readthedocs.io/

## Security references

- MCP security best practices: https://modelcontextprotocol.io/docs/tutorials/security/security_best_practices
- OWASP GenAI Security Project: https://genai.owasp.org/
- MITRE ATLAS: https://atlas.mitre.org/
- MITRE ATT&CK: https://attack.mitre.org/
- OWASP SSRF Prevention Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Server_Side_Request_Forgery_Prevention_Cheat_Sheet.html
- RFC 8785 JSON Canonicalization Scheme: https://www.rfc-editor.org/rfc/rfc8785

## Optional infrastructure

- Jaeger: https://www.jaegertracing.io/docs/
- PostgreSQL: https://www.postgresql.org/docs/
- Cytoscape.js: https://js.cytoscape.org/

## Suggested local tools

- Docker or Podman with Compose support.
- `git`, `uv`, Python 3.12+, and `make`.
- `gitleaks` or an equivalent secret scanner.
- `pip-audit` for Python dependency advisories.
- MCP Inspector for protocol debugging.
- Jaeger for trace visualization when using the optional OpenTelemetry exporter.
