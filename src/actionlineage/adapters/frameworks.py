"""Dependency-free framework adapter evidence helpers.

These helpers let optional runtime integrations for agent frameworks map tool
callbacks into ActionLineage's neutral evidence model without importing the
framework SDKs into core.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from enum import StrEnum

from actionlineage.domain import EventType, deterministic_json_bytes
from actionlineage.domain.events import JsonObject, validate_json_value
from actionlineage.evidence import (
    DelegatedIdentity,
    EvidenceRecord,
    EvidenceSourceKind,
    NormalizedAction,
    NormalizedResource,
    ToolIdentity,
)


class FrameworkKind(StrEnum):
    """Known optional framework adapter families."""

    OPENAI_AGENTS = "openai_agents"
    LANGCHAIN = "langchain"
    LLAMAINDEX = "llamaindex"
    CREWAI = "crewai"
    SHELL = "shell"
    BROWSER = "browser"
    LOCAL_FUNCTION = "local_function"
    UNKNOWN = "unknown"


class FrameworkAcknowledgementStatus(StrEnum):
    """Framework-level acknowledgement outcomes.

    These are adapter acknowledgements only. They are not side-effect
    observations or verification.
    """

    SUCCEEDED = "succeeded"
    FAILED = "failed"
    TIMED_OUT = "timed_out"
    CANCELLED = "cancelled"
    UNKNOWN = "unknown"


@dataclass(frozen=True, slots=True)
class FrameworkToolDescriptor:
    """Transport-neutral descriptor for non-MCP framework tools."""

    framework: FrameworkKind
    tool_name: str
    description: str
    input_schema: JsonObject
    server_identity: str | None = None
    output_schema: JsonObject | None = None
    version: str | None = None
    annotations: JsonObject = field(default_factory=dict)
    metadata: JsonObject = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.tool_name:
            raise ValueError("tool_name is required")
        validate_json_value(self.input_schema)
        if self.output_schema is not None:
            validate_json_value(self.output_schema)
        validate_json_value(self.annotations)
        validate_json_value(self.metadata)

    def canonical_object(self) -> JsonObject:
        """Return descriptor fields covered by identity hashing."""

        payload: JsonObject = {
            "adapter": "framework",
            "framework": self.framework.value,
            "tool_name": self.tool_name,
            "description": self.description,
            "input_schema": self.input_schema,
            "output_schema": self.output_schema,
            "annotations": self.annotations,
            "metadata": self.metadata,
        }
        if self.server_identity is not None:
            payload["server_identity"] = self.server_identity
        if self.version is not None:
            payload["version"] = self.version
        return payload


@dataclass(frozen=True, slots=True)
class FrameworkToolInvocation:
    """One framework tool invocation ready for evidence normalization."""

    descriptor: FrameworkToolDescriptor
    invocation_id: str
    action_type: str
    arguments_digest: str
    resources: tuple[NormalizedResource, ...] = ()
    delegated_identity: DelegatedIdentity | None = None
    attributes: JsonObject = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.invocation_id:
            raise ValueError("invocation_id is required")
        if not self.action_type:
            raise ValueError("action_type is required")
        if not self.arguments_digest:
            raise ValueError("arguments_digest is required")
        validate_json_value(self.attributes)

    @property
    def idempotency_prefix(self) -> str:
        """Stable idempotency prefix for lifecycle records."""

        return f"framework:{self.descriptor.framework.value}:{self.invocation_id}"


def framework_descriptor_hash(descriptor: FrameworkToolDescriptor) -> str:
    """Return a stable descriptor hash independent of JSON key order."""

    canonical_bytes = deterministic_json_bytes(descriptor.canonical_object())
    return f"sha256:{hashlib.sha256(canonical_bytes).hexdigest()}"


def framework_tool_identity(descriptor: FrameworkToolDescriptor) -> JsonObject:
    """Return a neutral tool identity payload for a framework tool."""

    identity: JsonObject = {
        "adapter": "framework",
        "framework": descriptor.framework.value,
        "name": descriptor.tool_name,
        "descriptor_hash": framework_descriptor_hash(descriptor),
    }
    if descriptor.server_identity is not None:
        identity["server_identity"] = descriptor.server_identity
    if descriptor.version is not None:
        identity["version"] = descriptor.version
    return identity


def framework_descriptor_payload(descriptor: FrameworkToolDescriptor) -> JsonObject:
    """Return a descriptor evidence payload for framework tools."""

    return {
        "tool_identity": framework_tool_identity(descriptor),
        "descriptor": descriptor.canonical_object(),
    }


def framework_lifecycle_records(
    invocation: FrameworkToolInvocation,
    *,
    acknowledgement_status: FrameworkAcknowledgementStatus | None = None,
    result_digest: str | None = None,
    result_summary: JsonObject | None = None,
    not_dispatched_reason: str | None = None,
    sort_key_prefix: str = "",
) -> tuple[EvidenceRecord, ...]:
    """Map one framework invocation into neutral lifecycle evidence records."""

    if result_summary is not None:
        validate_json_value(result_summary)

    records = [
        _record(
            invocation,
            event_type=EventType.TOOL_EXECUTION_REQUESTED,
            lifecycle="requested",
            payload=_request_payload(invocation),
            sort_key_prefix=sort_key_prefix,
        )
    ]

    if not_dispatched_reason is not None:
        records.append(
            _record(
                invocation,
                event_type=EventType.TOOL_EXECUTION_NOT_DISPATCHED,
                lifecycle="not_dispatched",
                payload=_not_dispatched_payload(invocation, reason=not_dispatched_reason),
                sort_key_prefix=sort_key_prefix,
            )
        )
        return tuple(records)

    records.append(
        _record(
            invocation,
            event_type=EventType.TOOL_EXECUTION_DISPATCHED,
            lifecycle="dispatched",
            payload=_dispatch_payload(invocation),
            sort_key_prefix=sort_key_prefix,
        )
    )

    if acknowledgement_status is not None:
        records.append(
            _record(
                invocation,
                event_type=EventType.TOOL_EXECUTION_ACKNOWLEDGED,
                lifecycle="acknowledged",
                payload=_acknowledgement_payload(
                    invocation,
                    status=acknowledgement_status,
                    result_digest=result_digest,
                    result_summary=result_summary,
                ),
                sort_key_prefix=sort_key_prefix,
            )
        )

    return tuple(records)


def _request_payload(invocation: FrameworkToolInvocation) -> JsonObject:
    action = NormalizedAction(
        action_type=invocation.action_type,
        resources=invocation.resources,
        tool_identity=ToolIdentity(
            name=invocation.descriptor.tool_name,
            descriptor_hash=framework_descriptor_hash(invocation.descriptor),
            adapter=f"framework:{invocation.descriptor.framework.value}",
            version=invocation.descriptor.version,
        ),
        delegated_identity=invocation.delegated_identity,
        attributes=invocation.attributes,
    )
    return {
        "tool_identity": framework_tool_identity(invocation.descriptor),
        "descriptor": invocation.descriptor.canonical_object(),
        "framework_invocation": _invocation_payload(invocation),
        "action": action.as_payload(),
    }


def _dispatch_payload(invocation: FrameworkToolInvocation) -> JsonObject:
    return {
        "tool_identity": framework_tool_identity(invocation.descriptor),
        "framework_invocation": _invocation_payload(invocation),
        "dispatch": {
            "state": "dispatched",
            "adapter": "framework",
            "framework": invocation.descriptor.framework.value,
        },
    }


def _acknowledgement_payload(
    invocation: FrameworkToolInvocation,
    *,
    status: FrameworkAcknowledgementStatus,
    result_digest: str | None,
    result_summary: JsonObject | None,
) -> JsonObject:
    acknowledgement: JsonObject = {
        "status": status.value,
        "side_effect_status": "unverified",
        "note": "Framework tool acknowledgement is not side-effect verification",
    }
    if result_digest is not None:
        acknowledgement["result_digest"] = result_digest
    if result_summary is not None:
        acknowledgement["result_summary"] = result_summary
    return {
        "tool_identity": framework_tool_identity(invocation.descriptor),
        "framework_invocation": _invocation_payload(invocation),
        "acknowledgement": acknowledgement,
    }


def _not_dispatched_payload(invocation: FrameworkToolInvocation, *, reason: str) -> JsonObject:
    if not reason:
        raise ValueError("not_dispatched_reason is required")
    return {
        "tool_identity": framework_tool_identity(invocation.descriptor),
        "framework_invocation": _invocation_payload(invocation),
        "not_dispatched": {
            "reason": reason,
            "downstream_forwarded": False,
        },
    }


def _invocation_payload(invocation: FrameworkToolInvocation) -> JsonObject:
    return {
        "invocation_id": invocation.invocation_id,
        "framework": invocation.descriptor.framework.value,
        "arguments_digest": invocation.arguments_digest,
    }


def _record(
    invocation: FrameworkToolInvocation,
    *,
    event_type: EventType,
    lifecycle: str,
    payload: JsonObject,
    sort_key_prefix: str,
) -> EvidenceRecord:
    validate_json_value(payload)
    return EvidenceRecord(
        idempotency_key=f"{invocation.idempotency_prefix}:{lifecycle}",
        event_type=event_type,
        payload=payload,
        source_kind=EvidenceSourceKind.EXTERNAL_JSON,
        sort_key=f"{sort_key_prefix}{invocation.invocation_id}:{lifecycle}",
    )
