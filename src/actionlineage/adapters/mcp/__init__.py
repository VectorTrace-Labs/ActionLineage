"""MCP adapter boundary without importing the MCP SDK into core modules."""

from actionlineage.adapters.mcp.descriptors import (
    McpToolDescriptor,
    descriptor_hash,
    descriptor_payload,
    tool_identity,
)
from actionlineage.adapters.mcp.runtime import (
    McpDownstreamCallable,
    McpDownstreamResult,
    McpExecutionPlan,
    McpProxyExecutionResult,
    McpTransportKind,
    acknowledgement_payload,
    descriptor_drift_payload,
    execute_mcp_tool_call,
    plan_mcp_tool_execution,
)
from actionlineage.adapters.mcp.sdk import (
    McpSdkClient,
    McpSdkSession,
    McpSdkSessionOpener,
    McpSdkTransportConfig,
    McpSdkUnavailable,
    McpStdioClientConfig,
    McpStreamableHttpClientConfig,
    descriptor_from_sdk_tool,
    downstream_result_from_sdk_call_result,
)

__all__ = [
    "McpDownstreamCallable",
    "McpDownstreamResult",
    "McpExecutionPlan",
    "McpProxyExecutionResult",
    "McpSdkClient",
    "McpSdkSession",
    "McpSdkSessionOpener",
    "McpSdkTransportConfig",
    "McpSdkUnavailable",
    "McpStdioClientConfig",
    "McpStreamableHttpClientConfig",
    "McpToolDescriptor",
    "McpTransportKind",
    "acknowledgement_payload",
    "descriptor_drift_payload",
    "descriptor_from_sdk_tool",
    "descriptor_hash",
    "descriptor_payload",
    "downstream_result_from_sdk_call_result",
    "execute_mcp_tool_call",
    "plan_mcp_tool_execution",
    "tool_identity",
]
