from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from actionlineage.adapters import (
    ApprovalArtifact,
    ApprovalReplayCache,
    PolicyDecision,
    PolicyDecisionOutcome,
    PolicyFailureMode,
    RiskClass,
)
from actionlineage.adapters.mcp import (
    McpDownstreamResult,
    McpToolDescriptor,
    McpTransportKind,
    acknowledgement_payload,
    descriptor_drift_payload,
    descriptor_hash,
    descriptor_payload,
    execute_mcp_tool_call,
    plan_mcp_tool_execution,
)
from actionlineage.domain import (
    Classification,
    Correlation,
    EventType,
    FixedClock,
    FixedIdGenerator,
    Principal,
    PrincipalType,
    Sensitivity,
    Source,
    TrustLevel,
)
from actionlineage.evidence import EvidenceNormalizer
from actionlineage.journal import LocalJournal
from tests.domain.test_events import BASE_TIME


def test_mcp_descriptor_hash_is_stable_for_equivalent_json_ordering() -> None:
    descriptor_a = McpToolDescriptor(
        server_identity="demo-mcp-server",
        name="safe_files.read",
        description="Read a synthetic local file",
        input_schema={
            "type": "object",
            "properties": {"path": {"type": "string"}, "encoding": {"type": "string"}},
            "required": ["path"],
        },
    )
    descriptor_b = McpToolDescriptor(
        server_identity="demo-mcp-server",
        name="safe_files.read",
        description="Read a synthetic local file",
        input_schema={
            "required": ["path"],
            "properties": {"encoding": {"type": "string"}, "path": {"type": "string"}},
            "type": "object",
        },
    )

    assert descriptor_hash(descriptor_a) == descriptor_hash(descriptor_b)


def test_mcp_descriptor_hash_changes_for_security_relevant_descriptor_drift() -> None:
    original = McpToolDescriptor(
        server_identity="demo-mcp-server",
        name="safe_files.read",
        description="Read a synthetic local file",
        input_schema={"type": "object"},
    )
    changed = McpToolDescriptor(
        server_identity="demo-mcp-server",
        name="safe_files.read",
        description="Read any local file",
        input_schema={"type": "object"},
    )

    assert descriptor_hash(original) != descriptor_hash(changed)


def test_mcp_descriptor_payload_maps_to_neutral_tool_identity() -> None:
    descriptor = McpToolDescriptor(
        server_identity="demo-mcp-server",
        name="safe_http.send",
        description="Send to the local receiver fixture",
        input_schema={"type": "object"},
    )
    payload = descriptor_payload(descriptor, arguments_digest="sha256:demo_args")

    assert payload["tool_identity"]["adapter"] == "mcp"
    assert payload["tool_identity"]["name"] == "safe_http.send"
    assert payload["arguments_digest"] == "sha256:demo_args"


def test_mcp_descriptor_rejects_non_json_schema_values() -> None:
    with pytest.raises(ValueError, match="unsupported JSON value type"):
        McpToolDescriptor(
            server_identity="demo-mcp-server",
            name="unsafe",
            description="bad schema",
            input_schema={"type": object()},
        )


def test_mcp_descriptor_drift_payload_records_hash_change() -> None:
    original = McpToolDescriptor(
        server_identity="demo-mcp-server",
        name="safe_files.read",
        description="Read a synthetic local file",
        input_schema={"type": "object"},
    )
    changed = McpToolDescriptor(
        server_identity="demo-mcp-server",
        name="safe_files.read",
        description="Read any local file",
        input_schema={"type": "object"},
    )
    payload = descriptor_drift_payload(original, changed)

    assert payload["descriptor_drift"]["changed"] is True
    assert (
        payload["descriptor_drift"]["previous_descriptor_hash"]
        != payload["descriptor_drift"]["current_descriptor_hash"]
    )


