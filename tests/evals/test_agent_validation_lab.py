from __future__ import annotations

import json
import sys
from pathlib import Path

from hypothesis import settings
from hypothesis import strategies as st
from hypothesis.stateful import RuleBasedStateMachine, invariant, rule

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT / "evals"))

from actionlineage_evals import adapters as adapters_module  # noqa: E402
from actionlineage_evals.adapters import GitHubModelsAdapter  # noqa: E402
from actionlineage_evals.minimization import (  # noqa: E402
    minimize_tool_calls,
    tool_call_count,
    transcript_with_calls,
)
from actionlineage_evals.models import (  # noqa: E402
    Budget,
    FailureClass,
    JsonMap,
    RunMode,
    ScoreResult,
    ToolCall,
)
from actionlineage_evals.runner import replay_bundle, run_suite  # noqa: E402
from actionlineage_evals.scenarios import (  # noqa: E402
    load_scenarios,
    validate_capability_coverage,
)
from actionlineage_evals.scoring import classify_failure  # noqa: E402
from actionlineage_evals.stateful import deterministic_mutation_sequence  # noqa: E402


def test_scenarios_and_capability_coverage_validate() -> None:
    scenarios = load_scenarios(PROJECT_ROOT / "evals" / "scenarios")
    coverage = validate_capability_coverage(PROJECT_ROOT / "evals" / "CAPABILITY_COVERAGE.yaml")

    assert [scenario.scenario_id for scenario in scenarios] == [
        "AVL-001",
        "AVL-002",
        "AVL-003",
        "AVL-004",
    ]
    assert coverage["ok"] is True
    assert coverage["scenario_ids"] == ["AVL-001", "AVL-002", "AVL-003", "AVL-004"]


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
                        "content": json.dumps({"final": "ok", "tool_calls": []}, sort_keys=True),
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
    ]
    for scenario_result in result.results:
        assert scenario_result.failure_class is None
        assert scenario_result.artifacts.replay_bundle_path.exists()
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

    replayed = replay_bundle(
        tmp_path / "evals" / "avl-001-scripted-seed-0" / "replay-bundle",
        artifact_root=tmp_path / "replay",
    )
    assert replayed.passed is True


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
