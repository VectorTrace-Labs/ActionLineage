"""Optional MCP SDK client bridge.

This module is intentionally confined to the adapter package. It lazily imports
the MCP SDK only when a concrete transport is opened, so domain, journal,
projection, and core CLI code stay independent of MCP.
"""

from __future__ import annotations

import hashlib
from collections.abc import AsyncIterator, Callable
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from dataclasses import dataclass
from typing import Any, Protocol

from actionlineage.adapters.mcp.descriptors import McpToolDescriptor
from actionlineage.adapters.mcp.runtime import McpDownstreamResult
from actionlineage.domain import deterministic_json_bytes
from actionlineage.domain.events import JsonObject, JsonValue, validate_json_value


class McpSdkUnavailable(RuntimeError):
    """Raised when the optional MCP SDK is not installed."""


@dataclass(frozen=True, slots=True)
class McpStreamableHttpClientConfig:
    """Configuration for the optional MCP Streamable HTTP client."""

    url: str
    headers: dict[str, str] | None = None
    timeout_seconds: float = 30.0
    sse_read_timeout_seconds: float = 300.0


@dataclass(frozen=True, slots=True)
class McpStdioClientConfig:
    """Configuration for the optional MCP stdio client."""

    command: str
    args: tuple[str, ...] = ()
    env: dict[str, str] | None = None
    cwd: str | None = None


type McpSdkTransportConfig = McpStreamableHttpClientConfig | McpStdioClientConfig


class McpSdkSession(Protocol):
    """Subset of MCP `ClientSession` used by ActionLineage."""

    async def initialize(self) -> object:
        """Initialize the MCP session."""

    async def list_tools(self) -> object:
        """Return an SDK list-tools result object."""

    async def call_tool(self, name: str, arguments: dict[str, Any] | None = None) -> object:
        """Call one MCP tool and return an SDK call result object."""


type McpSdkSessionOpener = Callable[
    [McpSdkTransportConfig],
    AbstractAsyncContextManager[McpSdkSession],
]


@dataclass(frozen=True, slots=True)
class McpSdkClient:
    """Thin optional SDK bridge that returns ActionLineage adapter objects."""

    config: McpSdkTransportConfig
    server_identity: str
    session_opener: McpSdkSessionOpener | None = None

    async def list_tools(self) -> tuple[McpToolDescriptor, ...]:
        """List downstream tools as canonical ActionLineage descriptors."""

        async with self._session_opener()(self.config) as session:
            await session.initialize()
            result = await session.list_tools()
            tools = getattr(result, "tools", None)
            if not isinstance(tools, list):
                raise ValueError("MCP list_tools result must expose a tools list")
            return tuple(
                descriptor_from_sdk_tool(tool, server_identity=self.server_identity)
                for tool in tools
            )

    async def call_tool(
        self,
        descriptor: McpToolDescriptor,
        arguments: JsonObject,
        *,
        include_result_payload: bool = False,
    ) -> McpDownstreamResult:
        """Call a downstream MCP tool and return a sanitized acknowledgement summary."""

        validate_json_value(arguments)
        async with self._session_opener()(self.config) as session:
            await session.initialize()
            result = await session.call_tool(descriptor.name, dict(arguments))
            return downstream_result_from_sdk_call_result(
                result,
                include_payload=include_result_payload,
            )

    def _session_opener(self) -> McpSdkSessionOpener:
        return self.session_opener or _open_sdk_session


def descriptor_from_sdk_tool(tool: object, *, server_identity: str) -> McpToolDescriptor:
    """Convert an MCP SDK tool object into a canonical descriptor."""

    name = _required_string_attribute(tool, "name")
    description = _optional_string_attribute(tool, "description") or ""
    input_schema = _required_json_object_attribute(tool, "inputSchema")
    output_schema = _optional_json_object_attribute(tool, "outputSchema")
    annotations = _optional_json_object_attribute(tool, "annotations") or {}
    metadata = _optional_json_object_attribute(tool, "_meta")
    if metadata is None:
        metadata = _optional_json_object_attribute(tool, "meta")
    metadata = metadata or {}
    return McpToolDescriptor(
        server_identity=server_identity,
        name=name,
        description=description,
        input_schema=input_schema,
        output_schema=output_schema,
        annotations=annotations,
        metadata=metadata,
    )


def downstream_result_from_sdk_call_result(
    result: object,
    *,
    include_payload: bool = False,
) -> McpDownstreamResult:
    """Convert an MCP SDK call result into a sanitized downstream result summary."""

    result_payload = _call_result_payload(result)
    status = "failed" if getattr(result, "isError", False) is True else "succeeded"
    return McpDownstreamResult(
        status=status,
        result_digest=_json_digest(result_payload),
        result_payload=result_payload if include_payload else None,
    )