def test_policy_deny_plan_is_not_dispatched() -> None:
    plan = plan_mcp_tool_execution(
        _descriptor(),
        arguments_digest="sha256:args",
        call_id="call_1",
        transport=McpTransportKind.STREAMABLE_HTTP,
        policy_decision=PolicyDecision(
            outcome=PolicyDecisionOutcome.DENY,
            policy_id="demo.deny",
            policy_version="1",
            reason="blocked by test policy",
        ),
    )

    assert plan.should_dispatch is False
    assert plan.dispatch_payload is None
    assert plan.not_dispatched_payload is not None
    assert plan.not_dispatched_payload["not_dispatched"]["downstream_forwarded"] is False
    assert "tool.execution.not_dispatched" in plan.lifecycle_event_types()


def test_policy_error_fail_open_and_fail_closed_are_explicit() -> None:
    decision = PolicyDecision(
        outcome=PolicyDecisionOutcome.ERROR,
        policy_id="demo.timeout",
        policy_version="1",
        reason="evaluator timeout",
        risk_class=RiskClass.HIGH,
    )
    fail_closed = plan_mcp_tool_execution(
        _descriptor(),
        arguments_digest="sha256:args",
        call_id="call_closed",
        transport=McpTransportKind.STREAMABLE_HTTP,
        policy_decision=decision,
        failure_mode=PolicyFailureMode.FAIL_CLOSED,
    )
    fail_open = plan_mcp_tool_execution(
        _descriptor(),
        arguments_digest="sha256:args",
        call_id="call_open",
        transport=McpTransportKind.STREAMABLE_HTTP,
        policy_decision=decision,
        failure_mode=PolicyFailureMode.FAIL_OPEN,
    )

    assert fail_closed.should_dispatch is False
    assert fail_closed.degraded_payload["dispatch_allowed"] is False
    assert fail_open.should_dispatch is True
    assert fail_open.degraded_payload["dispatch_allowed"] is True


def test_approval_artifact_rejects_replay() -> None:
    cache = ApprovalReplayCache.empty()
    now = datetime(2026, 6, 21, 18, 42, 12, tzinfo=UTC)
    approval = ApprovalArtifact(
        approval_id="approval_1",
        subject_event_id="evt_request",
        scope="safe_http.send:demo",
        expires_at=now + timedelta(minutes=5),
        nonce="nonce_1",
        approved_by="user_demo",
    )

    accepted = cache.claim(
        approval,
        now=now,
        subject_event_id="evt_request",
        scope="safe_http.send:demo",
    )
    replayed = cache.claim(
        approval,
        now=now,
        subject_event_id="evt_request",
        scope="safe_http.send:demo",
    )

    assert accepted.accepted is True
    assert replayed.accepted is False
    assert replayed.reason == "approval nonce was already used"


def test_require_approval_dispatches_only_with_valid_approval() -> None:
    now = datetime(2026, 6, 21, 18, 42, 12, tzinfo=UTC)
    approval = ApprovalArtifact(
        approval_id="approval_2",
        subject_event_id="evt_request",
        scope="safe_http.send:demo",
        expires_at=now + timedelta(minutes=5),
        nonce="nonce_2",
        approved_by="user_demo",
    )
    approval_result = ApprovalReplayCache.empty().claim(
        approval,
        now=now,
        subject_event_id="evt_request",
        scope="safe_http.send:demo",
    )
    decision = PolicyDecision(
        outcome=PolicyDecisionOutcome.REQUIRE_APPROVAL,
        policy_id="demo.approval",
        policy_version="1",
        reason="approval required",
    )

    without_approval = plan_mcp_tool_execution(
        _descriptor(),
        arguments_digest="sha256:args",
        call_id="call_no_approval",
        transport=McpTransportKind.STDIO,
        policy_decision=decision,
    )
    with_approval = plan_mcp_tool_execution(
        _descriptor(),
        arguments_digest="sha256:args",
        call_id="call_with_approval",
        transport=McpTransportKind.STDIO,
        policy_decision=decision,
        approval_result=approval_result,
    )

    assert without_approval.should_dispatch is False
    assert with_approval.should_dispatch is True
    assert with_approval.policy_payload["approval"]["status"] == "accepted"


def test_malformed_downstream_result_is_rejected() -> None:
    with pytest.raises(ValueError, match="unsupported JSON value type"):
        acknowledgement_payload(
            _descriptor(),
            call_id="call_bad_result",
            status="failed",
            result_payload={"bad": object()},
        )


