from __future__ import annotations

from actionlineage.adapters import (
    FrameworkAcknowledgementStatus,
    FrameworkKind,
    FrameworkToolDescriptor,
    FrameworkToolInvocation,
    framework_descriptor_hash,
    framework_lifecycle_records,
    framework_tool_identity,
)
from actionlineage.domain import EventType, ResourceType
from actionlineage.evidence import DelegatedIdentity, NormalizedResource


def test_framework_descriptor_hash_is_stable_for_equivalent_json_ordering() -> None:
    descriptor_a = FrameworkToolDescriptor(
        framework=FrameworkKind.OPENAI_AGENTS,
        tool_name="send_report",
        description="Send a report to a receiver",
        input_schema={
            "type": "object",
            "properties": {"url": {"type": "string"}, "body": {"type": "string"}},
            "required": ["url"],
        },
        version="1",
    )
    descriptor_b = FrameworkToolDescriptor(
        framework=FrameworkKind.OPENAI_AGENTS,
        tool_name="send_report",
        description="Send a report to a receiver",
        input_schema={
            "required": ["url"],
            "properties": {"body": {"type": "string"}, "url": {"type": "string"}},
            "type": "object",
        },
        version="1",
    )

    assert framework_descriptor_hash(descriptor_a) == framework_descriptor_hash(descriptor_b)


def test_framework_tool_identity_distinguishes_non_mcp_adapters() -> None:
    descriptor = _descriptor(framework=FrameworkKind.LANGCHAIN)
    identity = framework_tool_identity(descriptor)

    assert identity["adapter"] == "framework"
    assert identity["framework"] == "langchain"
    assert identity["name"] == "safe_http.send"
    assert str(identity["descriptor_hash"]).startswith("sha256:")


def test_framework_lifecycle_records_preserve_neutral_tool_states() -> None:
    records = framework_lifecycle_records(
        _invocation(framework=FrameworkKind.LLAMAINDEX),
        acknowledgement_status=FrameworkAcknowledgementStatus.SUCCEEDED,
        result_digest="sha256:result",
        result_summary={"status": "accepted"},
    )

    assert [record.event_type for record in records] == [
        EventType.TOOL_EXECUTION_REQUESTED,
        EventType.TOOL_EXECUTION_DISPATCHED,
        EventType.TOOL_EXECUTION_ACKNOWLEDGED,
    ]
    assert records[0].payload["action"]["tool_identity"]["adapter"] == "framework:llamaindex"
    assert records[2].payload["acknowledgement"]["side_effect_status"] == "unverified"
    assert "not side-effect verification" in records[2].payload["acknowledgement"]["note"]


def test_framework_not_dispatched_records_are_not_forwarded() -> None:
    records = framework_lifecycle_records(
        _invocation(framework=FrameworkKind.CREWAI),
        not_dispatched_reason="policy_deny",
    )

    assert [record.event_type for record in records] == [
        EventType.TOOL_EXECUTION_REQUESTED,
        EventType.TOOL_EXECUTION_NOT_DISPATCHED,
    ]
    assert records[1].payload["not_dispatched"]["downstream_forwarded"] is False
    assert records[1].payload["not_dispatched"]["reason"] == "policy_deny"


def test_shell_and_browser_tools_use_same_transport_neutral_identity_model() -> None:
    shell = _descriptor(framework=FrameworkKind.SHELL, tool_name="shell.run")
    browser = _descriptor(framework=FrameworkKind.BROWSER, tool_name="browser.click")

    assert framework_tool_identity(shell)["framework"] == "shell"
    assert framework_tool_identity(browser)["framework"] == "browser"
    assert framework_descriptor_hash(shell) != framework_descriptor_hash(browser)


def _descriptor(
    *,
    framework: FrameworkKind,
    tool_name: str = "safe_http.send",
) -> FrameworkToolDescriptor:
    return FrameworkToolDescriptor(
        framework=framework,
        server_identity="demo-agent-runtime",
        tool_name=tool_name,
        description="Send to the local receiver fixture",
        input_schema={"type": "object", "properties": {"url": {"type": "string"}}},
        metadata={"package": framework.value},
        version="1",
    )


def _invocation(*, framework: FrameworkKind) -> FrameworkToolInvocation:
    return FrameworkToolInvocation(
        descriptor=_descriptor(framework=framework),
        invocation_id="call_1",
        action_type="http.send",
        arguments_digest="sha256:arguments",
        resources=(
            NormalizedResource(
                resource_type=ResourceType.URL,
                identifier="https://receiver.example.invalid/ingest",
                attributes={"trust": "untrusted"},
            ),
        ),
        delegated_identity=DelegatedIdentity(
            initiating_principal_id="agent_demo",
            executing_principal_id="svc_demo",
            credential_id="cred_demo",
            scopes=("send:demo",),
        ),
    )
