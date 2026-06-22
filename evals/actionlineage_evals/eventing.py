"""Event construction helpers for eval scenario runs."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import cast

from actionlineage.adapters.mcp.descriptors import McpToolDescriptor, descriptor_hash
from actionlineage.domain import (
    Classification,
    Correlation,
    EventEnvelope,
    EventType,
    EvidenceLink,
    FixedClock,
    Principal,
    PrincipalType,
    RedactionPolicy,
    Sensitivity,
    Source,
    TrustLevel,
    deterministic_json_bytes,
)
from actionlineage.domain.events import JsonObject
from actionlineage.evidence import EvidenceNormalizer
from actionlineage.journal import LocalJournal
from actionlineage_evals.models import JsonMap

EVAL_TIME = datetime(2026, 6, 22, 12, 0, tzinfo=UTC)


@dataclass(slots=True)
class SequentialIdGenerator:
    """Deterministic ID generator scoped to one eval run."""

    scenario_id: str
    seed: int
    index: int = 0

    def new_id(self, prefix: str) -> str:
        value = f"{prefix}_{self.scenario_id.lower()}_{self.seed:04d}_{self.index:03d}"
        self.index += 1
        return value


@dataclass(slots=True)
class EventRecorder:
    """Append eval events through the ActionLineage journal boundary."""

    scenario_id: str
    seed: int
    journal_path: Path
    _events: list[EventEnvelope] | None = None
    _normalizer: EvidenceNormalizer | None = None
    _journal: LocalJournal | None = None

    def __post_init__(self) -> None:
        self.journal_path.parent.mkdir(parents=True, exist_ok=True)
        self.journal_path.unlink(missing_ok=True)
        correlation = Correlation(
            trace_id=f"trace_{self.scenario_id.lower()}_{self.seed:04d}",
            run_id=f"run_{self.scenario_id.lower()}_{self.seed:04d}",
        )
        source = Source(
            component="agent_validation_lab",
            instance_id=f"{self.scenario_id.lower()}-{self.seed}",
            version="0",
        )
        principal = Principal(
            principal_id="agent_validation_lab_agent",
            principal_type=PrincipalType.AGENT,
            on_behalf_of="agent_validation_lab_user",
            credential_id="none",
        )
        classification = Classification(sensitivity=Sensitivity.INTERNAL, trust=TrustLevel.LOCAL)
        self._events = []
        self._normalizer = EvidenceNormalizer(
            correlation=correlation,
            source=source,
            principal=principal,
            classification=classification,
            clock=FixedClock(EVAL_TIME),
            id_generator=SequentialIdGenerator(self.scenario_id, self.seed),
        )
        self._journal = LocalJournal(
            self.journal_path,
            redaction_policy=RedactionPolicy.from_paths(
                (
                    "payload.intent.prompt",
                    "payload.untrusted_input.raw",
                    "payload.tool_arguments.body",
                    "payload.tool_arguments.secret",
                )
            ),
        )

    @property
    def events(self) -> tuple[EventEnvelope, ...]:
        return tuple(self._require_events())

    @property
    def run_id(self) -> str:
        return self._require_normalizer().correlation.run_id

    @property
    def trace_id(self) -> str:
        return self._require_normalizer().correlation.trace_id

    def record(
        self,
        event_type: EventType | str,
        payload: JsonMap,
        *,
        source: Source | None = None,
        principal: Principal | None = None,
        classification: Classification | None = None,
        parent_event_id: str | None = None,
    ) -> EventEnvelope:
        """Record one event and return the persisted hashed event."""

        event = self._require_normalizer().record(
            event_type,
            cast(JsonObject, payload),
            source=source,
            principal=principal,
            classification=classification,
            parent_event_id=parent_event_id,
        )
        persisted = self._require_journal().append(event)
        self._require_events().append(persisted)
        return persisted

    def record_intent(self, *, prompt: str, scenario_id: str) -> EventEnvelope:
        return self.record(
            EventType.AGENT_INTENT_RECORDED,
            {
                "intent": {
                    "prompt_digest": sha256_text(prompt),
                    "scenario_id": scenario_id,
                    "summary": f"run agent validation scenario {scenario_id}",
                }
            },
            principal=Principal(
                principal_id="agent_validation_lab_user",
                principal_type=PrincipalType.HUMAN,
            ),
        )

    def record_run_started(self, *, mode: str, provider: str, model_id: str) -> EventEnvelope:
        return self.record(
            EventType.AGENT_RUN_STARTED,
            {
                "run": {
                    "mode": mode,
                    "model_id": model_id,
                    "model_provider": provider,
                    "scenario_id": self.scenario_id,
                }
            },
        )

    def record_run_completed(self, *, passed: bool) -> EventEnvelope:
        return self.record(
            EventType.AGENT_RUN_COMPLETED,
            {"run": {"passed": passed, "scenario_id": self.scenario_id}},
        )

    def record_run_failed(
        self,
        *,
        error_type: str,
        message: str,
        parent_event_id: str | None = None,
    ) -> EventEnvelope:
        return self.record(
            EventType.AGENT_RUN_FAILED,
            {
                "run": {
                    "error_message_digest": sha256_text(message),
                    "error_type": error_type,
                    "scenario_id": self.scenario_id,
                }
            },
            parent_event_id=parent_event_id,
        )

    def _require_events(self) -> list[EventEnvelope]:
        if self._events is None:
            raise RuntimeError("event recorder not initialized")
        return self._events

    def _require_normalizer(self) -> EvidenceNormalizer:
        if self._normalizer is None:
            raise RuntimeError("event recorder not initialized")
        return self._normalizer

    def _require_journal(self) -> LocalJournal:
        if self._journal is None:
            raise RuntimeError("event recorder not initialized")
        return self._journal


def tool_descriptor(tool_name: str, *, variant: str = "v1") -> McpToolDescriptor:
    """Return a deterministic descriptor for a lab tool."""

    return McpToolDescriptor(
        server_identity="actionlineage-eval-toolserver",
        name=tool_name,
        description=f"Agent Validation Lab tool {tool_name} ({variant})",
        input_schema={
            "additionalProperties": False,
            "properties": {
                "body": {"type": "string"},
                "mode": {"type": "string"},
                "path": {"type": "string"},
                "url": {"type": "string"},
            },
            "type": "object",
        },
        annotations={"development_only": True, "variant": variant},
        metadata={"lab": "agent_validation", "variant": variant},
    )


def tool_identity_payload(tool_name: str, *, variant: str = "v1") -> JsonMap:
    descriptor = tool_descriptor(tool_name, variant=variant)
    return {
        "adapter": "mcp",
        "descriptor_hash": descriptor_hash(descriptor),
        "name": descriptor.name,
        "server_identity": descriptor.server_identity,
    }


def evidence_link_payload(link: EvidenceLink) -> JsonMap:
    return cast(JsonMap, link.as_payload())


def sha256_text(value: str) -> str:
    return f"sha256:{hashlib.sha256(value.encode('utf-8')).hexdigest()}"


def sha256_object(value: JsonMap) -> str:
    return f"sha256:{hashlib.sha256(deterministic_json_bytes(cast(JsonObject, value))).hexdigest()}"


def write_json(path: Path, value: JsonMap) -> None:
    """Write a deterministic JSON object with a trailing newline."""

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )


def write_jsonl(path: Path, values: tuple[JsonMap, ...]) -> None:
    """Write deterministic JSONL."""

    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [json.dumps(value, sort_keys=True, allow_nan=False) for value in values]
    path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")


def observer_source(component: str) -> Source:
    return Source(component=component, instance_id="agent_validation_lab", version="0")


def verifier_source() -> Source:
    return Source(component="agent_validation_lab_verifier", instance_id="local", version="0")


def local_restricted_classification() -> Classification:
    return Classification(sensitivity=Sensitivity.RESTRICTED, trust=TrustLevel.LOCAL)


def internal_local_classification() -> Classification:
    return Classification(sensitivity=Sensitivity.INTERNAL, trust=TrustLevel.LOCAL)
