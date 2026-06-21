"""Dependency-free MCP runtime planning helpers.

The actual MCP SDK remains an optional transport dependency. This module defines
the evidence mapping and fail-behavior semantics that a concrete MCP proxy uses.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from typing import cast

from actionlineage.adapters.mcp.descriptors import (
    McpToolDescriptor,
    descriptor_hash,
    descriptor_payload,
    tool_identity,
)
from actionlineage.adapters.policy import (
    ApprovalValidationResult,
    PolicyDecision,
    PolicyFailureMode,
)
from actionlineage.domain import EventType
from actionlineage.domain.events import JsonObject, validate_json_value
from actionlineage.evidence import EvidenceNormalizer
from actionlineage.journal import JournalWriter


class McpTransportKind(StrEnum):
    """Supported optional MCP transports."""

    STREAMABLE_HTTP = "streamable_http"
    STDIO = "stdio"


@dataclass(frozen=True, slots=True)
class McpExecutionPlan:
    """Neutral evidence payloads for one MCP tool execution."""

    should_dispatch: bool
    requested_payload: JsonObject
    policy_payload: JsonObject
    authorized_payload: JsonObject | None
    dispatch_payload: JsonObject | None
    not_dispatched_payload: JsonObject | None
    degraded_payload: JsonObject | None

    def lifecycle_event_types(self) -> tuple[str, ...]:
        event_types = [EventType.TOOL_EXECUTION_REQUESTED.value, EventType.POLICY_DECISION.value]
        if self.authorized_payload is not None:
            event_types.append(EventType.TOOL_EXECUTION_AUTHORIZED.value)
        if self.dispatch_payload is not None:
            event_types.append(EventType.TOOL_EXECUTION_DISPATCHED.value)
        if self.not_dispatched_payload is not None:
            event_types.append(EventType.TOOL_EXECUTION_NOT_DISPATCHED.value)
        if self.degraded_payload is not None:
            event_types.append(EventType.RECORDER_DEGRADED.value)
        return tuple(event_types)


@dataclass(frozen=True, slots=True)
class McpDownstreamResult:
    """Sanitized downstream MCP result summary for acknowledgement evidence."""

    status: str
    result_digest: str | None = None
    result_payload: JsonObject | None = None


@dataclass(frozen=True, slots=True)
class McpProxyExecutionResult:
    """Result of executing one MCP call through the adapter boundary."""

    dispatched: bool
    downstream_called: bool
    event_ids: tuple[str, ...]
    acknowledgement_event_id: str | None = None
    acknowledgement_status: str | None = None


type McpDownstreamCallable = Callable[[McpToolDescriptor, JsonObject], McpDownstreamResult]


def plan_mcp_tool_execution(
    descriptor: McpToolDescriptor,
    *,
    arguments_digest: str,
    call_id: str,
    transport: McpTransportKind,
    policy_decision: PolicyDecision,
    failure_mode: PolicyFailureMode = PolicyFailureMode.FAIL_CLOSED,
    approval_result: ApprovalValidationResult | None = None,
) -> McpExecutionPlan:
    """Map one MCP call decision into neutral lifecycle payloads."""

    approval_accepted = approval_result.accepted if approval_result is not None else False
    should_dispatch = policy_decision.dispatch_allowed(
        failure_mode=failure_mode,
        approval_accepted=approval_accepted,
    )
    requested_payload = descriptor_payload(descriptor, arguments_digest=arguments_digest)
    requested_payload["call_id"] = call_id
    requested_payload["transport"] = transport.value
    policy_payload = _json_object(policy_decision.as_payload())
    if approval_result is not None:
        policy_payload["approval"] = _json_object(approval_result.as_payload())

    authorized_payload: JsonObject | None = None
    dispatch_payload: JsonObject | None = None
    not_dispatched_payload: JsonObject | None = None
    degraded_payload: JsonObject | None = None

    if should_dispatch:
        authorized_payload = _json_object(
            {
                "tool_identity": tool_identity(descriptor),
                "authorization": {
                    "outcome": "authorized",
                    "policy_decision": policy_payload,
                    "approval_accepted": approval_accepted,
                },
            }
        )
        dispatch_payload = _json_object(
            {
                "tool_identity": tool_identity(descriptor),
                "dispatch": {
                    "state": "dispatched",
                    "transport": transport.value,
                    "call_id": call_id,
                },
            }
        )
    else:
        not_dispatched_payload = _json_object(
            {
                "tool_identity": tool_identity(descriptor),
                "not_dispatched": {
                    "reason": _not_dispatched_reason(policy_decision, approval_result),
                    "downstream_forwarded": False,
                    "call_id": call_id,
                },
            }
        )

    if policy_decision.outcome.value == "error":
        degraded_payload = _json_object(
            {
                "degraded_component": "policy_adapter",
                "failure_mode": failure_mode.value,
                "risk_class": policy_decision.risk_class.value,
                "reason": policy_decision.reason,
                "dispatch_allowed": should_dispatch,
            }
        )

    return McpExecutionPlan(
        should_dispatch=should_dispatch,
        requested_payload=requested_payload,
        policy_payload=policy_payload,
        authorized_payload=authorized_payload,
        dispatch_payload=dispatch_payload,
        not_dispatched_payload=not_dispatched_payload,
        degraded_payload=degraded_payload,
    )


def execute_mcp_tool_call(
    descriptor: McpToolDescriptor,
    *,
    arguments: JsonObject,
    arguments_digest: str,
    call_id: str,
    transport: McpTransportKind,
    policy_decision: PolicyDecision,
    downstream: McpDownstreamCallable,
    normalizer: EvidenceNormalizer,
    journal: JournalWriter,
    failure_mode: PolicyFailureMode = PolicyFailureMode.FAIL_CLOSED,
    approval_result: ApprovalValidationResult | None = None,
) -> McpProxyExecutionResult:
    """Record and optionally dispatch one MCP tool call.

    The caller supplies an already-rooted normalizer, usually after recording
    agent intent. Raw arguments are passed only to the downstream callable and
    are not persisted by this helper; the journal receives the digest and neutral
    lifecycle evidence.
    """

    validate_json_value(arguments)
    plan = plan_mcp_tool_execution(
        descriptor,
        arguments_digest=arguments_digest,
        call_id=call_id,
        transport=transport,
        policy_decision=policy_decision,
        failure_mode=failure_mode,
        approval_result=approval_result,
    )
    event_ids = list(_append_plan_events(plan, normalizer=normalizer, journal=journal))

    if not plan.should_dispatch:
        return McpProxyExecutionResult(
            dispatched=False,
            downstream_called=False,
            event_ids=tuple(event_ids),
        )

    acknowledgement = _call_downstream(
        descriptor,
        arguments=arguments,
        call_id=call_id,
        downstream=downstream,
    )
    acknowledgement_event = journal.append(
        normalizer.record(EventType.TOOL_EXECUTION_ACKNOWLEDGED, acknowledgement)
    )
    event_ids.append(acknowledgement_event.event_id)
    acknowledgement_body = acknowledgement.get("acknowledgement")
    status = acknowledgement_body.get("status") if isinstance(acknowledgement_body, dict) else None
    return McpProxyExecutionResult(
        dispatched=True,
        downstream_called=True,
        event_ids=tuple(event_ids),
        acknowledgement_event_id=acknowledgement_event.event_id,
        acknowledgement_status=status if isinstance(status, str) else None,
    )


def descriptor_drift_payload(
    previous: McpToolDescriptor,
    current: McpToolDescriptor,
) -> JsonObject:
    """Return payload for a descriptor drift evidence event."""

    previous_hash = descriptor_hash(previous)
    current_hash = descriptor_hash(current)
    return {
        "tool_identity": tool_identity(current),
        "descriptor_drift": {
            "previous_descriptor_hash": previous_hash,
            "current_descriptor_hash": current_hash,
            "changed": previous_hash != current_hash,
            "server_identity": current.server_identity,
            "tool_name": current.name,
        },
    }


def acknowledgement_payload(
    descriptor: McpToolDescriptor,
    *,
    call_id: str,
    status: str,
    result_digest: str | None = None,
    result_payload: JsonObject | None = None,
) -> JsonObject:
    """Return an acknowledgement payload and reject malformed JSON results."""

    if result_payload is not None:
        validate_json_value(result_payload)
    acknowledgement: JsonObject = {
        "status": status,
        "call_id": call_id,
        "side_effect_status": "unverified",
        "note": "MCP tool acknowledgement is not side-effect verification",
    }
    if result_digest is not None:
        acknowledgement["result_digest"] = result_digest
    if result_payload is not None:
        acknowledgement["result"] = result_payload
    return _json_object(
        {
            "tool_identity": tool_identity(descriptor),
            "acknowledgement": acknowledgement,
        }
    )


def _append_plan_events(
    plan: McpExecutionPlan,
    *,
    normalizer: EvidenceNormalizer,
    journal: JournalWriter,
) -> tuple[str, ...]:
    appended: list[str] = []
    for event_type, payload in (
        (EventType.TOOL_EXECUTION_REQUESTED, plan.requested_payload),
        (EventType.POLICY_DECISION, plan.policy_payload),
        (EventType.TOOL_EXECUTION_AUTHORIZED, plan.authorized_payload),
        (EventType.TOOL_EXECUTION_DISPATCHED, plan.dispatch_payload),
        (EventType.TOOL_EXECUTION_NOT_DISPATCHED, plan.not_dispatched_payload),
        (EventType.RECORDER_DEGRADED, plan.degraded_payload),
    ):
        if payload is None:
            continue
        appended_event = journal.append(normalizer.record(event_type, payload))
        appended.append(appended_event.event_id)
    return tuple(appended)


def _call_downstream(
    descriptor: McpToolDescriptor,
    *,
    arguments: JsonObject,
    call_id: str,
    downstream: McpDownstreamCallable,
) -> JsonObject:
    try:
        result = downstream(descriptor, arguments)
        return acknowledgement_payload(
            descriptor,
            call_id=call_id,
            status=result.status,
            result_digest=result.result_digest,
            result_payload=result.result_payload,
        )
    except ValueError:
        return acknowledgement_payload(
            descriptor,
            call_id=call_id,
            status="failed",
            result_payload={"error": "malformed_downstream_result"},
        )
    except Exception as exc:
        return acknowledgement_payload(
            descriptor,
            call_id=call_id,
            status="failed",
            result_payload={
                "error": "downstream_execution_failed",
                "error_type": type(exc).__name__,
            },
        )


def _not_dispatched_reason(
    policy_decision: PolicyDecision,
    approval_result: ApprovalValidationResult | None,
) -> str:
    if approval_result is not None and not approval_result.accepted:
        return "approval_rejected"
    return f"policy_{policy_decision.outcome.value}"


def _json_object(value: dict[str, object]) -> JsonObject:
    validate_json_value(value)
    return cast(JsonObject, value)
