"""Typed development-only models for the Agent Validation Lab."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Any, Literal, Protocol

type JsonMap = dict[str, Any]


class FailureClass(StrEnum):
    """Distinct failure classes reported by scenario scorers."""

    PRODUCT = "product_failure"
    AGENT = "agent_failure"
    HARNESS = "harness_failure"
    PROVIDER = "provider_failure"
    BUDGET = "inconclusive_budget_exhausted"


class RunMode(StrEnum):
    """Supported eval execution modes."""

    SCRIPTED = "scripted"
    LIVE = "live"
    REPLAY = "replay"


type ModelAdapterName = Literal[
    "replay",
    "github_models",
    "openai_compatible",
    "ollama",
    "scripted",
]


@dataclass(frozen=True, slots=True)
class Budget:
    """Per-scenario execution limits."""

    max_model_requests: int
    max_model_turns: int
    max_tool_calls: int
    max_completion_tokens_per_turn: int
    timeout_seconds: int


@dataclass(frozen=True, slots=True)
class ToolCall:
    """A model- or replay-requested tool call."""

    name: str
    arguments: JsonMap

    def as_dict(self) -> JsonMap:
        return {"name": self.name, "arguments": self.arguments}


@dataclass(frozen=True, slots=True)
class ModelTurn:
    """One model or replay turn."""

    content: str
    tool_calls: tuple[ToolCall, ...]
    provider: ModelAdapterName
    model_id: str
    request_index: int
    raw: JsonMap = field(default_factory=dict)

    def as_dict(self) -> JsonMap:
        return {
            "content": self.content,
            "model_id": self.model_id,
            "provider": self.provider,
            "raw": self.raw,
            "request_index": self.request_index,
            "tool_calls": [call.as_dict() for call in self.tool_calls],
        }


@dataclass(frozen=True, slots=True)
class ToolResult:
    """Result returned by an executable tool implementation."""

    name: str
    ok: bool
    acknowledgement: JsonMap
    observation: JsonMap | None = None

    def as_dict(self) -> JsonMap:
        data: JsonMap = {
            "acknowledgement": self.acknowledgement,
            "name": self.name,
            "ok": self.ok,
        }
        if self.observation is not None:
            data["observation"] = self.observation
        return data


@dataclass(frozen=True, slots=True)
class ScenarioDefinition:
    """Loaded scenario DSL document."""

    path: Path
    raw: JsonMap

    @property
    def scenario_id(self) -> str:
        return str(self.raw["metadata"]["id"])

    @property
    def name(self) -> str:
        return str(self.raw["metadata"]["name"])

    @property
    def prompt(self) -> str:
        return str(self.raw["spec"]["intent"]["prompt"])

    @property
    def budget(self) -> Budget:
        raw_budget = self.raw["spec"]["budgets"]
        if not isinstance(raw_budget, dict):
            raise TypeError("scenario spec.budgets must be an object")
        return Budget(
            max_model_requests=int(raw_budget["maxModelRequests"]),
            max_model_turns=int(raw_budget["maxModelTurns"]),
            max_tool_calls=int(raw_budget["maxToolCalls"]),
            max_completion_tokens_per_turn=int(raw_budget["maxCompletionTokensPerTurn"]),
            timeout_seconds=int(raw_budget["timeoutSeconds"]),
        )

    @property
    def expected_event_types(self) -> tuple[str, ...]:
        return tuple(str(item) for item in self.raw["spec"]["expected"]["lifecycle"])

    @property
    def mutations(self) -> tuple[JsonMap, ...]:
        spec = self.raw["spec"]
        if not isinstance(spec, dict):
            raise TypeError("scenario spec must be an object")
        mutations = spec.get("mutations", ())
        if not isinstance(mutations, list):
            raise TypeError("scenario spec.mutations must be a list")
        return tuple(item for item in mutations if isinstance(item, dict))

    @property
    def expected_statuses(self) -> tuple[str, ...]:
        return tuple(str(item) for item in self.raw["spec"]["expected"]["verificationStatuses"])

    @property
    def forbidden_statuses(self) -> tuple[str, ...]:
        expected = self.raw["spec"]["expected"]
        if not isinstance(expected, dict):
            raise TypeError("scenario spec.expected must be an object")
        return tuple(str(item) for item in expected.get("mustNotIncludeVerificationStatuses", ()))

    @property
    def expected_detections(self) -> tuple[str, ...]:
        expected = self.raw["spec"]["expected"]
        if not isinstance(expected, dict):
            raise TypeError("scenario spec.expected must be an object")
        return tuple(str(item) for item in expected.get("detections", ()))

    @property
    def expected_contracts(self) -> tuple[str, ...]:
        expected = self.raw["spec"]["expected"]
        if not isinstance(expected, dict):
            raise TypeError("scenario spec.expected must be an object")
        return tuple(str(item) for item in expected.get("contracts", ()))

    @property
    def expected_canary_ids(self) -> tuple[str, ...]:
        expected = self.raw["spec"]["expected"]
        if not isinstance(expected, dict):
            raise TypeError("scenario spec.expected must be an object")
        canaries = expected.get("redactionCanaries", ())
        if not isinstance(canaries, list):
            return ()
        return tuple(str(item["id"]) for item in canaries if isinstance(item, dict))

    @property
    def mismatch_failure_class(self) -> FailureClass:
        value = str(self.raw["spec"]["expected"]["failureClass"])
        return FailureClass(value)

    def agent_allowed_tools(self) -> tuple[str, ...]:
        agents = self.raw["spec"]["agents"]
        if not isinstance(agents, list) or not agents:
            raise TypeError("scenario spec.agents must be a non-empty list")
        first_agent = agents[0]
        if not isinstance(first_agent, dict):
            raise TypeError("scenario agent must be an object")
        return tuple(str(item) for item in first_agent["allowedTools"])


@dataclass(frozen=True, slots=True)
class RunPaths:
    """Artifact paths for one scenario run."""

    run_dir: Path
    journal_path: Path
    projection_path: Path
    transcript_path: Path
    tool_calls_path: Path
    oracle_observations_path: Path
    scorecard_path: Path
    replay_bundle_path: Path
    coverage_path: Path
    environment_path: Path
    toxiproxy_timeline_path: Path
    mutation_sequence_path: Path
    triage_path: Path


@dataclass(frozen=True, slots=True)
class ScoreResult:
    """One scorer result."""

    name: str
    ok: bool
    details: JsonMap
    failure_class: FailureClass | None = None

    def as_dict(self) -> JsonMap:
        data: JsonMap = {"details": self.details, "name": self.name, "ok": self.ok}
        if self.failure_class is not None:
            data["failure_class"] = self.failure_class.value
        return data


@dataclass(frozen=True, slots=True)
class ScenarioResult:
    """Machine-readable result for one scenario run."""

    scenario_id: str
    name: str
    passed: bool
    mode: RunMode
    failure_class: FailureClass | None
    scores: tuple[ScoreResult, ...]
    artifacts: RunPaths

    def as_dict(self) -> JsonMap:
        data: JsonMap = {
            "artifacts": {
                "coverage_path": str(self.artifacts.coverage_path),
                "environment_path": str(self.artifacts.environment_path),
                "journal_path": str(self.artifacts.journal_path),
                "mutation_sequence_path": str(self.artifacts.mutation_sequence_path),
                "oracle_observations_path": str(self.artifacts.oracle_observations_path),
                "projection_path": str(self.artifacts.projection_path),
                "replay_bundle_path": str(self.artifacts.replay_bundle_path),
                "run_dir": str(self.artifacts.run_dir),
                "scorecard_path": str(self.artifacts.scorecard_path),
                "toxiproxy_timeline_path": str(self.artifacts.toxiproxy_timeline_path),
                "tool_calls_path": str(self.artifacts.tool_calls_path),
                "triage_path": str(self.artifacts.triage_path),
                "transcript_path": str(self.artifacts.transcript_path),
            },
            "failure_class": self.failure_class.value if self.failure_class is not None else None,
            "mode": self.mode.value,
            "name": self.name,
            "passed": self.passed,
            "scenario_id": self.scenario_id,
            "scores": [score.as_dict() for score in self.scores],
        }
        return data


class ModelAdapter(Protocol):
    """Common model interface for GitHub Models, Ollama, and replay."""

    @property
    def provider(self) -> ModelAdapterName:
        """Provider identifier."""

    @property
    def model_id(self) -> str:
        """Model identifier."""

    def generate(
        self,
        *,
        prompt: str,
        tools: tuple[str, ...],
        budget: Budget,
        request_index: int,
    ) -> ModelTurn:
        """Return the next model turn."""


class AgentAdapter(Protocol):
    """Common agent interface for live and replay agents."""

    def run(self, scenario: ScenarioDefinition, model: ModelAdapter) -> tuple[ModelTurn, ...]:
        """Run an agent against a scenario using the supplied model adapter."""
