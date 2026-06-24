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
    ProviderError,
)
from actionlineage_evals.artifact_audit import audit_artifacts  # noqa: E402
from actionlineage_evals.baseline import baseline_check_passes, check_public_baseline  # noqa: E402
from actionlineage_evals.boundary import check_eval_import_boundaries  # noqa: E402
from actionlineage_evals.linting import lint_scenarios  # noqa: E402
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
from actionlineage_evals.stateful import (  # noqa: E402
    deterministic_mutation_sequence,
    deterministic_stateful_counterexample,
    minimize_stateful_steps,
    stateful_failure_predicate,
)
from actionlineage_evals.summary import (  # noqa: E402
    build_public_baseline_report,
    render_public_baseline_report_markdown,
    summarize_scorecards,
    summarize_scorecards_text,
    write_public_baseline_report,
    write_trend_report,
)
from actionlineage_evals.tools import WorldState  # noqa: E402

EXPECTED_SCENARIO_IDS = tuple(f"AVL-{index:03d}" for index in range(1, 16))


def test_scenarios_and_capability_coverage_validate() -> None:
    scenarios = load_scenarios(PROJECT_ROOT / "evals" / "scenarios")
    coverage = validate_capability_coverage(
        PROJECT_ROOT / "evals" / "CAPABILITY_COVERAGE.yaml",
        strict=True,
    )

    assert [scenario.scenario_id for scenario in scenarios] == list(EXPECTED_SCENARIO_IDS)
    assert coverage["ok"] is True
    assert coverage["scenario_ids"] == list(EXPECTED_SCENARIO_IDS)
    assert coverage["known_gaps"] == [
        {
            "id": "cloud_observer_live",
            "reason": "Live cloud observers remain outside development-only eval scope.",
        }
    ]
    assert coverage["uncovered_capabilities"] == []
    lint = lint_scenarios(
        scenario_path=PROJECT_ROOT / "evals" / "scenarios",
        coverage_path=PROJECT_ROOT / "evals" / "CAPABILITY_COVERAGE.yaml",
    )
    assert lint["ok"] is True


def test_public_agent_validation_evidence_doc_matches_registry() -> None:
    scenarios = load_scenarios(PROJECT_ROOT / "evals" / "scenarios")
    coverage = validate_capability_coverage(
        PROJECT_ROOT / "evals" / "CAPABILITY_COVERAGE.yaml",
        strict=True,
    )
    doc = (PROJECT_ROOT / "docs" / "AGENT_VALIDATION_EVIDENCE.md").read_text(encoding="utf-8")
    public_report = json.loads(
        (PROJECT_ROOT / "docs" / "evidence" / "agent-validation-baseline.json").read_text(
            encoding="utf-8"
        )
    )
    public_report_md = (
        PROJECT_ROOT / "docs" / "evidence" / "agent-validation-baseline.md"
    ).read_text(encoding="utf-8")
    normalized_doc = " ".join(doc.split())

    assert f"{len(scenarios)} scenarios" in doc
    assert (
        f"{coverage['covered_capability_count']}/{coverage['capability_count']} "
        "declared capabilities covered"
    ) in doc
    for scenario in scenarios:
        assert f"`{scenario.scenario_id}`" in doc
    for gap in coverage["known_gaps"]:
        assert f"`{gap['id']}`" in doc
    assert "Model output is not authoritative product evidence" in normalized_doc
    assert "Agent Validation Lab beyond `Local-proof` maturity" in doc
    assert public_report["schema_version"] == "actionlineage.dev/agent-validation-public-report-v0"
    assert public_report["scenario_ids"] == [scenario.scenario_id for scenario in scenarios]
    assert public_report["baseline_inputs"]["digest"].startswith("sha256:")
    assert public_report["baseline_inputs"]["file_count"] > 0
    assert public_report["suite"]["scorecard_count"] == len(scenarios)
    assert (
        public_report["capability_coverage"]["covered_capability_count"]
        == coverage["covered_capability_count"]
    )
    assert public_report["capability_coverage"]["capability_count"] == coverage["capability_count"]
    assert public_report["model_adapters"] == [
        {
            "adapter": "scripted",
            "model_id": None,
            "no_model": True,
        }
    ]
    assert public_report["failure_classification"]["counts"]["product_failure"] == 3
    assert public_report["failure_classification"]["expected_control_scenarios"]
    assert public_report["tool_schema_hashes"]
    assert "Source commit under evaluation" in public_report_md
    assert "Expected control scenarios intentionally preserve product, agent" in public_report_md
    assert "Scripted adapter output is not treated as an authoritative product oracle." in (
        public_report_md
    )


