# MCP Adapter Boundary

MCP support lives under `actionlineage.adapters.mcp`. It is an optional adapter
surface and must not be imported by the domain core, journal, projection, or
core CLI logic.

## Implemented Boundary

- Canonical MCP tool descriptors.
- Stable descriptor hashes.
- Neutral tool identity payloads.
- Descriptor drift payloads for `agent.tool.schema_changed`.
- Dependency-free execution plans for Streamable HTTP and stdio adapters.
- Dependency-free proxy executor that records lifecycle events and calls a
  supplied downstream function only after policy permits dispatch.
- Acknowledgement payloads that explicitly keep side effects `unverified`.
- Lazy optional MCP SDK client bridge for Streamable HTTP and stdio transports.
- SDK tool/result conversion that records descriptor identity and sanitized
  acknowledgement summaries without persisting raw tool arguments.

The concrete MCP SDK transport remains behind optional extras and is imported
only by `actionlineage.adapters.mcp.sdk` when a transport session is opened. The
core runtime maps adapter decisions into neutral lifecycle payloads and provides
a transport-agnostic executor.

## Optional SDK Client

Install the adapter extra when using the SDK bridge:

```bash
pip install 'actionlineage[adapters]'
```

Use `McpSdkClient` to list tools and call a downstream MCP transport:

```python
from actionlineage.adapters.mcp import (
    McpSdkClient,
    McpStreamableHttpClientConfig,
)

client = McpSdkClient(
    config=McpStreamableHttpClientConfig(url="http://localhost:8000/mcp"),
    server_identity="local-demo-server",
)
descriptors = await client.list_tools()
result = await client.call_tool(descriptors[0], {"path": "demo.txt"})
```

`call_tool()` returns `McpDownstreamResult` with a digest by default. Set
`include_result_payload=True` only when the downstream payload is already safe to
persist after the caller's redaction boundary. Tool acknowledgement still does
not prove any side effect occurred.

## Lifecycle Mapping

`plan_mcp_tool_execution()` produces payloads for:

- `tool.execution.requested`
- `policy.decision`
- `tool.execution.authorized`
- `tool.execution.dispatched`
- `tool.execution.not_dispatched`
- `recorder.degraded`

Denied calls and rejected approvals produce `tool.execution.not_dispatched` with
`downstream_forwarded=false`.

Tool acknowledgements are produced with `acknowledgement_payload()`. An
acknowledgement is never side-effect verification; observer or verification
adapters must emit separate side-effect evidence.

`execute_mcp_tool_call()` records the requested, policy, authorization,
dispatch, not-dispatched, and acknowledgement events into a caller-supplied
journal. It passes raw arguments only to the supplied downstream callable and
persists the argument digest rather than raw arguments.

## Descriptor Drift

`descriptor_drift_payload(previous, current)` records previous and current
descriptor hashes. Consumers can alert on drift before sensitive actions without
treating drift as a policy decision.