def test_mcp_proxy_executor_records_allowed_lifecycle_and_acknowledgement(tmp_path) -> None:
    journal = LocalJournal(tmp_path / "mcp.journal")
    normalizer = _normalizer(
        "evt_root",
        "evt_requested",
        "evt_policy",
        "evt_authorized",
        "evt_dispatched",
        "evt_ack",
    )
    journal.append(normalizer.record(EventType.AGENT_INTENT_RECORDED, {"intent": "call mcp"}))
    calls: list[dict[str, object]] = []

    def downstream(
        descriptor: McpToolDescriptor, arguments: dict[str, object]
    ) -> McpDownstreamResult:
        calls.append({"tool": descriptor.name, "arguments": arguments})
        return McpDownstreamResult(
            status="succeeded",
            result_digest="sha256:result",
            result_payload={"accepted": True},
        )

    result = execute_mcp_tool_call(
        _descriptor(),
        arguments={"url": "https://receiver.example.invalid/ingest"},
        arguments_digest="sha256:args",
        call_id="call_allowed",
        transport=McpTransportKind.STREAMABLE_HTTP,
        policy_decision=PolicyDecision(
            outcome=PolicyDecisionOutcome.ALLOW,
            policy_id="demo.allow",
            policy_version="1",
            reason="allowed by test policy",
        ),
        downstream=downstream,
        normalizer=normalizer,
        journal=journal,
    )
    events = tuple(journal.iter_events())

    assert result.dispatched is True
    assert result.downstream_called is True
    assert result.acknowledgement_status == "succeeded"
    assert len(calls) == 1
    assert [event.event_type for event in events[1:]] == [
        EventType.TOOL_EXECUTION_REQUESTED,
        EventType.POLICY_DECISION,
        EventType.TOOL_EXECUTION_AUTHORIZED,
        EventType.TOOL_EXECUTION_DISPATCHED,
        EventType.TOOL_EXECUTION_ACKNOWLEDGED,
    ]
    assert events[-1].payload["acknowledgement"]["side_effect_status"] == "unverified"


def test_mcp_proxy_executor_does_not_forward_denied_calls(tmp_path) -> None:
    journal = LocalJournal(tmp_path / "mcp-deny.journal")
    normalizer = _normalizer("evt_root", "evt_requested", "evt_policy", "evt_not_dispatched")
    journal.append(normalizer.record(EventType.AGENT_INTENT_RECORDED, {"intent": "call mcp"}))
    called = False

    def downstream(
        descriptor: McpToolDescriptor,
        arguments: dict[str, object],
    ) -> McpDownstreamResult:
        nonlocal called
        called = True
        return McpDownstreamResult(status="succeeded")

    result = execute_mcp_tool_call(
        _descriptor(),
        arguments={"url": "https://receiver.example.invalid/ingest"},
        arguments_digest="sha256:args",
        call_id="call_denied",
        transport=McpTransportKind.STDIO,
        policy_decision=PolicyDecision(
            outcome=PolicyDecisionOutcome.DENY,
            policy_id="demo.deny",
            policy_version="1",
            reason="blocked by test policy",
        ),
        downstream=downstream,
        normalizer=normalizer,
        journal=journal,
    )
    events = tuple(journal.iter_events())

    assert result.dispatched is False
    assert result.downstream_called is False
    assert called is False
    assert events[-1].event_type == EventType.TOOL_EXECUTION_NOT_DISPATCHED
    assert events[-1].payload["not_dispatched"]["downstream_forwarded"] is False