def test_actionlineage_core_does_not_import_eval_package() -> None:
    report = check_eval_import_boundaries(PROJECT_ROOT)

    assert report["ok"] is True
    assert report["violations"] == []


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


def test_github_models_adapter_requires_explicit_model_secret(monkeypatch) -> None:
    monkeypatch.delenv("GH_MODELS_TOKEN", raising=False)
    monkeypatch.delenv("GITHUB_MODELS_TOKEN", raising=False)
    monkeypatch.setenv("GITHUB_TOKEN", "ambient-actions-token")

    with pytest.raises(ProviderError, match="GH_MODELS_TOKEN or GITHUB_MODELS_TOKEN"):
        GitHubModelsAdapter(model_id="openai/gpt-4.1-mini").generate(
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
    assert [item.scenario_id for item in result.results] == list(EXPECTED_SCENARIO_IDS)
    for scenario_result in result.results:
        expected_failure = {
            "AVL-011": FailureClass.PRODUCT,
            "AVL-007": FailureClass.PROVIDER,
            "AVL-008": FailureClass.BUDGET,
            "AVL-009": FailureClass.HARNESS,
            "AVL-010": FailureClass.AGENT,
            "AVL-013": FailureClass.PRODUCT,
            "AVL-014": FailureClass.PRODUCT,
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

    avl011_scorecard = json.loads(
        (tmp_path / "evals" / "avl-011-scripted-seed-0" / "scorecard.json").read_text(
            encoding="utf-8"
        )
    )
    assert avl011_scorecard["passed"] is True
    assert avl011_scorecard["failure_class"] == "product_failure"
    assert avl011_scorecard["agent_error"] is None
    assert avl011_scorecard["provider_error"] is None
    assert any(score["ok"] is False for score in avl011_scorecard["scores"])

    avl012_scorecard = json.loads(
        (tmp_path / "evals" / "avl-012-scripted-seed-0" / "scorecard.json").read_text(
            encoding="utf-8"
        )
    )
    assert avl012_scorecard["passed"] is True
    assert avl012_scorecard["failure_class"] is None
    run_isolation = next(
        score for score in avl012_scorecard["scores"] if score["name"] == "run_isolation"
    )
    assert run_isolation["ok"] is True
    assert run_isolation["details"]["child_run_ids"] == [
        "run_avl-012_agent_a_0000",
        "run_avl-012_agent_b_0000",
    ]
    assert run_isolation["details"]["tool_request_run_ids"] == [
        "run_avl-012_agent_a_0000",
        "run_avl-012_agent_b_0000",
        "run_avl-012_agent_a_0000",
        "run_avl-012_agent_b_0000",
    ]
    assert run_isolation["details"]["coordinator_tool_events"] == []
    assert run_isolation["details"]["cross_run_evidence_links"] == []
    assert run_isolation["details"]["interleaving_transitions"] == 3
    assert all(count > 0 for count in run_isolation["details"]["projection_event_counts"].values())

    avl013_scorecard = json.loads(
        (tmp_path / "evals" / "avl-013-scripted-seed-0" / "scorecard.json").read_text(
            encoding="utf-8"
        )
    )
    assert avl013_scorecard["passed"] is True
    assert avl013_scorecard["failure_class"] == "product_failure"
    assert avl013_scorecard["agent_error"] is None
    assert avl013_scorecard["provider_error"] is None
    assert avl013_scorecard["harness_error"] is None
    contaminated_run_isolation = next(
        score for score in avl013_scorecard["scores"] if score["name"] == "run_isolation"
    )
    assert contaminated_run_isolation["ok"] is False
    assert contaminated_run_isolation["failure_class"] == "product_failure"
    assert len(contaminated_run_isolation["details"]["cross_run_evidence_links"]) == 1
    contaminated_link = contaminated_run_isolation["details"]["cross_run_evidence_links"][0]
    assert contaminated_link["event_run_id"] == "run_avl-013_agent_b_0000"
    assert contaminated_link["subject_run_id"] == "run_avl-013_agent_a_0000"
    assert contaminated_link["evidence_run_id"] == "run_avl-013_agent_b_0000"
    assert contaminated_run_isolation["details"]["coordinator_tool_events"] == []

    avl014_scorecard = json.loads(
        (tmp_path / "evals" / "avl-014-scripted-seed-0" / "scorecard.json").read_text(
            encoding="utf-8"
        )
    )
    assert avl014_scorecard["passed"] is True
    assert avl014_scorecard["failure_class"] == "product_failure"
    assert avl014_scorecard["agent_error"] is None
    assert avl014_scorecard["provider_error"] is None
    assert avl014_scorecard["harness_error"] is None
    stateful_score = next(
        score
        for score in avl014_scorecard["scores"]
        if score["name"] == "stateful_mutation_minimization"
    )
    assert stateful_score["ok"] is False
    assert stateful_score["failure_class"] == "product_failure"
    assert stateful_score["details"]["counterexample_found"] is True
    assert stateful_score["details"]["expected_failure_class"] is True
    assert stateful_score["details"]["expected_operation_present"] is True
    assert stateful_score["details"]["generated_step_count"] == 4
    assert stateful_score["details"]["minimized_step_count"] == 1
    assert stateful_score["details"]["minimized_operations"] == [
        "drop_required_verification_status"
    ]

    avl014_stateful_report = json.loads(
        (
            tmp_path / "evals" / "avl-014-scripted-seed-0" / "stateful-mutation-report.json"
        ).read_text(encoding="utf-8")
    )
    assert avl014_stateful_report["counterexample_found"] is True
    assert avl014_stateful_report["reduced"] is True
    assert len(avl014_stateful_report["minimized_steps"]) == 1

    avl014_manifest = json.loads(
        (
            tmp_path / "evals" / "avl-014-scripted-seed-0" / "replay-bundle" / "manifest.json"
        ).read_text(encoding="utf-8")
    )
    assert avl014_manifest["stateful_mutation_report"] == "stateful-mutation-report.json"
    assert avl014_manifest["artifact_hashes"]["stateful_mutation_report"].startswith("sha256:")

    avl015_run_dir = tmp_path / "evals" / "avl-015-scripted-seed-0"
    avl015_scorecard = json.loads((avl015_run_dir / "scorecard.json").read_text(encoding="utf-8"))
    assert avl015_scorecard["passed"] is True
    assert avl015_scorecard["failure_class"] is None
    service_detection = next(
        score for score in avl015_scorecard["scores"] if score["name"] == "detection"
    )
    assert service_detection["ok"] is True
    assert service_detection["details"]["expected_rule_ids"] == [
        "AVL-015.service_auth_denied_then_allowed"
    ]
    redaction = next(score for score in avl015_scorecard["scores"] if score["name"] == "redaction")
    assert redaction["ok"] is True
    assert redaction["details"]["canary_count"] == 3
    avl015_oracles = [
        json.loads(line)
        for line in (avl015_run_dir / "oracle-observations.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
    ]
    assert [item["status"] for item in avl015_oracles] == [
        "service_auth_denied",
        "service_auth_allowed",
    ]
    avl015_tool_calls = json.loads((avl015_run_dir / "tool-calls.json").read_text(encoding="utf-8"))
    assert [item["tool_call"]["arguments"]["token_ref"] for item in avl015_tool_calls["calls"]] == [
        "invalid",
        "reader",
    ]
    assert all("token" not in item["tool_call"]["arguments"] for item in avl015_tool_calls["calls"])
    service_artifact_text = "\n".join(
        path.read_text(encoding="utf-8")
        for path in (
            avl015_run_dir / "journal.jsonl",
            avl015_run_dir / "transcript.json",
            avl015_run_dir / "tool-calls.json",
            avl015_run_dir / "oracle-observations.jsonl",
            avl015_run_dir / "replay-bundle" / "journal.jsonl",
            avl015_run_dir / "replay-bundle" / "transcript.json",
            avl015_run_dir / "replay-bundle" / "tool-calls.json",
            avl015_run_dir / "replay-bundle" / "oracle-observations.jsonl",
        )
    )
    assert "synthetic-read-token" not in service_artifact_text
    assert "invalid-synthetic-token" not in service_artifact_text

    suite_summary = json.loads((tmp_path / "evals" / "suite-summary.json").read_text())
    assert suite_summary["schema_version"] == "actionlineage.dev/eval-suite-summary/v0"
    assert suite_summary["failure_class_counts"]["product_failure"] == 3
    summary_by_id = {item["scenario_id"]: item for item in suite_summary["scenarios"]}
    assert summary_by_id["AVL-001"]["failure_fingerprint"] is None
    assert summary_by_id["AVL-011"]["failure_fingerprint"].startswith("sha256:")
    assert summary_by_id["AVL-013"]["failure_fingerprint"].startswith("sha256:")
    assert summary_by_id["AVL-014"]["failure_fingerprint"].startswith("sha256:")

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
    assert len(replayed_artifacts.results) == 15
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
        scenario_path=PROJECT_ROOT / "evals" / "scenarios" / "AVL-010.yaml",
        artifact_root=tmp_path / "evals",
        mode=RunMode.SCRIPTED,
        model_adapter_name="scripted",
    )
    assert result.passed is True
    candidate = promote_regression_bundle(
        tmp_path / "evals" / "avl-010-scripted-seed-0" / "replay-bundle",
        tmp_path / "regressions",
    )
    assert "_candidates" in candidate.parts

    reviewed = promote_regression_bundle(
        tmp_path / "evals" / "avl-010-scripted-seed-0" / "replay-bundle",
        tmp_path / "regressions",
        reviewed=True,
        reviewed_by="security-platform",
        reason="synthetic agent-failure minimized regression control",
        source_run="local-test",
    )
    reviewed_manifest = json.loads((reviewed / "manifest.json").read_text(encoding="utf-8"))
    assert reviewed_manifest["review"]["failure_class"] == "agent_failure"
    assert reviewed_manifest["review"]["reviewed_by"] == "security-platform"

    replayed = run_regression_corpus(
        regression_dir=reviewed.parent,
        artifact_root=tmp_path / "regression-replay",
    )

    assert replayed.passed is True
    assert [item.scenario_id for item in replayed.results] == ["AVL-010"]


def test_committed_reviewed_regression_corpus_replays(tmp_path: Path) -> None:
    replayed = run_regression_corpus(
        regression_dir=PROJECT_ROOT / "evals" / "regressions",
        artifact_root=tmp_path / "committed-regression-replay",
    )

    assert replayed.passed is True
    assert [item.scenario_id for item in replayed.results] == ["AVL-010"]


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


def test_reviewed_regression_promotion_requires_minimized_bundle(tmp_path: Path) -> None:
    result = run_suite(
        scenario_path=PROJECT_ROOT / "evals" / "scenarios" / "AVL-007.yaml",
        artifact_root=tmp_path / "evals",
        mode=RunMode.SCRIPTED,
        model_adapter_name="scripted",
    )
    assert result.passed is True

    with pytest.raises(ValueError, match="missing required artifacts"):
        promote_regression_bundle(
            tmp_path / "evals" / "avl-007-scripted-seed-0" / "replay-bundle",
            tmp_path / "regressions",
            reviewed=True,
            reviewed_by="security-platform",
            reason="provider control has no minimized transcript yet",
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


def test_docker_eval_fixture_uses_supported_python_floor() -> None:
    compose = (PROJECT_ROOT / "evals" / "docker" / "compose.yaml").read_text(encoding="utf-8")

    assert "image: python:3.12-alpine" in compose


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
    assert summary["scorecards"][0]["failure_fingerprint"].startswith("sha256:")
    assert "actionlineage_evals replay" in summary["scorecards"][0]["replay_command"]
    assert "failure_fingerprint" in text
    assert "AVL-007" in text


def test_public_baseline_report_is_generated_from_eval_artifacts(tmp_path: Path) -> None:
    result = run_suite(
        scenario_path=PROJECT_ROOT / "evals" / "scenarios" / "AVL-001.yaml",
        artifact_root=tmp_path / "evals",
        mode=RunMode.SCRIPTED,
        model_adapter_name="scripted",
    )
    assert result.passed is True

    report = build_public_baseline_report(tmp_path / "evals")
    markdown = render_public_baseline_report_markdown(report)
    json_output = tmp_path / "report" / "agent-validation-baseline.json"
    markdown_output = tmp_path / "report" / "agent-validation-baseline.md"
    written = write_public_baseline_report(
        tmp_path / "evals",
        json_output=json_output,
        markdown_output=markdown_output,
    )

    assert report["ok"] is True
    assert report["schema_version"] == "actionlineage.dev/agent-validation-public-report-v0"
    assert report["baseline_inputs"]["schema_version"] == (
        "actionlineage.dev/agent-validation-baseline-inputs-v0"
    )
    assert report["baseline_inputs"]["digest"].startswith("sha256:")
    assert report["baseline_inputs"]["file_count"] > 0
    assert report["suite"]["scorecard_count"] == 1
    assert report["scenario_ids"][0] == "AVL-001"
    assert report["seeds"] == [0]
    assert report["model_adapters"] == [
        {
            "adapter": "scripted",
            "model_id": None,
            "no_model": True,
        }
    ]
    assert report["tool_schema_hashes"]
    assert report["coverage"]["event_type_coverage"]["tool.execution.acknowledged"] == 1
    assert report["coverage"]["contract_coverage"]["passed"] == 1
    assert report["hard_assertion_results"]["score_counts"]["integrity"]["passed"] == 1
    assert report["runs"][0]["failure_fingerprint"] is None
    assert written == report
    assert json.loads(json_output.read_text(encoding="utf-8")) == report
    assert markdown_output.read_text(encoding="utf-8") == markdown
    assert "Source commit under evaluation" in markdown
    assert "Baseline input digest" in markdown
    assert "PYTHONPATH=evals uv run --group eval python -m actionlineage_evals run" in markdown


def test_trend_report_is_generated_from_eval_artifacts(tmp_path: Path) -> None:
    result = run_suite(
        scenario_path=PROJECT_ROOT / "evals" / "scenarios" / "AVL-001.yaml",
        artifact_root=tmp_path / "evals",
        mode=RunMode.SCRIPTED,
        model_adapter_name="scripted",
    )
    assert result.passed is True

    output = tmp_path / "reports" / "trend.json"
    markdown_output = tmp_path / "reports" / "trend.md"
    first = write_trend_report(
        tmp_path / "evals",
        output_path=output,
        markdown_output=markdown_output,
        label="test-run-1",
    )
    second = write_trend_report(
        tmp_path / "evals",
        output_path=output,
        markdown_output=markdown_output,
        label="test-run-2",
    )

    assert first["run_count"] == 1
    assert second["run_count"] == 2
    assert second["latest"]["label"] == "test-run-2"
    assert second["latest"]["ok"] is True
    assert second["latest"]["capability_coverage"]["capability_count"] == 56
    assert second["latest"]["scenario_count"] == 1
    assert "Agent Validation Trend" in markdown_output.read_text(encoding="utf-8")


def test_public_baseline_check_allows_provenance_only_drift(tmp_path: Path) -> None:
    result = run_suite(
        scenario_path=PROJECT_ROOT / "evals" / "scenarios" / "AVL-001.yaml",
        artifact_root=tmp_path / "evals",
        mode=RunMode.SCRIPTED,
        model_adapter_name="scripted",
    )
    assert result.passed is True
    committed = build_public_baseline_report(tmp_path / "evals")
    committed["artifact_root"] = "build/evals/public-alpha"
    committed["commit_sha"] = "previous-commit"
    committed["source_commits"] = ["previous-commit"]
    committed["reproduction_commands"] = ["stale command"]
    committed_path = tmp_path / "committed-baseline.json"
    committed_path.write_text(json.dumps(committed, indent=2, sort_keys=True), encoding="utf-8")

    check = check_public_baseline(
        tmp_path / "evals",
        committed_report_path=committed_path,
    )

    assert check["ok"] is True
    assert check["status"] == "provenance_only_drift"
    assert check["semantic_differences"] == []
    assert check["input_differences"] == {}
    assert set(check["provenance_differences"]) == {
        "artifact_root",
        "commit_sha",
        "reproduction_commands",
        "source_commits",
    }


def test_public_baseline_check_fails_on_semantic_drift(tmp_path: Path) -> None:
    result = run_suite(
        scenario_path=PROJECT_ROOT / "evals" / "scenarios" / "AVL-001.yaml",
        artifact_root=tmp_path / "evals",
        mode=RunMode.SCRIPTED,
        model_adapter_name="scripted",
    )
    assert result.passed is True
    committed = build_public_baseline_report(tmp_path / "evals")
    committed["suite"]["failed_count"] = 1
    committed_path = tmp_path / "committed-baseline.json"
    committed_path.write_text(json.dumps(committed, indent=2, sort_keys=True), encoding="utf-8")

    check = check_public_baseline(
        tmp_path / "evals",
        committed_report_path=committed_path,
    )

    assert check["ok"] is False
    assert check["status"] == "semantic_drift"
    assert check["semantic_differences"]
    assert check["semantic_differences"][0]["path"] == "$.suite.failed_count"
    assert baseline_check_passes(check) is False
    assert baseline_check_passes(check, allow_input_drift=True) is False


def test_public_baseline_check_fails_on_input_drift(tmp_path: Path) -> None:
    result = run_suite(
        scenario_path=PROJECT_ROOT / "evals" / "scenarios" / "AVL-001.yaml",
        artifact_root=tmp_path / "evals",
        mode=RunMode.SCRIPTED,
        model_adapter_name="scripted",
    )
    assert result.passed is True
    committed = build_public_baseline_report(tmp_path / "evals")
    committed["baseline_inputs"]["digest"] = "sha256:stale"
    committed_path = tmp_path / "committed-baseline.json"
    committed_path.write_text(json.dumps(committed, indent=2, sort_keys=True), encoding="utf-8")

    check = check_public_baseline(
        tmp_path / "evals",
        committed_report_path=committed_path,
    )

    assert check["ok"] is False
    assert check["status"] == "input_drift"
    assert check["semantic_differences"] == []
    assert check["input_differences"]["committed_digest"] == "sha256:stale"
    assert baseline_check_passes(check) is False
    assert baseline_check_passes(check, allow_input_drift=True) is True


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


def test_inspect_run_writes_logs_summary_and_scorecard(tmp_path: Path) -> None:
    pytest.importorskip("inspect_ai")
    from actionlineage_evals.inspect_tasks import run_inspect_eval

    summary = run_inspect_eval(
        scenario_path=PROJECT_ROOT / "evals" / "scenarios" / "AVL-001.yaml",
        artifact_root=tmp_path / "inspect",
        mode=RunMode.SCRIPTED.value,
        model_adapter="scripted",
        seed=0,
    )

    assert summary["ok"] is True
    assert summary["schema_version"] == "actionlineage.dev/eval-inspect-run-summary-v0"
    assert summary["logs"]
    assert (tmp_path / "inspect" / "inspect-run-summary.json").exists()
    assert (tmp_path / "inspect" / "inspect-logs").exists()
    scorecard = tmp_path / "inspect" / "avl-001-scripted-seed-0" / "scorecard.json"
    assert json.loads(scorecard.read_text(encoding="utf-8"))["passed"] is True


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


def test_stateful_counterexample_minimizer_preserves_failure_predicate() -> None:
    counterexample = deterministic_stateful_counterexample(4, base_scenario_id="AVL-001")

    assert counterexample.counterexample_found is True
    assert len(counterexample.generated_steps) == 4
    assert len(counterexample.minimized_steps) == 1
    assert counterexample.minimized_steps[0].operation == "drop_required_verification_status"
    assert stateful_failure_predicate(counterexample.minimized_steps) is True
    assert counterexample.as_report()["replayable"] is True

    minimized_again = minimize_stateful_steps(
        counterexample.generated_steps,
        still_fails=stateful_failure_predicate,
    )

    assert minimized_again == counterexample.minimized_steps


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

    @rule(seed=st.integers(min_value=0, max_value=20))
    def generate_stateful_counterexample(self, seed: int) -> None:
        counterexample = deterministic_stateful_counterexample(seed, base_scenario_id="AVL-001")
        repeated = deterministic_stateful_counterexample(seed, base_scenario_id="AVL-001")

        assert counterexample == repeated
        assert counterexample.counterexample_found is True
        assert len(counterexample.minimized_steps) == 1
        assert stateful_failure_predicate(counterexample.minimized_steps) is True
        self.generated.append(tuple(step.as_dict() for step in counterexample.minimized_steps))

    @invariant()
    def generated_mutations_are_seeded(self) -> None:
        for sequence in self.generated:
            assert all("seed" in item and "dimension" in item for item in sequence)


TestMutationMachine = MutationMachine.TestCase
