"""Transport-boundary helpers for MCP tool descriptors."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field

from actionlineage.domain import deterministic_json_bytes
from actionlineage.domain.events import JsonObject, JsonValue, validate_json_value


@dataclass(frozen=True, slots=True)
class McpToolDescriptor:
    """Canonical MCP descriptor data used for transport-neutral tool identity."""

    server_identity: str
    name: str
    description: str
    input_schema: JsonObject
    output_schema: JsonObject | None = None
    annotations: JsonObject = field(default_factory=dict)
    metadata: JsonObject = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.server_identity:
            raise ValueError("server_identity is required")
        if not self.name:
            raise ValueError("name is required")
        validate_json_value(self.input_schema)
        if self.output_schema is not None:
            validate_json_value(self.output_schema)
        validate_json_value(self.annotations)
        validate_json_value(self.metadata)

    def canonical_object(self) -> JsonObject:
        """Return the descriptor fields covered by identity hashing."""

        return {
            "adapter": "mcp",
            "server_identity": self.server_identity,
            "name": self.name,
            "description": self.description,
            "input_schema": self.input_schema,
            "output_schema": self.output_schema,
            "annotations": self.annotations,
            "metadata": self.metadata,
        }


def descriptor_hash(descriptor: McpToolDescriptor) -> str:
    """Return a stable descriptor hash independent of JSON key order."""

    canonical_bytes = deterministic_json_bytes(descriptor.canonical_object())
    return f"sha256:{hashlib.sha256(canonical_bytes).hexdigest()}"


def tool_identity(descriptor: McpToolDescriptor) -> JsonObject:
    """Return transport-neutral tool identity payload."""

    return {
        "adapter": "mcp",
        "server_identity": descriptor.server_identity,
        "name": descriptor.name,
        "descriptor_hash": descriptor_hash(descriptor),
    }


def descriptor_payload(
    descriptor: McpToolDescriptor,
    *,
    arguments_digest: str | None = None,
) -> JsonObject:
    """Return a neutral evidence payload for a tool execution request."""

    payload: dict[str, JsonValue] = {
        "tool_identity": tool_identity(descriptor),
        "descriptor": descriptor.canonical_object(),
    }
    if arguments_digest is not None:
        payload["arguments_digest"] = arguments_digest
    return payload
