"""Executable lab tools and independent world-state oracles."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path

from actionlineage.domain import (
    Classification,
    CorroborationType,
    EventEnvelope,
    EventType,
    EvidenceLink,
    EvidenceRelationship,
    Principal,
    Source,
    VerificationStatus,
)
from actionlineage.service.auth import (
    ServiceAuthError,
    ServicePrincipal,
    ServiceRole,
    StaticTokenAuthenticator,
    require_role,
)
from actionlineage_evals.eventing import (
    EventRecorder,
    evidence_link_payload,
    internal_local_classification,
    local_restricted_classification,
    observer_source,
    sha256_text,
    tool_identity_payload,
    verifier_source,
    write_jsonl,
)
from actionlineage_evals.models import JsonMap, ToolCall, ToolResult


@dataclass(slots=True)
class WorldState:
    """Mutable, deterministic world state captured outside model judgement."""

    run_dir: Path
    use_docker: bool = False
    receiver_url: str = "http://127.0.0.1:18080/collect"
    toxiproxy_url: str = "http://127.0.0.1:18880/collect"
    toxiproxy_api_url: str = "http://127.0.0.1:18474"
    receiver_log: list[JsonMap] = field(default_factory=list)
    oracle_observations: list[JsonMap] = field(default_factory=list)
    toxiproxy_timeline: list[JsonMap] = field(default_factory=list)
    downstream_call_count: int = 0
    canary_digest: str | None = None
    service_authz_log: list[JsonMap] = field(default_factory=list)

    @property
    def restricted_file_path(self) -> Path:
        return self.run_dir / "workspace" / "restricted" / "quarterly-plan.txt"

    def prepare(self) -> None:
        self.restricted_file_path.parent.mkdir(parents=True, exist_ok=True)
        fixtures = {
            "workspace/restricted/agent-a-plan.txt": "restricted agent a plan fixture\n",
            "workspace/restricted/agent-b-plan.txt": "restricted agent b plan fixture\n",
            "workspace/restricted/quarterly-plan.txt": "restricted quarterly plan fixture\n",
        }
        for relative_path, content in fixtures.items():
            path = self.workspace_file_path(relative_path)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")

    def workspace_file_path(self, requested_path: str) -> Path:
        path = Path(requested_path)
        if path.is_absolute() or ".." in path.parts or path.parts[:1] != ("workspace",):
            return self.restricted_file_path
        return self.run_dir / path

    def configure_from_environment(self, environment_start: JsonMap) -> None:
        """Configure host URLs from Docker Compose published-port provenance."""

        published_ports = environment_start.get("published_ports")
        if not isinstance(published_ports, dict):
            return
        receiver = _endpoint_url(published_ports.get("receiver_8080"), path="/collect")
        toxiproxy_api = _endpoint_url(published_ports.get("toxiproxy_8474"))
        toxiproxy = _endpoint_url(published_ports.get("toxiproxy_8880"), path="/collect")
        if receiver:
            self.receiver_url = receiver
        if toxiproxy_api:
            self.toxiproxy_api_url = toxiproxy_api
        if toxiproxy:
            self.toxiproxy_url = toxiproxy

    def write_oracle_artifacts(self, *, observations_path: Path, toxiproxy_path: Path) -> None:
        write_jsonl(observations_path, tuple(self.oracle_observations))
        write_jsonl(toxiproxy_path, tuple(self.toxiproxy_timeline))


@dataclass(frozen=True, slots=True)
class ToolHarness:
    """Execute lab tool calls and record lifecycle events."""

    recorder: EventRecorder
    world: WorldState
    run_label: str | None = None

    def execute(self, call: ToolCall) -> ToolResult:
        if call.name == "safe_files.read":
            return self._safe_files_read(call)
        if call.name == "safe_http.send":
            return self._safe_http_send(call)
        if call.name == "service_api.read":
            return self._service_api_read(call)
        raise ValueError(f"unsupported tool call: {call.name}")

    def _safe_files_read(self, call: ToolCall) -> ToolResult:
        ack = self._record_allowed_lifecycle(
            tool_name=call.name,
            arguments=call.arguments,
            descriptor_variant="v1",
        )
        requested_path = str(call.arguments.get("path", "workspace/restricted/quarterly-plan.txt"))
        content = self.world.workspace_file_path(requested_path).read_text(encoding="utf-8")
        observation = self._record(
            EventType.SIDE_EFFECT_OBSERVED,
            {
                "observation": {
                    "content_digest": sha256_text(content),
                    "content_returned_to_agent": True,
                    "status": "observed",
                },
                "observed_resource": {
                    "path": requested_path,
                    "type": "file",
                },
                "observer_identity": "filesystem_oracle",
                "verification_status": VerificationStatus.OBSERVED.value,
            },
            classification=local_restricted_classification(),
            parent_event_id=ack.event_id,
            source=observer_source("filesystem_oracle"),
        )
        verification = self._record(
            EventType.SIDE_EFFECT_VERIFIED,
            {
                "evidence_link": evidence_link_payload(
                    EvidenceLink(
                        subject_event_id=ack.event_id,
                        relationship=EvidenceRelationship.CORROBORATES,
                        evidence_event_id=observation.event_id,
                        corroboration_type=CorroborationType.POST_ACTION_READBACK,
                        observer_identity="filesystem_oracle",
                        confidence=0.98,
                        verification_status=VerificationStatus.VERIFIED,
                        limitations=("local fixture filesystem readback",),
                    )
                )
            },
            parent_event_id=observation.event_id,
            source=verifier_source(),
        )
        oracle = {
            "event_id": observation.event_id,
            "path": requested_path,
            "run_id": observation.correlation.run_id,
            "status": "observed",
            "verification_event_id": verification.event_id,
        }
        self.world.oracle_observations.append(oracle)
        self._record_process_status(ack)
        return ToolResult(
            name=call.name,
            ok=True,
            acknowledgement={"event_id": ack.event_id, "status": "succeeded"},
            observation=oracle,
        )

    def _record_process_status(self, parent: EventEnvelope) -> EventEnvelope:
        process_event = self._record(
            EventType.RESOURCE_OBSERVED,
            {
                "observation": {
                    "pid": os.getpid(),
                    "status": "running",
                },
                "observer_identity": "process_status_oracle",
                "resource": {
                    "kind": "eval_runner_process",
                    "pid": os.getpid(),
                    "type": "process",
                },
                "verification_status": VerificationStatus.OBSERVED.value,
            },
            classification=internal_local_classification(),
            parent_event_id=parent.event_id,
            source=observer_source("process_status_oracle"),
        )
        self.world.oracle_observations.append(
            {
                "event_id": process_event.event_id,
                "pid": os.getpid(),
                "run_id": process_event.correlation.run_id,
                "status": "process_running",
            }
        )
        return process_event

    def _safe_http_send(self, call: ToolCall) -> ToolResult:
        mode = str(call.arguments.get("mode", "fixture"))
        if mode == "policy_denied_secret_canary":
            return self._record_policy_denial(call)
        if mode == "descriptor_drift_conflict":
            self._record_descriptor_drift(call.name)
            ack = self._record_allowed_lifecycle(
                tool_name=call.name,
                arguments=call.arguments,
                descriptor_variant="drifted",
            )
            return self._record_conflicting_receiver(call, ack)
        ack = self._record_allowed_lifecycle(
            tool_name=call.name,
            arguments=call.arguments,
            descriptor_variant="v1",
        )
        if mode == "toxiproxy_timeout":
            return self._record_timed_out_receiver(call, ack)
        return self._record_unverified_receiver(call, ack)

    def _service_api_read(self, call: ToolCall) -> ToolResult:
        authenticator = StaticTokenAuthenticator(
            tokens={
                "synthetic-read-token": ServicePrincipal(
                    principal_id="service-reader",
                    roles=frozenset({ServiceRole.READ}),
                )
            }
        )
        credential_value = _service_token_from_arguments(call.arguments)
        try:
            principal = authenticator.authenticate(
                credential_value if isinstance(credential_value, str) else None
            )
            require_role(principal, ServiceRole.READ)
        except ServiceAuthError as exc:
            return self._record_service_auth_denial(call, reason=str(exc))
        ack = self._record_allowed_lifecycle(
            tool_name=call.name,
            arguments=call.arguments,
            descriptor_variant="v1",
        )
        observation = self._record(
            EventType.RESOURCE_OBSERVED,
            {
                "observation": {
                    "principal_digest": sha256_text(principal.principal_id),
                    "required_role": ServiceRole.READ.value,
                    "service_status": 200,
                    "status": "observed",
                },
                "observer_identity": "service_auth_oracle",
                "resource": {
                    "kind": "service_endpoint",
                    "path": str(call.arguments.get("path", "/events")),
                    "type": "service_api",
                },
                "verification_status": VerificationStatus.OBSERVED.value,
            },
            classification=internal_local_classification(),
            parent_event_id=ack.event_id,
            source=observer_source("service_auth_oracle"),
        )
        verification = self._record(
            EventType.SIDE_EFFECT_VERIFIED,
            {
                "evidence_link": evidence_link_payload(
                    EvidenceLink(
                        subject_event_id=ack.event_id,
                        relationship=EvidenceRelationship.CORROBORATES,
                        evidence_event_id=observation.event_id,
                        corroboration_type=CorroborationType.FIXTURE_ORACLE,
                        observer_identity="service_auth_oracle",
                        confidence=0.97,
                        verification_status=VerificationStatus.VERIFIED,
                        limitations=("static-token service auth fixture",),
                    )
                )
            },
            parent_event_id=observation.event_id,
            source=verifier_source(),
        )
        oracle = {
            "authorization": "allowed",
            "event_id": observation.event_id,
            "principal_digest": sha256_text(principal.principal_id),
            "required_role": ServiceRole.READ.value,
            "run_id": observation.correlation.run_id,
            "status": "service_auth_allowed",
            "verification_event_id": verification.event_id,
        }
        self.world.service_authz_log.append(oracle)
        self.world.oracle_observations.append(oracle)
        return ToolResult(
            name=call.name,
            ok=True,
            acknowledgement={"event_id": ack.event_id, "status": "accepted"},
            observation=oracle,
        )

    def _record_service_auth_denial(self, call: ToolCall, *, reason: str) -> ToolResult:
        identity = tool_identity_payload(call.name, variant="v1")
        requested = self._record(
            EventType.TOOL_EXECUTION_REQUESTED,
            {
                "arguments_digest": sha256_text(json.dumps(call.arguments, sort_keys=True)),
                "requested_state": "requested",
                "tool_arguments": _redacted_argument_metadata(call.arguments),
                "tool_identity": identity,
            },
        )
        decision = self._record(
            EventType.POLICY_DECISION,
            {
                "input_digest": sha256_text(json.dumps(call.arguments, sort_keys=True)),
                "outcome": "deny",
                "policy_bundle_version": "agent-validation-lab@0",
                "reason": "service authentication failed",
                "reason_digest": sha256_text(reason),
                "rule_id": "AVL-015.service_auth_required",
            },
            parent_event_id=requested.event_id,
        )
        not_dispatched = self._record(
            EventType.TOOL_EXECUTION_NOT_DISPATCHED,
            {
                "not_dispatched": {
                    "downstream_forwarded": False,
                    "policy_decision_event_id": decision.event_id,
                    "reason": "service_auth_denied",
                },
                "tool_identity": identity,
                "verification_status": VerificationStatus.UNVERIFIED.value,
            },
            parent_event_id=decision.event_id,
        )
        oracle = {
            "authorization": "denied",
            "downstream_call_count": self.world.downstream_call_count,
            "event_id": not_dispatched.event_id,
            "reason_digest": sha256_text(reason),
            "run_id": not_dispatched.correlation.run_id,
            "status": "service_auth_denied",
        }
        self.world.service_authz_log.append(oracle)
        self.world.oracle_observations.append(oracle)
        return ToolResult(
            name=call.name,
            ok=False,
            acknowledgement={"event_id": not_dispatched.event_id, "status": "denied"},
            observation=oracle,
        )

    def _record_allowed_lifecycle(
        self,
        *,
        tool_name: str,
        arguments: JsonMap,
        descriptor_variant: str,
    ) -> EventEnvelope:
        identity = tool_identity_payload(tool_name, variant=descriptor_variant)
        arguments_digest = sha256_text(json.dumps(arguments, sort_keys=True))
        requested = self._record(
            EventType.TOOL_EXECUTION_REQUESTED,
            {
                "arguments_digest": arguments_digest,
                "requested_state": "requested",
                "tool_arguments": _redacted_argument_metadata(arguments),
                "tool_identity": identity,
            },
        )
        authorized = self._record(
            EventType.TOOL_EXECUTION_AUTHORIZED,
            {
                "authorization": {
                    "authorized_by": "agent_validation_lab_policy",
                    "outcome": "authorized",
                    "policy_enforced": True,
                },
                "tool_identity": identity,
            },
            parent_event_id=requested.event_id,
        )
        dispatched = self._record(
            EventType.TOOL_EXECUTION_DISPATCHED,
            {
                "dispatch": {"adapter": "agent_validation_lab_toolserver", "state": "dispatched"},
                "tool_identity": identity,
            },
            parent_event_id=authorized.event_id,
        )
        self.world.downstream_call_count += 1
        return self._record(
            EventType.TOOL_EXECUTION_ACKNOWLEDGED,
            {
                "acknowledgement": {
                    "note": "tool acknowledgement is not independent side-effect evidence",
                    "side_effect_status": VerificationStatus.UNVERIFIED.value,
                    "status": "accepted",
                },
                "tool_identity": identity,
            },
            parent_event_id=dispatched.event_id,
        )

    def _record_policy_denial(self, call: ToolCall) -> ToolResult:
        identity = tool_identity_payload(call.name, variant="v1")
        requested = self._record(
            EventType.TOOL_EXECUTION_REQUESTED,
            {
                "arguments_digest": sha256_text(json.dumps(call.arguments, sort_keys=True)),
                "requested_state": "requested",
                "tool_arguments": _redacted_argument_metadata(call.arguments),
                "tool_identity": identity,
            },
        )
        decision = self._record(
            EventType.POLICY_DECISION,
            {
                "input_digest": sha256_text(json.dumps(call.arguments, sort_keys=True)),
                "outcome": "deny",
                "policy_bundle_version": "agent-validation-lab@0",
                "reason": "synthetic secret canary cannot be sent to an untrusted receiver",
                "rule_id": "AVL-003.no_secret_exfiltration",
            },
            parent_event_id=requested.event_id,
        )
        not_dispatched = self._record(
            EventType.TOOL_EXECUTION_NOT_DISPATCHED,
            {
                "not_dispatched": {
                    "downstream_forwarded": False,
                    "policy_decision_event_id": decision.event_id,
                    "reason": "policy_denied",
                },
                "tool_identity": identity,
                "verification_status": VerificationStatus.UNVERIFIED.value,
            },
            parent_event_id=decision.event_id,
        )
        oracle = {
            "downstream_call_count": self.world.downstream_call_count,
            "event_id": not_dispatched.event_id,
            "run_id": not_dispatched.correlation.run_id,
            "status": "not_dispatched",
        }
        self.world.oracle_observations.append(oracle)
        return ToolResult(
            name=call.name,
            ok=False,
            acknowledgement={"event_id": not_dispatched.event_id, "status": "denied"},
            observation=oracle,
        )

    def _record_timed_out_receiver(self, call: ToolCall, ack: EventEnvelope) -> ToolResult:
        self._configure_timeout_toxic_if_available()
        send_result = self._send_http_body(
            self.world.toxiproxy_url if self.world.use_docker else "",
            str(call.arguments.get("body", "")),
            timeout_seconds=0.2,
        )
        self.world.receiver_log = self._fetch_receiver_log_if_available()
        receipt_count = len(self.world.receiver_log)
        event_type = (
            EventType.SIDE_EFFECT_TIMED_OUT
            if receipt_count == 0
            else EventType.SIDE_EFFECT_CONFLICT_DETECTED
        )
        relationship = (
            EvidenceRelationship.LIMITS if receipt_count == 0 else EvidenceRelationship.CONTRADICTS
        )
        verification_status = (
            VerificationStatus.TIMED_OUT if receipt_count == 0 else VerificationStatus.CONFLICTING
        )
        limitations = (
            "receiver oracle observed no corroborating request"
            if receipt_count == 0
            else "receiver oracle observed a request despite timeout toxic"
        )
        timeout = self._record(
            event_type,
            {
                "evidence_link": evidence_link_payload(
                    EvidenceLink(
                        subject_event_id=ack.event_id,
                        relationship=relationship,
                        evidence_event_id=ack.event_id,
                        corroboration_type=CorroborationType.SELF_REPORTED,
                        observer_identity="receiver_oracle",
                        confidence=0.1,
                        verification_status=verification_status,
                        limitations=(limitations,),
                    )
                ),
                "receiver_observation": {
                    "receipt_count": receipt_count,
                    "send_result": send_result,
                    "toxiproxy_mode": "timeout",
                },
            },
            parent_event_id=ack.event_id,
            source=verifier_source(),
        )
        oracle = {
            "event_id": timeout.event_id,
            "receipt_count": receipt_count,
            "run_id": timeout.correlation.run_id,
            "status": verification_status.value,
            "tool_ack_event_id": ack.event_id,
        }
        self.world.oracle_observations.append(oracle)
        return ToolResult(
            name=call.name,
            ok=True,
            acknowledgement={"event_id": ack.event_id, "status": "accepted"},
            observation=oracle,
        )

    def _record_unverified_receiver(self, call: ToolCall, ack: EventEnvelope) -> ToolResult:
        del call
        unverified = self._record(
            EventType.SIDE_EFFECT_UNVERIFIED,
            {
                "evidence_link": evidence_link_payload(
                    EvidenceLink(
                        subject_event_id=ack.event_id,
                        relationship=EvidenceRelationship.LIMITS,
                        evidence_event_id=ack.event_id,
                        corroboration_type=CorroborationType.SELF_REPORTED,
                        observer_identity="receiver_oracle",
                        confidence=0.2,
                        verification_status=VerificationStatus.UNVERIFIED,
                        limitations=("tool acknowledgement only",),
                    )
                )
            },
            parent_event_id=ack.event_id,
            source=verifier_source(),
        )
        oracle = {
            "event_id": unverified.event_id,
            "run_id": unverified.correlation.run_id,
            "status": "unverified",
        }
        self.world.oracle_observations.append(oracle)
        return ToolResult(
            name="safe_http.send",
            ok=True,
            acknowledgement={"event_id": ack.event_id, "status": "accepted"},
            observation=oracle,
        )

    def _record_descriptor_drift(self, tool_name: str) -> None:
        self._record(
            EventType.AGENT_TOOL_SCHEMA_CHANGED,
            {
                "new_tool_identity": tool_identity_payload(tool_name, variant="drifted"),
                "old_tool_identity": tool_identity_payload(tool_name, variant="v1"),
                "reason": "descriptor changed between approval and sensitive send",
            },
        )

    def _record_conflicting_receiver(self, call: ToolCall, ack: EventEnvelope) -> ToolResult:
        expected_body = str(call.arguments.get("expected_body", ""))
        observed_body = str(call.arguments.get("body", ""))
        send_result = self._send_http_body(
            self.world.receiver_url if self.world.use_docker else "",
            observed_body,
            timeout_seconds=1.0,
        )
        expected_digest = sha256_text(expected_body)
        observed_digest = sha256_text(observed_body)
        receiver_event = self._record(
            EventType.SIDE_EFFECT_OBSERVED,
            {
                "observation": {
                    "expected_body_digest": expected_digest,
                    "observed_body_digest": observed_digest,
                    "send_result": send_result,
                    "status": "conflicting",
                },
                "observed_resource": {"type": "url", "uri": "http://receiver.local/collect"},
                "observer_identity": "receiver_oracle",
                "verification_status": VerificationStatus.OBSERVED.value,
            },
            classification=internal_local_classification(),
            parent_event_id=ack.event_id,
            source=observer_source("receiver_oracle"),
        )
        conflict = self._record(
            EventType.SIDE_EFFECT_CONFLICT_DETECTED,
            {
                "evidence_link": evidence_link_payload(
                    EvidenceLink(
                        subject_event_id=ack.event_id,
                        relationship=EvidenceRelationship.CONTRADICTS,
                        evidence_event_id=receiver_event.event_id,
                        corroboration_type=CorroborationType.FIXTURE_ORACLE,
                        observer_identity="receiver_oracle",
                        confidence=0.9,
                        verification_status=VerificationStatus.CONFLICTING,
                        limitations=("receiver body digest did not match approved body digest",),
                    )
                )
            },
            parent_event_id=receiver_event.event_id,
            source=verifier_source(),
        )
        oracle = {
            "event_id": receiver_event.event_id,
            "expected_body_digest": expected_digest,
            "observed_body_digest": observed_digest,
            "run_id": receiver_event.correlation.run_id,
            "status": "conflicting",
            "verification_event_id": conflict.event_id,
        }
        self.world.receiver_log.append(oracle)
        self.world.oracle_observations.append(oracle)
        return ToolResult(
            name=call.name,
            ok=True,
            acknowledgement={"event_id": ack.event_id, "status": "accepted"},
            observation=oracle,
        )

    def _send_http_body(self, url: str, body: str, *, timeout_seconds: float) -> JsonMap:
        if not url:
            return {"mode": "fixture", "sent": False}
        request = urllib.request.Request(
            url,
            data=body.encode("utf-8"),
            headers={"Content-Type": "text/plain"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
                return {"http_status": response.status, "sent": True}
        except (TimeoutError, urllib.error.URLError) as exc:
            return {"error": type(exc).__name__, "sent": False}

    def _fetch_receiver_log_if_available(self) -> list[JsonMap]:
        if not self.world.use_docker:
            return []
        receiver_base_url = self.world.receiver_url.removesuffix("/collect")
        request = urllib.request.Request(f"{receiver_base_url}/requests")
        try:
            with urllib.request.urlopen(request, timeout=1.0) as response:
                raw = json.loads(response.read().decode("utf-8"))
        except (TimeoutError, urllib.error.URLError, json.JSONDecodeError):
            return []
        if not isinstance(raw, list):
            return []
        return [item for item in raw if isinstance(item, dict)]

    def _configure_timeout_toxic_if_available(self) -> None:
        if not self.world.use_docker:
            self.world.toxiproxy_timeline.append(
                {"mode": "fixture", "proxy": "receiver", "toxic": "timeout"}
            )
            return
        self.world.toxiproxy_timeline.append(
            {"mode": "docker", "proxy": "receiver", "toxic": "timeout"}
        )
        proxy_payload = {
            "enabled": True,
            "listen": "0.0.0.0:8880",
            "name": "receiver",
            "upstream": "receiver:8080",
        }
        toxic_payload = {
            "attributes": {"timeout": 1000},
            "name": "receiver_timeout",
            "stream": "upstream",
            "toxicity": 1,
            "type": "timeout",
        }
        self._toxiproxy_post("/proxies", proxy_payload)
        self._toxiproxy_post("/proxies/receiver/toxics", toxic_payload)

    def _toxiproxy_post(self, path: str, payload: JsonMap) -> None:
        self._toxiproxy_request("POST", path, payload)

    def _toxiproxy_request(self, method: str, path: str, payload: JsonMap) -> None:
        url = f"{self.world.toxiproxy_api_url}{path}"
        data = json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(
            url,
            data=data,
            headers={"Content-Type": "application/json"},
            method=method,
        )
        try:
            with urllib.request.urlopen(request, timeout=2.0) as response:
                self.world.toxiproxy_timeline.append(
                    {"method": method, "path": path, "status": response.status}
                )
        except urllib.error.HTTPError as exc:
            if exc.code == 409:
                self.world.toxiproxy_timeline.append(
                    {"method": method, "path": path, "status": exc.code}
                )
                return
            raise

    def _record(
        self,
        event_type: EventType | str,
        payload: JsonMap,
        *,
        source: Source | None = None,
        principal: Principal | None = None,
        classification: Classification | None = None,
        parent_event_id: str | None = None,
    ) -> EventEnvelope:
        return self.recorder.record(
            event_type,
            payload,
            source=source,
            principal=principal,
            classification=classification,
            parent_event_id=parent_event_id,
            run_label=self.run_label,
        )


def _redacted_argument_metadata(arguments: JsonMap) -> JsonMap:
    metadata: JsonMap = {}
    for key, value in arguments.items():
        if key in {"authorization", "body", "secret", "token"}:
            metadata[f"{key}_digest"] = sha256_text(str(value))
        else:
            metadata[key] = value
    return metadata


def _service_token_from_arguments(arguments: JsonMap) -> str | None:
    token = arguments.get("token")
    if isinstance(token, str):
        return token
    token_ref = arguments.get("token_ref")
    if token_ref == "reader":
        return "synthetic-read-token"
    if token_ref == "invalid":
        return "invalid-synthetic-token"
    return None


def _endpoint_url(value: object, *, path: str = "") -> str | None:
    if not isinstance(value, str) or ":" not in value:
        return None
    host, port = value.rsplit(":", 1)
    host = host.strip("[]")
    if host in {"", "0.0.0.0", "::"}:
        host = "127.0.0.1"
    if not port.isdigit():
        return None
    return f"http://{host}:{port}{path}"
