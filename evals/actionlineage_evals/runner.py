"""Standalone scenario runner for the Agent Validation Lab."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from actionlineage.domain import EventType
from actionlineage_evals.adapters import (
    AgentBudgetError,
    LocalToolAgent,
    ProviderError,
    model_adapter_for,
)
from actionlineage_evals.environment import (
    build_environment_controller,
    write_environment_report,
)
from actionlineage_evals.eventing import (
    EventRecorder,
    internal_local_classification,
    observer_source,
    write_json,
)
from actionlineage_evals.models import (
    FailureClass,
    ModelTurn,
    RunMode,
    RunPaths,
    ScenarioDefinition,
    ScenarioResult,
    ScoreResult,
)
from actionlineage_evals.replay import (
    discover_regression_bundles,
    load_transcript,
    promote_regression_bundle,
    write_replay_bundle,
    write_tool_calls,
    write_transcript,
)
from actionlineage_evals.scenarios import load_scenarios
from actionlineage_evals.scoring import classify_failure, score_run, write_scorecard
from actionlineage_evals.tools import ToolHarness, WorldState
from actionlineage_evals.triage import write_triage_report

DEFAULT_ARTIFACT_ROOT = Path("build/evals")
DEFAULT_COMPOSE_FILE = Path("evals/docker/compose.yaml")


class HarnessControlError(RuntimeError):
    """Synthetic harness failure used by deterministic lab-control scenarios."""


@dataclass(frozen=True, slots=True)
class SuiteResult:
    """Result for an eval suite run."""

    passed: bool
    results: tuple[ScenarioResult, ...]

    def as_dict(self) -> dict[str, object]:
        return {
            "passed": self.passed,
            "results": [result.as_dict() for result in self.results],
            "scenario_count": len(self.results),
        }


def run_suite(
    *,
    scenario_path: Path,
    artifact_root: Path = DEFAULT_ARTIFACT_ROOT,
    mode: RunMode = RunMode.SCRIPTED,
    model_adapter_name: str = "scripted",
    model_id: str | None = None,
    seeds: int = 1,
    max_scenarios: int | None = None,
    use_docker: bool = False,
    promote_regressions: bool = False,
) -> SuiteResult:
    """Run a scenario suite."""

    scenarios = load_scenarios(scenario_path)
    if max_scenarios is not None:
        scenarios = scenarios[:max_scenarios]
    results: list[ScenarioResult] = []
    for scenario in scenarios:
        for seed in range(seeds):
            results.append(
                run_scenario(
                    scenario=scenario,
                    artifact_root=artifact_root,
                    mode=mode,
                    model_adapter_name=model_adapter_name,
                    model_id=model_id,
                    seed=seed,
                    use_docker=use_docker,
                    promote_regressions=promote_regressions,
                )
            )
    return SuiteResult(passed=all(result.passed for result in results), results=tuple(results))


def run_scenario(
    *,
    scenario: ScenarioDefinition,
    artifact_root: Path = DEFAULT_ARTIFACT_ROOT,
    mode: RunMode = RunMode.SCRIPTED,
    model_adapter_name: str = "scripted",
    model_id: str | None = None,
    seed: int = 0,
    use_docker: bool = False,
    promote_regressions: bool = False,
    replay_transcript: Path | None = None,
) -> ScenarioResult:
    """Run one scenario and produce a replayable scorecard."""

    run_id = f"{scenario.scenario_id.lower()}-{mode.value}-seed-{seed}"
    paths = _run_paths(Path(artifact_root) / run_id)
    paths.run_dir.mkdir(parents=True, exist_ok=True)
    world = WorldState(run_dir=paths.run_dir, use_docker=use_docker)
    world.prepare()
    environment = build_environment_controller(
        use_docker=use_docker,
        run_id=run_id,
        run_dir=paths.run_dir,
        compose_file=Path(DEFAULT_COMPOSE_FILE),
    )
    environment_start: dict[str, object] = {}
    environment_stop: dict[str, object] = {}
    scores: tuple[ScoreResult, ...] = ()
    failure_class: FailureClass | None = None
    turns: tuple[ModelTurn, ...] = ()
    provider_error: Exception | None = None
    agent_error: Exception | None = None
    harness_error: Exception | None = None
    budget_exhausted = False
    try:
        environment_start = environment.start()
        recorder = EventRecorder(scenario.scenario_id, seed, paths.journal_path)
        recorder.record_intent(prompt=scenario.prompt, scenario_id=scenario.scenario_id)
        replay_turns = load_transcript(replay_transcript) if replay_transcript is not None else ()
        adapter = model_adapter_for(
            adapter=model_adapter_name,
            scenario_id=scenario.scenario_id,
            model_id=model_id,
            replay_turns=replay_turns,
        )
        run_started = recorder.record_run_started(
            mode=mode.value,
            provider=adapter.provider,
            model_id=adapter.model_id,
        )
        agent = LocalToolAgent()
        try:
            turns = agent.run(scenario, adapter)
        except ProviderError as exc:
            provider_error = exc
            turns = ()
        except AgentBudgetError as exc:
            agent_error = exc
            budget_exhausted = True
            turns = ()
        harness = ToolHarness(recorder=recorder, world=world)
        mutation_sequence = _mutation_sequence(scenario, seed)
        if scenario.scenario_id == "AVL-009" and provider_error is None and agent_error is None:
            harness_error = HarnessControlError("synthetic harness oracle failure for AVL-009")
        if provider_error is None and agent_error is None and harness_error is None:
            for turn in turns:
                for call in turn.tool_calls:
                    harness.execute(call)
            _apply_runtime_mutations(
                recorder=recorder,
                scenario=scenario,
                mutation_sequence=mutation_sequence,
            )
        write_json(
            paths.mutation_sequence_path,
            {
                "mutations": mutation_sequence,
                "scenario_id": scenario.scenario_id,
                "schema_version": "actionlineage.dev/eval-mutation-sequence/v0",
                "seed": seed,
            },
        )
        write_transcript(paths.transcript_path, turns)
        write_tool_calls(paths.tool_calls_path, turns)
        world.write_oracle_artifacts(
            observations_path=paths.oracle_observations_path,
            toxiproxy_path=paths.toxiproxy_timeline_path,
        )
        terminal_error = provider_error or agent_error or harness_error
        if terminal_error is None:
            recorder.record_run_completed(passed=True)
        else:
            recorder.record_run_failed(
                error_type=type(terminal_error).__name__,
                message=str(terminal_error),
                parent_event_id=run_started.event_id,
            )
        scores = score_run(scenario=scenario, paths=paths, canary_values=_canaries(scenario, seed))
    except Exception as exc:
        harness_error = exc
        scores = ()
    finally:
        environment_stop = environment.stop()
        write_environment_report(
            paths.environment_path,
            start=environment_start,
            stop=environment_stop,
        )

    failure_class = classify_failure(
        scores=scores,
        agent_error=agent_error,
        provider_error=provider_error,
        harness_error=harness_error,
        budget_exhausted=budget_exhausted,
    )
    scores_ok = bool(scores) and all(score.ok for score in scores)
    expected_failure_class = scenario.mismatch_failure_class
    expected_terminal_failure = (
        expected_failure_class != FailureClass.PRODUCT and failure_class == expected_failure_class
    )
    passed = (failure_class is None and scores_ok) or (expected_terminal_failure and scores_ok)
    scorecard = {
        "agent_error": _error_dict(agent_error),
        "expected_failure_class": expected_failure_class.value,
        "failure_class": failure_class.value if failure_class else None,
        "harness_error": _error_dict(harness_error),
        "passed": passed,
        "provider_error": _error_dict(provider_error),
        "scenario_id": scenario.scenario_id,
        "scores": [score.as_dict() for score in scores],
    }
    write_scorecard(paths.scorecard_path, scorecard)
    write_json(paths.coverage_path, _coverage_report(scenario))
    write_triage_report(
        paths.triage_path,
        scenario=scenario,
        mode=mode,
        seed=seed,
        scorecard=scorecard,
        scores=scores,
        turns=turns,
        paths=paths,
    )
    if paths.transcript_path.exists() and paths.journal_path.exists():
        write_replay_bundle(
            scenario=scenario,
            seed=seed,
            paths=paths,
            turns=turns,
            environment_start=environment_start,
            scorecard=scorecard,
        )
    if promote_regressions and not passed and paths.replay_bundle_path.exists():
        promote_regression_bundle(paths.replay_bundle_path, Path("evals/regressions"))
    return ScenarioResult(
        scenario_id=scenario.scenario_id,
        name=scenario.name,
        passed=passed,
        mode=mode,
        failure_class=failure_class,
        scores=scores,
        artifacts=paths,
    )


def run_regression_corpus(
    *,
    regression_dir: Path,
    artifact_root: Path = DEFAULT_ARTIFACT_ROOT / "regression-replay",
    allow_empty: bool = False,
) -> SuiteResult:
    """Replay reviewed regression bundles without model calls."""

    bundles = discover_regression_bundles(regression_dir)
    if not bundles:
        return SuiteResult(passed=allow_empty, results=())
    results = tuple(
        replay_bundle(bundle, artifact_root=artifact_root / bundle.name) for bundle in bundles
    )
    return SuiteResult(passed=all(result.passed for result in results), results=results)


def replay_artifacts(
    *,
    artifact_root: Path,
    replay_artifact_root: Path,
) -> SuiteResult:
    """Replay every captured replay bundle below an artifact root."""

    manifest_paths = sorted(Path(artifact_root).rglob("replay-bundle/manifest.json"))
    results = tuple(
        replay_bundle(
            manifest_path.parent,
            artifact_root=replay_artifact_root / manifest_path.parent.parent.name,
        )
        for manifest_path in manifest_paths
    )
    return SuiteResult(
        passed=bool(results) and all(result.passed for result in results),
        results=results,
    )


def replay_bundle(
    bundle_dir: Path,
    *,
    artifact_root: Path = DEFAULT_ARTIFACT_ROOT,
) -> ScenarioResult:
    """Replay a captured bundle without provider calls."""

    manifest = json.loads((Path(bundle_dir) / "manifest.json").read_text(encoding="utf-8"))
    scenario_path = Path(manifest["scenario"]["path"])
    scenario = load_scenarios(scenario_path)[0]
    transcript_path = Path(bundle_dir) / str(manifest["transcript"])
    return run_scenario(
        scenario=scenario,
        artifact_root=artifact_root,
        mode=RunMode.REPLAY,
        model_adapter_name="replay",
        seed=int(manifest["seed"]),
        replay_transcript=transcript_path,
    )


def _run_paths(run_dir: Path) -> RunPaths:
    return RunPaths(
        run_dir=run_dir,
        journal_path=run_dir / "journal.jsonl",
        projection_path=run_dir / "projection.sqlite",
        transcript_path=run_dir / "transcript.json",
        tool_calls_path=run_dir / "tool-calls.json",
        oracle_observations_path=run_dir / "oracle-observations.jsonl",
        scorecard_path=run_dir / "scorecard.json",
        replay_bundle_path=run_dir / "replay-bundle",
        coverage_path=run_dir / "capability-coverage.json",
        environment_path=run_dir / "environment.json",
        toxiproxy_timeline_path=run_dir / "toxiproxy-timeline.jsonl",
        mutation_sequence_path=run_dir / "mutation-sequence.json",
        triage_path=run_dir / "triage.md",
    )


def _canaries(scenario: ScenarioDefinition, seed: int) -> tuple[str, ...]:
    return tuple(f"AVL_CANARY_{canary_id}_{seed:04d}" for canary_id in scenario.expected_canary_ids)


def _error_dict(error: Exception | None) -> dict[str, str] | None:
    if error is None:
        return None
    return {"message": str(error), "type": type(error).__name__}


def _coverage_report(scenario: ScenarioDefinition) -> dict[str, object]:
    from actionlineage_evals.scenarios import load_capability_coverage

    coverage = load_capability_coverage()
    capabilities: list[str] = []
    scenarios = coverage.get("scenarios", ())
    if isinstance(scenarios, list):
        for item in scenarios:
            if isinstance(item, dict) and item.get("id") == scenario.scenario_id:
                raw = item.get("covers", ())
                if isinstance(raw, list):
                    capabilities = [str(value) for value in raw]
                break
    return {
        "capabilities": capabilities,
        "coverage_goal": coverage.get("coverage_goal", ""),
        "scenario_id": scenario.scenario_id,
    }


def _mutation_sequence(scenario: ScenarioDefinition, seed: int) -> list[dict[str, object]]:
    mutations: list[dict[str, object]] = []
    for index, mutation in enumerate(scenario.mutations):
        parameters = mutation.get("parameters", {})
        mutations.append(
            {
                "index": index,
                "parameters": parameters if isinstance(parameters, dict) else {},
                "seed": seed + index,
                "semantic_property": _mutation_semantic_property(str(mutation.get("type", ""))),
                "type": str(mutation.get("type", "")),
            }
        )
    return mutations


def _apply_runtime_mutations(
    *,
    recorder: EventRecorder,
    scenario: ScenarioDefinition,
    mutation_sequence: list[dict[str, object]],
) -> None:
    for mutation in mutation_sequence:
        if mutation.get("type") != "duplicate_benign_event":
            continue
        parent_event_id = recorder.events[-1].event_id if recorder.events else None
        for duplicate_index in range(2):
            event = recorder.record(
                EventType.RESOURCE_OBSERVED,
                {
                    "mutation": {
                        "duplicate_index": duplicate_index,
                        "semantic_property": mutation.get("semantic_property"),
                        "type": mutation.get("type"),
                    },
                    "observation": {
                        "benign": True,
                        "status": "observed",
                    },
                    "resource": {
                        "path": f"fixture://benign/{scenario.scenario_id.lower()}.txt",
                        "type": "file",
                    },
                },
                classification=internal_local_classification(),
                parent_event_id=parent_event_id,
                source=observer_source("mutation_oracle"),
            )
            parent_event_id = event.event_id


def _mutation_semantic_property(mutation_type: str) -> str:
    if mutation_type == "duplicate_benign_event":
        return "duplicate benign evidence must not change expected scenario outcome"
    return "declared mutation is tracked for replay provenance"
