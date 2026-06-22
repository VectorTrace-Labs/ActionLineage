from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest
from hypothesis import settings
from hypothesis import strategies as st
from hypothesis.stateful import RuleBasedStateMachine, invariant, rule

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT / "evals"))

from actionlineage_evals import adapters as adapters_module  # noqa: E402
from actionlineage_evals.adapters import (  # noqa: E402
    GitHubModelsAdapter,
    LocalToolAgent,
    OpenAICompatibleAdapter,
)
from actionlineage_evals.artifact_audit import audit_artifacts  # noqa: E402
from actionlineage_evals.minimization import (  # noqa: E402
    minimize_tool_calls,
    tool_call_count,
    transcript_with_calls,
)
from actionlineage_evals.models import (  # noqa: E402
    Budget,
    FailureClass,
    JsonMap,
    ModelTurn,
    RunMode,
    ScoreResult,
    ToolCall,
)
from actionlineage_evals.replay import promote_regression_bundle  # noqa: E402
from actionlineage_evals.runner import (  # noqa: E402
    replay_artifacts,
    replay_bundle,
    run_regression_corpus,
    run_suite,
)
from actionlineage_evals.scenarios import (  # noqa: E402
    load_scenarios,
    validate_capability_coverage,
)
from actionlineage_evals.scoring import classify_failure  # noqa: E402
from actionlineage_evals.stateful import deterministic_mutation_sequence  # noqa: E402
from actionlineage_evals.summary import (  # noqa: E402
    summarize_scorecards,
    summarize_scorecards_text,
)
from actionlineage_evals.tools import WorldState  # noqa: E402


def test_scenarios_and_capability_coverage_validate() -> None:
    scenarios = load_scenarios(PROJECT_ROOT / "evals" / "scenarios")
    coverage = validate_capability_coverage(
        PROJECT_ROOT / "evals" / "CAPABILITY_COVERAGE.yaml",
        strict=True,
    )

    assert [scenario.scenario_id for scenario in scenarios] == [
        "AVL-001",
        "AVL-002",
        "AVL-003",
        "AVL-004",
        "AVL-005",
        "AVL-006",
        "AVL-007",
        "AVL-008",
        "AVL-009",
        "AVL-010",
    ]
    assert coverage["ok"] is True
    assert coverage["scenario_ids"] == [
        "AVL-001",
        "AVL-002",
        "AVL-003",
        "AVL-004",
        "AVL-005",
        "AVL-006",
        "AVL-007",
        "AVL-008",
        "AVL-009",
        "AVL-010",
    ]
    assert coverage["uncovered_capabilities"] == []


def test_actionlineage_core_does_not_import_eval_package() -> None:
    source_files = sorted((PROJECT_ROOT / "src" / "actionlineage").rglob("*.py"))

    offenders = [
        str(path.relative_to(PROJECT_ROOT))
        for path in source_files
        if "actionlineage_evals" in path.read_text(encoding="utf-8")
    ]

    assert offenders == []


def test_github_models_adapter_prefers_model_specific_token(monkeypatch) -> None:
    seen: dict[str, str] = {}

    def fake_post_openai_compatible(
        *,
        endpoint: str,
        token: str,
        model_id: str,
        prompt: str,
        max_tokens: int,
        timeout_seconds: int,
    ) -> JsonMap:
        del endpoint, model_id, prompt, max_tokens, timeout_seconds
        seen["token"] = token
        return {
            "choices": [
                {
                    "message": {
                        "content": (
                            "```json\n"
                            f"{json.dumps({'final': 'ok', 'tool_calls': []}, sort_keys=True)}\n"
                            "```"
                        ),
                    },
                },
            ],
        }

    monkeypatch.setenv("GITHUB_TOKEN", "actions-token")
    monkeypatch.setenv("GH_MODELS_TOKEN", "models-token")
    monkeypatch.setattr(adapters_module, "_post_openai_compatible", fake_post_openai_compatible)

    turn = GitHubModelsAdapter(model_id="openai/gpt-4.1-mini").generate(
        prompt="return no tool calls",
        tools=(),
        budget=Budget(
            max_model_requests=1,
            max_model_turns=1,
            max_tool_calls=1,
            max_completion_tokens_per_turn=16,
            timeout_seconds=10,
        ),
        request_index=0,
    )

    assert seen["token"] == "models-token"
    assert turn.tool_calls == ()


