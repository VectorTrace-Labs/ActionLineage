"""Standalone scenario runner for the Agent Validation Lab."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from actionlineage.domain import (
    CorroborationType,
    EventEnvelope,
    EventType,
    EvidenceLink,
    EvidenceRelationship,
    VerificationStatus,
)
from actionlineage.domain.events import event_type_value
from actionlineage_evals.adapters import (
    AgentBudgetError,
    AgentExecutionError,
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
    evidence_link_payload,
    internal_local_classification,
    observer_source,
    verifier_source,
    write_json,
)
from actionlineage_evals.minimization import minimize_tool_calls, tool_call_count
from actionlineage_evals.models import (
    FailureClass,
    JsonMap,
    ModelTurn,
    RunMode,
    RunPaths,
    ScenarioDefinition,
    ScenarioResult,
    ScoreResult,
    ToolCall,
)
from actionlineage_evals.provenance import write_run_provenance
from actionlineage_evals.replay import (
    discover_regression_bundles,
    load_transcript,
    promote_regression_bundle,
    write_replay_bundle,
    write_tool_calls,
    write_transcript,
)
from actionlineage_evals.scenarios import load_scenarios
from actionlineage_evals.scoring import (
    classify_failure,
    score_replay_equivalence,
    score_run,
    write_scorecard,
)
from actionlineage_evals.summary import write_suite_summary
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
    suite = SuiteResult(passed=all(result.passed for result in results), results=tuple(results))
    write_suite_summary(Path(artifact_root) / "suite-summary.json", suite.results)
    return suite


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
    expected_replay_scorecard: JsonMap | None = None,
) -> ScenarioResult:
    """Run one scenario and produce a replayable scorecard."""

    run_id = f"{scenario.scenario_id.lower()}-{mode.value}-seed-{seed}"
    paths = _run_paths(Path(artifact_root) / run_id)
    paths.run_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
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
        world.configure_from_environment(environment_start)
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
        except AgentExecutionError as exc:
            agent_error = exc
            turns = exc.turns
        except AgentBudgetError as exc:
            agent_error = exc
            budget_exhausted = True
            turns = ()
        harness = ToolHarness(recorder=recorder, world=world)
        mutation_sequence = _mutation_sequence(scenario, seed)
        if scenario.scenario_id == "AVL-009" and provider_error is None and agent_error is None:
            harness_error = HarnessControlError("synthetic harness oracle failure for AVL-009")
        if provider_error is None and agent_error is None and harness_error is None:
            if scenario.scenario_id in {"AVL-012", "AVL-013"}:
                try:
                    _execute_concurrent_tool_plan(
                        recorder=recorder,
                        world=world,
                        turns=turns,
                        mode=mode,
                        provider=adapter.provider,
                        model_id=adapter.model_id,
                        contaminate_evidence=scenario.scenario_id == "AVL-013",
                    )
                except AgentExecutionError as exc:
                    agent_error = exc
            else:
                for turn in turns:
                    for call in turn.tool_calls:
                        harness.execute(call)
            if agent_error is None:
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
        write_run_provenance(
            paths.provenance_path,
            scenario=scenario,
            run_id=run_id,
            seed=seed,
            mode=mode,
            model_adapter_name=model_adapter_name,
            model_id=model_id,
            paths=paths,
            environment_start=environment_start,
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
        _is_expected_failure_control(scenario)
        and failure_class == expected_failure_class
        and _only_expected_score_failures(scores, expected_failure_class)
    )
    passed = (failure_class is None and scores_ok) or expected_terminal_failure
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
    if expected_replay_scorecard is not None:
        equivalence_score = score_replay_equivalence(
            expected_scorecard=expected_replay_scorecard,
            actual_scorecard=scorecard,
            report_path=paths.replay_equivalence_path,
        )
        scores = (*scores, equivalence_score)
        failure_class = classify_failure(
            scores=scores,
            agent_error=agent_error,
            provider_error=provider_error,
            harness_error=harness_error,
            budget_exhausted=budget_exhausted,
        )
        scores_ok = bool(scores) and all(score.ok for score in scores)
        expected_terminal_failure = (
            _is_expected_failure_control(scenario)
            and failure_class == expected_failure_class
            and _only_expected_score_failures(scores, expected_failure_class)
        )
        passed = (failure_class is None and scores_ok) or expected_terminal_failure
        scorecard.update(
            {
                "failure_class": failure_class.value if failure_class else None,
                "passed": passed,
                "scores": [score.as_dict() for score in scores],
            }
        )
    write_scorecard(paths.scorecard_path, scorecard)
    if failure_class is not None:
        _write_minimization_artifacts(paths=paths, failure_class=failure_class, turns=turns)
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
        expected_replay_scorecard=manifest.get("scorecard")
        if isinstance(manifest.get("scorecard"), dict)
        else None,
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
        provenance_path=run_dir / "provenance.json",
        replay_equivalence_path=run_dir / "replay-equivalence.json",
        minimization_report_path=run_dir / "minimization-report.json",
        minimized_transcript_path=run_dir / "minimized-transcript.json",
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


def _execute_concurrent_tool_plan(
    *,
    recorder: EventRecorder,
    world: WorldState,
    turns: tuple[ModelTurn, ...],
    mode: RunMode,
    provider: str,
    model_id: str,
    contaminate_evidence: bool = False,
) -> None:
    labels = _concurrent_run_labels(turns)
    for label in labels:
        recorder.record_scoped_run_started(
            mode=mode.value,
            provider=provider,
            model_id=model_id,
            run_label=label,
            coordinator_run_id=recorder.run_id,
        )
    for turn in turns:
        for call in turn.tool_calls:
            run_label = _tool_call_run_label(call)
            ToolHarness(recorder=recorder, world=world, run_label=run_label).execute(call)
    if contaminate_evidence:
        _inject_cross_run_evidence_contamination(recorder=recorder, world=world)
    for label in labels:
        recorder.record_scoped_run_completed(passed=True, run_label=label)


def _concurrent_run_labels(turns: tuple[ModelTurn, ...]) -> tuple[str, ...]:
    labels: list[str] = []
    for turn in turns:
        for call in turn.tool_calls:
            label = _tool_call_run_label(call)
            if label not in labels:
                labels.append(label)
    return tuple(labels)


def _tool_call_run_label(call: ToolCall) -> str:
    if not isinstance(call.arguments.get("run_label"), str):
        raise AgentExecutionError("concurrent tool plan is missing required run_label")
    return str(call.arguments["run_label"])


def _inject_cross_run_evidence_contamination(
    *,
    recorder: EventRecorder,
    world: WorldState,
) -> None:
    agent_a_ack = _first_child_event(
        recorder.events,
        run_id=recorder.run_id_for_label("agent_a"),
        event_type="tool.execution.acknowledged",
    )
    agent_b_observation = _first_child_event(
        recorder.events,
        run_id=recorder.run_id_for_label("agent_b"),
        event_type="side_effect.observed",
    )
    if agent_a_ack is None or agent_b_observation is None:
        raise AgentExecutionError("concurrent contamination control lacks child evidence")
    contamination = recorder.record(
        EventType.SIDE_EFFECT_VERIFIED,
        {
            "contamination_control": {
                "expected_scorer": "run_isolation",
                "mode": "cross_run_evidence_link",
            },
            "evidence_link": evidence_link_payload(
                EvidenceLink(
                    subject_event_id=agent_a_ack.event_id,
                    relationship=EvidenceRelationship.CORROBORATES,
                    evidence_event_id=agent_b_observation.event_id,
                    corroboration_type=CorroborationType.POST_ACTION_READBACK,
                    observer_identity="filesystem_oracle",
                    confidence=0.8,
                    verification_status=VerificationStatus.VERIFIED,
                    limitations=("synthetic cross-run contamination control",),
                )
            ),
        },
        parent_event_id=agent_b_observation.event_id,
        run_label="agent_b",
        source=verifier_source(),
    )
    world.oracle_observations.append(
        {
            "event_id": contamination.event_id,
            "evidence_event_id": agent_b_observation.event_id,
            "evidence_run_id": agent_b_observation.correlation.run_id,
            "status": "cross_run_contaminated",
            "subject_event_id": agent_a_ack.event_id,
            "subject_run_id": agent_a_ack.correlation.run_id,
        }
    )


def _first_child_event(
    events: tuple[EventEnvelope, ...],
    *,
    run_id: str,
    event_type: str,
) -> EventEnvelope | None:
    for event in events:
        if event.correlation.run_id == run_id and event_type_value(event.event_type) == event_type:
            return event
    return None


def _apply_runtime_mutations(
    *,
    recorder: EventRecorder,
    scenario: ScenarioDefinition,
    mutation_sequence: list[dict[str, object]],
) -> None:
    for mutation in mutation_sequence:
        if mutation.get("type") != "duplicate_benign_event":
            if mutation.get("type") in {"event_ordering_skew", "missing_optional_field"}:
                parent_event_id = recorder.events[-1].event_id if recorder.events else None
                recorder.record(
                    EventType.RESOURCE_OBSERVED,
                    {
                        "mutation": {
                            "parameters": mutation.get("parameters", {}),
                            "semantic_property": mutation.get("semantic_property"),
                            "type": mutation.get("type"),
                        },
                        "observation": {
                            "benign": True,
                            "status": "mutation_recorded",
                        },
                        "resource": {
                            "path": f"fixture://mutation/{scenario.scenario_id.lower()}",
                            "type": "fixture",
                        },
                    },
                    classification=internal_local_classification(),
                    parent_event_id=parent_event_id,
                    source=observer_source("mutation_oracle"),
                )
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
    if mutation_type == "missing_optional_field":
        return "optional-field omission must not alter authoritative lifecycle outcome"
    if mutation_type == "event_ordering_skew":
        return "timestamp/order variation must preserve causal parent requirements"
    if mutation_type == "concurrency":
        return "interleaved child runs must preserve run attribution and evidence links"
    return "declared mutation is tracked for replay provenance"


def _write_minimization_artifacts(
    *,
    paths: RunPaths,
    failure_class: FailureClass,
    turns: tuple[ModelTurn, ...],
) -> None:
    if failure_class != FailureClass.AGENT or not turns:
        return
    minimized = minimize_tool_calls(
        turns,
        still_fails=lambda candidate: _preserves_failure_signature(
            candidate,
            failure_class=failure_class,
        ),
    )
    write_transcript(paths.minimized_transcript_path, minimized)
    write_json(
        paths.minimization_report_path,
        {
            "failure_class": failure_class.value,
            "minimized_tool_calls": tool_call_count(minimized),
            "original_tool_calls": tool_call_count(turns),
            "reduced": tool_call_count(minimized) < tool_call_count(turns),
            "schema_version": "actionlineage.dev/eval-minimization-report/v0",
        },
    )


def _preserves_failure_signature(
    turns: tuple[ModelTurn, ...],
    *,
    failure_class: FailureClass,
) -> bool:
    if failure_class != FailureClass.AGENT:
        return bool(turns)
    return any(
        call.name == "safe_files.read" and not isinstance(call.arguments.get("path"), str)
        for turn in turns
        for call in turn.tool_calls
    )


def _is_expected_failure_control(scenario: ScenarioDefinition) -> bool:
    return "failure-classification" in scenario.tags


def _only_expected_score_failures(
    scores: tuple[ScoreResult, ...],
    expected_failure_class: FailureClass,
) -> bool:
    return all(
        score.ok or (score.failure_class or FailureClass.PRODUCT) == expected_failure_class
        for score in scores
    )
