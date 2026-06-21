from __future__ import annotations

from contextlib import asynccontextmanager
from types import SimpleNamespace
from typing import Any

import pytest

from actionlineage.adapters.mcp import (
    McpSdkClient,
    McpStdioClientConfig,
    McpStreamableHttpClientConfig,
    descriptor_from_sdk_tool,
    downstream_result_from_sdk_call_result,
)


def test_descriptor_from_sdk_tool_accepts_real_mcp_tool_shape() -> None:
    from mcp.types import Tool

    tool = Tool(
        name="safe_http.send",
        description="Send to the local receiver fixture",
        inputSchema={"type": "object", "properties": {"url": {"type": "string"}}},
        outputSchema={"type": "object"},
        _meta={"version": "1"},
    )

    descriptor = descriptor_from_sdk_tool(tool, server_identity="demo-server")

    assert descriptor.server_identity == "demo-server"
    assert descriptor.name == "safe_http.send"
    assert descriptor.input_schema["type"] == "object"
    assert descriptor.output_schema == {"type": "object"}
    assert descriptor.metadata == {"version": "1"}


def test_downstream_result_from_sdk_call_result_defaults_to_digest_only() -> None:
    from mcp.types import CallToolResult, TextContent

    result = CallToolResult(
        content=[TextContent(type="text", text="accepted")],
        structuredContent={"accepted": True},
        isError=False,
    )

    downstream = downstream_result_from_sdk_call_result(result)

    assert downstream.status == "succeeded"
    assert downstream.result_digest is not None
    assert downstream.result_payload is None


def test_downstream_result_from_sdk_call_result_can_include_sanitized_payload() -> None:
    result = SimpleNamespace(
        isError=True,
        structuredContent={"error": "blocked"},
        content=[{"type": "text", "text": "blocked"}],
    )

    downstream = downstream_result_from_sdk_call_result(result, include_payload=True)

    assert downstream.status == "failed"
    assert downstream.result_payload == {
        "content_item_count": 1,
        "content_types": ["text"],
        "is_error": True,
        "structured_content": {"error": "blocked"},
    }


@pytest.mark.asyncio
async def test_sdk_client_lists_tools_with_injected_session() -> None:
    session = _FakeMcpSession()

    client = McpSdkClient(
        config=McpStreamableHttpClientConfig(url="http://mcp.example.invalid/mcp"),
        server_identity="demo-server",
        session_opener=_fake_session_opener(session),
    )
    descriptors = await client.list_tools()

    assert session.initialized == 1
    assert [descriptor.name for descriptor in descriptors] == ["safe_http.send"]
    assert descriptors[0].server_identity == "demo-server"


@pytest.mark.asyncio
async def test_sdk_client_calls_tool_with_injected_stdio_session() -> None:
    session = _FakeMcpSession()
    client = McpSdkClient(
        config=McpStdioClientConfig(command="demo-mcp"),
        server_identity="demo-server",
        session_opener=_fake_session_opener(session),
    )
    descriptor = descriptor_from_sdk_tool(session.tool, server_identity="demo-server")

    downstream = await client.call_tool(descriptor, {"url": "https://example.invalid"})

    assert session.calls == [("safe_http.send", {"url": "https://example.invalid"})]
    assert downstream.status == "succeeded"
    assert downstream.result_digest is not None
    assert downstream.result_payload is None


class _FakeMcpSession:
    def __init__(self) -> None:
        self.initialized = 0
        self.calls: list[tuple[str, dict[str, Any] | None]] = []
        self.tool = SimpleNamespace(
            name="safe_http.send",
            description="Send to the local receiver fixture",
            inputSchema={"type": "object", "properties": {"url": {"type": "string"}}},
            outputSchema=None,
            annotations=None,
            meta={"fixture": True},
        )

    async def initialize(self) -> object:
        self.initialized += 1
        return SimpleNamespace()

    async def list_tools(self) -> object:
        return SimpleNamespace(tools=[self.tool])

    async def call_tool(self, name: str, arguments: dict[str, Any] | None = None) -> object:
        self.calls.append((name, arguments))
        return SimpleNamespace(
            isError=False,
            structuredContent={"accepted": True},
            content=[{"type": "text", "text": "accepted"}],
        )


def _fake_session_opener(session: _FakeMcpSession):
    @asynccontextmanager
    async def _opener(config):
        yield session

    return _opener