def test_mcp_proxy_executor_records_downstream_failure_as_unverified_acknowledgement(
    tmp_path,
) -> None:
    journal = LocalJournal(tmp_path / "mcp-fail.journal")
    normalizer = _normalizer(
        "evt_root",
        "evt_requested",
        "evt_policy",
        "evt_authorized",
        "evt_dispatched",
        "evt_ack",
    )
    journal.append(normalizer.record(EventType.AGENT_INTENT_RECORDED, {"intent": "call mcp"}))

    def downstream(
        descriptor: McpToolDescriptor,
        arguments: dict[str, object],
    ) -> McpDownstreamResult:
        raise TimeoutError("synthetic timeout")

    result = execute_mcp_tool_call(
        _descriptor(),
        arguments={"url": "https://receiver.example.invalid/ingest"},
        arguments_digest="sha256:args",
        call_id="call_failed",
        transport=McpTransportKind.STREAMABLE_HTTP,
        policy_decision=PolicyDecision(
            outcome=PolicyDecisionOutcome.ALLOW,
            policy_id="demo.allow",
            policy_version="1",
            reason="allowed by test policy",
        ),
        downstream=downstream,
        normalizer=normalizer,
        journal=journal,
    )
    acknowledgement = tuple(journal.iter_events())[-1].payload["acknowledgement"]

    assert result.acknowledgement_status == "failed"
    assert acknowledgement["side_effect_status"] == "unverified"
    assert acknowledgement["result"]["error"] == "downstream_execution_failed"
    assert acknowledgement["result"]["error_type"] == "TimeoutError"


def test_mcp_proxy_executor_sanitizes_malformed_downstream_results(tmp_path) -> None:
    journal = LocalJournal(tmp_path / "mcp-malformed.journal")
    normalizer = _normalizer(
        "evt_root",
        "evt_requested",
        "evt_policy",
        "evt_authorized",
        "evt_dispatched",
        "evt_ack",
    )
    journal.append(normalizer.record(EventType.AGENT_INTENT_RECORDED, {"intent": "call mcp"}))

    def downstream(
        descriptor: McpToolDescriptor,
        arguments: dict[str, object],
    ) -> McpDownstreamResult:
        return McpDownstreamResult(status="succeeded", result_payload={"bad": object()})

    execute_mcp_tool_call(
        _descriptor(),
        arguments={"url": "https://receiver.example.invalid/ingest"},
        arguments_digest="sha256:args",
        call_id="call_malformed",
        transport=McpTransportKind.STREAMABLE_HTTP,
        policy_decision=PolicyDecision(
            outcome=PolicyDecisionOutcome.ALLOW,
            policy_id="demo.allow",
            policy_version="1",
            reason="allowed by test policy",
        ),
        downstream=downstream,
        normalizer=normalizer,
        journal=journal,
    )
    acknowledgement = tuple(journal.iter_events())[-1].payload["acknowledgement"]

    assert acknowledgement["status"] == "failed"
    assert acknowledgement["result"]["error"] == "malformed_downstream_result"


def test_core_modules_do_not_import_optional_adapter_dependencies() -> None:
    forbidden = (
        "import mcp",
        "from mcp",
        "import opentelemetry",
        "from opentelemetry",
        "import openai",
        "from openai",
        "import langchain",
        "from langchain",
        "import llama_index",
        "from llama_index",
        "import crewai",
        "from crewai",
        "import fastapi",
        "from fastapi",
        "import httpx",
        "from httpx",
    )
    core_roots = (
        Path("src/actionlineage/domain"),
        Path("src/actionlineage/journal"),
        Path("src/actionlineage/projection"),
        Path("src/actionlineage/cli.py"),
    )

    for root in core_roots:
        paths = (root,) if root.is_file() else tuple(root.rglob("*.py"))
        for path in paths:
            text = path.read_text(encoding="utf-8")
            assert not any(token in text for token in forbidden), path


def _descriptor() -> McpToolDescriptor:
    return McpToolDescriptor(
        server_identity="demo-mcp-server",
        name="safe_http.send",
        description="Send to the local receiver fixture",
        input_schema={"type": "object"},
    )


def _normalizer(*event_ids: str) -> EvidenceNormalizer:
    return EvidenceNormalizer(
        correlation=Correlation(trace_id="trace_mcp", run_id="run_mcp"),
        source=Source(component="mcp-adapter", instance_id="adapter_01", version="1.0.0"),
        principal=Principal(principal_id="agent_demo", principal_type=PrincipalType.AGENT),
        classification=Classification(sensitivity=Sensitivity.INTERNAL, trust=TrustLevel.LOCAL),
        clock=FixedClock(BASE_TIME),
        id_generator=FixedIdGenerator(event_ids),
    )