def test_openai_compatible_adapter_allows_local_endpoint_without_token(monkeypatch) -> None:
    seen: dict[str, object] = {}

    def fake_post_openai_compatible(
        *,
        endpoint: str,
        token: str | None,
        model_id: str,
        prompt: str,
        max_tokens: int,
        timeout_seconds: int,
    ) -> JsonMap:
        del prompt, max_tokens, timeout_seconds
        seen.update({"endpoint": endpoint, "model_id": model_id, "token": token})
        return {
            "choices": [
                {
                    "message": {
                        "content": json.dumps({"final": "ok", "tool_calls": []}, sort_keys=True),
                    },
                },
            ],
        }

    monkeypatch.delenv("OPENAI_COMPATIBLE_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("OPENAI_COMPATIBLE_BASE_URL", "http://localhost:9999/v1")
    monkeypatch.setattr(adapters_module, "_post_openai_compatible", fake_post_openai_compatible)

    turn = OpenAICompatibleAdapter(model_id="local/test").generate(
        prompt="return no tool calls",
        tools=(),
        budget=Budget(
            max_model_requests=1,
            max_model_turns=1,
            max_tool_calls=1,
            max_completion_tokens_per_turn=16,
            timeout_seconds=10,
        ),
        request_index=0,
    )

    assert seen == {
        "endpoint": "http://localhost:9999/v1/chat/completions",
        "model_id": "local/test",
        "token": None,
    }
    assert turn.provider == "openai_compatible"
    assert turn.tool_calls == ()


def test_local_tool_agent_returns_live_tool_plan_with_single_turn_budget() -> None:
    class FakeLiveModel:
        provider = "github_models"
        model_id = "test/live-tool-plan"

        def generate(
            self,
            *,
            prompt: str,
            tools: tuple[str, ...],
            budget: Budget,
            request_index: int,
        ) -> ModelTurn:
            del prompt, tools, budget
            return ModelTurn(
                content=json.dumps(
                    {
                        "final": "read requested",
                        "tool_calls": [
                            {
                                "name": "safe_files.read",
                                "arguments": {
                                    "path": "workspace/restricted/quarterly-plan.txt",
                                },
                            },
                        ],
                    },
                    sort_keys=True,
                ),
                tool_calls=(
                    ToolCall(
                        name="safe_files.read",
                        arguments={"path": "workspace/restricted/quarterly-plan.txt"},
                    ),
                ),
                provider="github_models",
                model_id=self.model_id,
                request_index=request_index,
            )

    scenario = load_scenarios(PROJECT_ROOT / "evals" / "scenarios")[0]

    turns = LocalToolAgent().run(scenario, FakeLiveModel())

    assert len(turns) == 1
    assert turns[0].tool_calls == (
        ToolCall(
            name="safe_files.read",
            arguments={"path": "workspace/restricted/quarterly-plan.txt"},
        ),
    )


def test_scripted_suite_runs_all_scenarios_and_replay(tmp_path: Path) -> None:
    result = run_suite(
        scenario_path=PROJECT_ROOT / "evals" / "scenarios",
        artifact_root=tmp_path / "evals",
        mode=RunMode.SCRIPTED,
        model_adapter_name="scripted",
    )

    assert result.passed is True
    assert [item.scenario_id for item in result.results] == [
        "AVL-001",
        "AVL-002",
        "AVL-003",
        "AVL-004",
        "AVL-005",
        "AVL-006",
        "AVL-007",
        "AVL-008",
        "AVL-009",
        "AVL-010",
    ]
    for scenario_result in result.results:
        expected_failure = {
            "AVL-007": FailureClass.PROVIDER,
            "AVL-008": FailureClass.BUDGET,
            "AVL-009": FailureClass.HARNESS,
            "AVL-010": FailureClass.AGENT,
        }.get(scenario_result.scenario_id)
        assert scenario_result.failure_class == expected_failure
        assert scenario_result.artifacts.replay_bundle_path.exists()
        assert scenario_result.artifacts.mutation_sequence_path.exists()
        assert scenario_result.artifacts.provenance_path.exists()
        assert scenario_result.artifacts.triage_path.exists()
        score_names = {score.name for score in scenario_result.scores}
        assert {
            "capability_coverage",
            "contract",
            "detection",
            "integrity",
            "lifecycle",
            "projection_rebuild",
            "redaction",
            "replayability",
        } <= score_names

    avl002_scorecard = json.loads(
        (tmp_path / "evals" / "avl-002-scripted-seed-0" / "scorecard.json").read_text(
            encoding="utf-8"
        )
    )
    lifecycle = next(score for score in avl002_scorecard["scores"] if score["name"] == "lifecycle")
    assert "verified" not in lifecycle["details"]["observed_verification_statuses"]
    assert lifecycle["details"]["observed_event_types"].count("resource.observed") == 2

    avl006_triage = (tmp_path / "evals" / "avl-006-scripted-seed-0" / "triage.md").read_text(
        encoding="utf-8"
    )
    assert "denied-then-allowed-safe-alternative" in avl006_triage
    assert "body_digest" in avl006_triage
    assert "safe-summary-only" not in avl006_triage

    avl005_manifest = json.loads(
        (
            tmp_path / "evals" / "avl-005-scripted-seed-0" / "replay-bundle" / "manifest.json"
        ).read_text(encoding="utf-8")
    )
    assert avl005_manifest["mutation_sequence"] == "mutation-sequence.json"
    assert avl005_manifest["reviewed"] is False
    assert avl005_manifest["triage"] == "triage.md"

    avl007_scorecard = json.loads(
        (tmp_path / "evals" / "avl-007-scripted-seed-0" / "scorecard.json").read_text(
            encoding="utf-8"
        )
    )
    assert avl007_scorecard["passed"] is True
    assert avl007_scorecard["failure_class"] == "provider_failure"
    assert avl007_scorecard["provider_error"]["type"] == "ProviderError"

    avl008_scorecard = json.loads(
        (tmp_path / "evals" / "avl-008-scripted-seed-0" / "scorecard.json").read_text(
            encoding="utf-8"
        )
    )
    assert avl008_scorecard["passed"] is True
    assert avl008_scorecard["failure_class"] == "inconclusive_budget_exhausted"
    assert avl008_scorecard["agent_error"]["type"] == "AgentBudgetError"

    avl009_scorecard = json.loads(
        (tmp_path / "evals" / "avl-009-scripted-seed-0" / "scorecard.json").read_text(
            encoding="utf-8"
        )
    )
    assert avl009_scorecard["passed"] is True
    assert avl009_scorecard["failure_class"] == "harness_failure"
    assert avl009_scorecard["harness_error"]["type"] == "HarnessControlError"

    avl010_scorecard = json.loads(
        (tmp_path / "evals" / "avl-010-scripted-seed-0" / "scorecard.json").read_text(
            encoding="utf-8"
        )
    )
    assert avl010_scorecard["passed"] is True
    assert avl010_scorecard["failure_class"] == "agent_failure"
    assert avl010_scorecard["agent_error"]["type"] == "AgentExecutionError"

    avl010_minimization = json.loads(
        (tmp_path / "evals" / "avl-010-scripted-seed-0" / "minimization-report.json").read_text(
            encoding="utf-8"
        )
    )
    assert avl010_minimization["failure_class"] == "agent_failure"
    assert avl010_minimization["original_tool_calls"] == 1
    assert avl010_minimization["minimized_tool_calls"] == 1

    avl001_oracles = [
        json.loads(line)
        for line in (tmp_path / "evals" / "avl-001-scripted-seed-0" / "oracle-observations.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
    ]
    assert any(item["status"] == "process_running" for item in avl001_oracles)

    replayed = replay_bundle(
        tmp_path / "evals" / "avl-001-scripted-seed-0" / "replay-bundle",
        artifact_root=tmp_path / "replay",
    )
    assert replayed.passed is True

    replayed_provider_failure = replay_bundle(
        tmp_path / "evals" / "avl-007-scripted-seed-0" / "replay-bundle",
        artifact_root=tmp_path / "provider-replay",
    )
    assert replayed_provider_failure.passed is True
    assert replayed_provider_failure.failure_class == FailureClass.PROVIDER

    replayed_artifacts = replay_artifacts(
        artifact_root=tmp_path / "evals",
        replay_artifact_root=tmp_path / "artifact-replay",
    )
    assert replayed_artifacts.passed is True
    assert len(replayed_artifacts.results) == 10
    avl010_replay_scorecard = json.loads(
        (
            tmp_path
            / "artifact-replay"
            / "avl-010-scripted-seed-0"
            / "avl-010-replay-seed-0"
            / "scorecard.json"
        ).read_text(encoding="utf-8")
    )
    assert avl010_replay_scorecard["failure_class"] == "agent_failure"
    replay_equivalence = next(
        score
        for score in avl010_replay_scorecard["scores"]
        if score["name"] == "replay_equivalence"
    )
    assert replay_equivalence["ok"] is True

    audit = audit_artifacts(tmp_path / "evals")
    assert audit["ok"] is True
    assert audit["leak_count"] == 0


def test_regression_corpus_replay_supports_empty_and_promoted_bundles(tmp_path: Path) -> None:
    empty = run_regression_corpus(
        regression_dir=tmp_path / "empty-regressions",
        artifact_root=tmp_path / "empty-replay",
        allow_empty=True,
    )
    assert empty.passed is True
    assert empty.results == ()

    result = run_suite(
        scenario_path=PROJECT_ROOT / "evals" / "scenarios" / "AVL-007.yaml",
        artifact_root=tmp_path / "evals",
        mode=RunMode.SCRIPTED,
        model_adapter_name="scripted",
    )
    assert result.passed is True
    candidate = promote_regression_bundle(
        tmp_path / "evals" / "avl-007-scripted-seed-0" / "replay-bundle",
        tmp_path / "regressions",
    )
    assert "_candidates" in candidate.parts

    reviewed = promote_regression_bundle(
        tmp_path / "evals" / "avl-007-scripted-seed-0" / "replay-bundle",
        tmp_path / "regressions",
        reviewed=True,
        reviewed_by="security-platform",
        reason="synthetic provider-failure regression control",
        source_run="local-test",
    )
    reviewed_manifest = json.loads((reviewed / "manifest.json").read_text(encoding="utf-8"))
    assert reviewed_manifest["review"]["failure_class"] == "provider_failure"
    assert reviewed_manifest["review"]["reviewed_by"] == "security-platform"

    replayed = run_regression_corpus(
        regression_dir=reviewed.parent,
        artifact_root=tmp_path / "regression-replay",
    )

    assert replayed.passed is True
    assert [item.scenario_id for item in replayed.results] == ["AVL-007"]


def test_reviewed_regression_promotion_requires_review_metadata(tmp_path: Path) -> None:
    result = run_suite(
        scenario_path=PROJECT_ROOT / "evals" / "scenarios" / "AVL-007.yaml",
        artifact_root=tmp_path / "evals",
        mode=RunMode.SCRIPTED,
        model_adapter_name="scripted",
    )
    assert result.passed is True

    with pytest.raises(ValueError, match="reviewed_by"):
        promote_regression_bundle(
            tmp_path / "evals" / "avl-007-scripted-seed-0" / "replay-bundle",
            tmp_path / "regressions",
            reviewed=True,
            reason="missing reviewer",
            source_run="local-test",
        )


def test_artifact_audit_reports_redacted_pattern_without_value(tmp_path: Path) -> None:
    artifact = tmp_path / "artifact.txt"
    token = "Bearer " + "abcdefghijklmnop" + "qrstuvwxyz123456"
    artifact.write_text(f"token={token}\n", encoding="utf-8")

    audit = audit_artifacts(tmp_path)

    assert audit["ok"] is False
    assert audit["leaks"] == [{"path": str(artifact), "pattern": "bearer_token"}]
    assert token not in json.dumps(audit)


def test_world_state_uses_dynamic_docker_ports(tmp_path: Path) -> None:
    world = WorldState(run_dir=tmp_path, use_docker=True)

    world.configure_from_environment(
        {
            "published_ports": {
                "receiver_8080": "0.0.0.0:49152",
                "toxiproxy_8474": "0.0.0.0:49153",
                "toxiproxy_8880": "0.0.0.0:49154",
            },
        }
    )

    assert world.receiver_url == "http://127.0.0.1:49152/collect"
    assert world.toxiproxy_api_url == "http://127.0.0.1:49153"
    assert world.toxiproxy_url == "http://127.0.0.1:49154/collect"


def test_unreviewed_regression_bundle_is_rejected(tmp_path: Path) -> None:
    result = run_suite(
        scenario_path=PROJECT_ROOT / "evals" / "scenarios" / "AVL-001.yaml",
        artifact_root=tmp_path / "evals",
        mode=RunMode.SCRIPTED,
        model_adapter_name="scripted",
    )
    assert result.passed is True
    unreviewed = tmp_path / "regressions" / "AVL-001-unreviewed"
    source = tmp_path / "evals" / "avl-001-scripted-seed-0" / "replay-bundle"
    unreviewed.mkdir(parents=True)
    for item in source.iterdir():
        if item.is_file():
            (unreviewed / item.name).write_bytes(item.read_bytes())

    with pytest.raises(ValueError, match="not reviewed"):
        run_regression_corpus(
            regression_dir=unreviewed.parent,
            artifact_root=tmp_path / "regression-replay",
        )


def test_scorecard_summary_reports_replay_commands(tmp_path: Path) -> None:
    result = run_suite(
        scenario_path=PROJECT_ROOT / "evals" / "scenarios" / "AVL-007.yaml",
        artifact_root=tmp_path / "evals",
        mode=RunMode.SCRIPTED,
        model_adapter_name="scripted",
    )
    assert result.passed is True

    summary = summarize_scorecards(tmp_path / "evals")
    text = summarize_scorecards_text(tmp_path / "evals")

    assert summary["ok"] is True
    assert summary["scenario_count"] == 1
    assert summary["scorecards"][0]["scenario_id"] == "AVL-007"
    assert summary["scorecards"][0]["failure_class"] == "provider_failure"
    assert "actionlineage_evals replay" in summary["scorecards"][0]["replay_command"]
    assert "AVL-007" in text


def test_inspect_task_accepts_live_configuration_metadata() -> None:
    pytest.importorskip("inspect_ai")
    from actionlineage_evals.inspect_tasks import agent_validation_lab

    task = agent_validation_lab(
        scenario_path=str(PROJECT_ROOT / "evals" / "scenarios"),
        artifact_root="build/evals/inspect-test",
        mode="live",
        model_adapter="openai_compatible",
        model_id="local/test",
        seed=7,
        max_scenarios=1,
    )
    sample = task.dataset[0]

    assert sample.metadata["mode"] == "live"
    assert sample.metadata["model_adapter"] == "openai_compatible"
    assert sample.metadata["model_id"] == "local/test"
    assert sample.metadata["seed"] == 7


def test_failure_classification_preserves_distinct_classes() -> None:
    product_score = ScoreResult(
        name="oracle",
        ok=False,
        details={},
        failure_class=FailureClass.PRODUCT,
    )

    assert classify_failure(scores=(product_score,)) == FailureClass.PRODUCT
    assert classify_failure(scores=(), agent_error=RuntimeError("bad plan")) == FailureClass.AGENT
    assert (
        classify_failure(scores=(), provider_error=RuntimeError("rate limited"))
        == FailureClass.PROVIDER
    )
    assert classify_failure(scores=(), harness_error=RuntimeError("bug")) == FailureClass.HARNESS
    assert classify_failure(scores=(), budget_exhausted=True) == FailureClass.BUDGET


def test_tool_call_minimizer_preserves_failure_predicate() -> None:
    calls = (
        ToolCall(name="safe_files.read", arguments={"path": "noise"}),
        ToolCall(name="safe_http.send", arguments={"mode": "descriptor_drift_conflict"}),
        ToolCall(name="safe_http.send", arguments={"mode": "noise"}),
    )
    transcript = transcript_with_calls(calls)

    minimized = minimize_tool_calls(
        transcript,
        still_fails=lambda turns: any(
            call.arguments.get("mode") == "descriptor_drift_conflict"
            for turn in turns
            for call in turn.tool_calls
        ),
    )

    assert tool_call_count(minimized) == 1
    assert minimized[0].tool_calls[0].arguments["mode"] == "descriptor_drift_conflict"


@settings(max_examples=20, stateful_step_count=8)
class MutationMachine(RuleBasedStateMachine):
    def __init__(self) -> None:
        super().__init__()
        self.generated: list[tuple[dict[str, object], ...]] = []

    @rule(seed=st.integers(min_value=0, max_value=20), count=st.integers(min_value=1, max_value=6))
    def generate_mutations(self, seed: int, count: int) -> None:
        sequence = deterministic_mutation_sequence(seed, count=count)
        repeated = deterministic_mutation_sequence(seed, count=count)

        assert sequence == repeated
        self.generated.append(tuple(item.as_dict() for item in sequence))

    @invariant()
    def generated_mutations_are_seeded(self) -> None:
        for sequence in self.generated:
            assert all("seed" in item and "dimension" in item for item in sequence)


TestMutationMachine = MutationMachine.TestCase