@asynccontextmanager
async def _open_sdk_session(
    config: McpSdkTransportConfig,
) -> AsyncIterator[McpSdkSession]:
    if isinstance(config, McpStreamableHttpClientConfig):
        async with _open_streamable_http_session(config) as session:
            yield session
        return

    async with _open_stdio_session(config) as session:
        yield session


@asynccontextmanager
async def _open_streamable_http_session(
    config: McpStreamableHttpClientConfig,
) -> AsyncIterator[McpSdkSession]:
    try:
        from mcp import ClientSession
        from mcp.client.streamable_http import streamablehttp_client
    except ImportError as exc:
        raise McpSdkUnavailable("MCP SDK is required for Streamable HTTP transport") from exc

    async with (
        streamablehttp_client(
            config.url,
            headers=config.headers,
            timeout=config.timeout_seconds,
            sse_read_timeout=config.sse_read_timeout_seconds,
        ) as (read_stream, write_stream, _get_session_id),
        ClientSession(
            read_stream,
            write_stream,
        ) as session,
    ):
        yield session


@asynccontextmanager
async def _open_stdio_session(config: McpStdioClientConfig) -> AsyncIterator[McpSdkSession]:
    try:
        from mcp import ClientSession
        from mcp.client.stdio import StdioServerParameters, stdio_client
    except ImportError as exc:
        raise McpSdkUnavailable("MCP SDK is required for stdio transport") from exc

    parameters = StdioServerParameters(
        command=config.command,
        args=list(config.args),
        env=config.env,
        cwd=config.cwd,
    )
    async with (
        stdio_client(parameters) as (read_stream, write_stream),
        ClientSession(
            read_stream,
            write_stream,
        ) as session,
    ):
        yield session


def _call_result_payload(result: object) -> JsonObject:
    payload: JsonObject = {
        "is_error": getattr(result, "isError", False) is True,
    }
    structured = _json_compatible(getattr(result, "structuredContent", None))
    if structured is not None:
        if not isinstance(structured, dict):
            raise ValueError("MCP structured content must be a JSON object")
        payload["structured_content"] = structured

    content = _json_compatible(getattr(result, "content", None))
    if content is not None:
        if not isinstance(content, list):
            raise ValueError("MCP content must be a JSON array")
        payload["content_item_count"] = len(content)
        payload["content_types"] = _content_types(content)
    validate_json_value(payload)
    return payload


def _content_types(content: list[JsonValue]) -> list[JsonValue]:
    content_types: list[JsonValue] = []
    for item in content:
        if isinstance(item, dict):
            item_type = item.get("type")
            if isinstance(item_type, str):
                content_types.append(item_type)
    return content_types


def _json_digest(payload: JsonObject) -> str:
    digest = hashlib.sha256(deterministic_json_bytes(payload)).hexdigest()
    return f"sha256:{digest}"


def _required_string_attribute(value: object, attribute: str) -> str:
    result = getattr(value, attribute, None)
    if not isinstance(result, str) or not result:
        raise ValueError(f"MCP SDK object missing required string attribute: {attribute}")
    return result


def _optional_string_attribute(value: object, attribute: str) -> str | None:
    result = getattr(value, attribute, None)
    if result is None:
        return None
    if not isinstance(result, str):
        raise ValueError(f"MCP SDK object attribute must be a string: {attribute}")
    return result


def _required_json_object_attribute(value: object, attribute: str) -> JsonObject:
    result = _json_compatible(getattr(value, attribute, None))
    if not isinstance(result, dict):
        raise ValueError(f"MCP SDK object missing required JSON object attribute: {attribute}")
    return result


def _optional_json_object_attribute(value: object, attribute: str) -> JsonObject | None:
    result = _json_compatible(getattr(value, attribute, None))
    if result is None:
        return None
    if not isinstance(result, dict):
        raise ValueError(f"MCP SDK object attribute must be a JSON object: {attribute}")
    return result


def _json_compatible(value: object) -> JsonValue | None:
    if value is None:
        return None
    if isinstance(value, str | int | float | bool):
        return value
    if hasattr(value, "model_dump"):
        dumped = value.model_dump(mode="json", by_alias=True, exclude_none=True)
        return _json_compatible(dumped)
    if isinstance(value, list):
        return [_json_compatible(item) for item in value]
    if isinstance(value, dict):
        converted: JsonObject = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise ValueError("payload object keys must be strings")
            converted[key] = _json_compatible(item)
        return converted
    validate_json_value(value)
    raise ValueError(f"payload contains unsupported JSON value type: {type(value).__name__}")
