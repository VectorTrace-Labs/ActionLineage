"""Inspect AI task definitions for the development-only Agent Validation Lab."""

# mypy: ignore-errors

from __future__ import annotations

from pathlib import Path
from typing import Any

from inspect_ai import Task, task
from inspect_ai.dataset import Sample
from inspect_ai.scorer import Score, Target, accuracy, scorer
from inspect_ai.solver import TaskState, solver

from actionlineage_evals.models import RunMode
from actionlineage_evals.runner import run_scenario
from actionlineage_evals.scenarios import SCENARIO_DIR, load_scenarios


@solver
def actionlineage_solver(
    *,
    artifact_root: str = "build/evals/inspect",
    mode: str = RunMode.SCRIPTED.value,
    model_adapter: str = "scripted",
    model_id: str | None = None,
    seed: int = 0,
    use_docker: bool = False,
) -> Any:
    """Inspect solver that delegates execution to ActionLineage eval oracles."""

    async def solve(state: TaskState, generate: Any) -> TaskState:
        del generate
        scenario_path = Path(str(state.metadata.get("scenario_path", SCENARIO_DIR)))
        scenarios = load_scenarios(scenario_path)
        scenario_id = str(state.metadata["scenario_id"])
        scenario = next(item for item in scenarios if item.scenario_id == scenario_id)
        active_mode = RunMode(str(state.metadata.get("mode", mode)))
        active_model_id = state.metadata.get("model_id", model_id)
        result = run_scenario(
            scenario=scenario,
            artifact_root=Path(str(state.metadata.get("artifact_root", artifact_root))),
            mode=active_mode,
            model_adapter_name=str(state.metadata.get("model_adapter", model_adapter)),
            model_id=str(active_model_id) if active_model_id else None,
            seed=int(state.metadata.get("seed", seed)),
            use_docker=bool(state.metadata.get("use_docker", use_docker)),
        )
        state.output.completion = "pass" if result.passed else "fail"
        state.metadata["actionlineage_result"] = result.as_dict()
        return state

    return solve


@scorer(metrics=[accuracy()])
def actionlineage_scorer() -> Any:
    """Inspect scorer that trusts only ActionLineage scorecards."""

    async def score(state: TaskState, target: Target) -> Score:
        del target
        result = state.metadata.get("actionlineage_result")
        passed = isinstance(result, dict) and result.get("passed") is True
        return Score(value=1.0 if passed else 0.0, answer=state.output.completion)

    return score


@task
def agent_validation_lab(
    scenario_path: str = str(SCENARIO_DIR),
    *,
    artifact_root: str = "build/evals/inspect",
    mode: str = RunMode.SCRIPTED.value,
    model_adapter: str = "scripted",
    model_id: str | None = None,
    seed: int = 0,
    use_docker: bool = False,
    max_scenarios: int | None = None,
) -> Task:
    """Inspect AI task for the ActionLineage Agent Validation Lab."""

    scenarios = load_scenarios(Path(scenario_path))
    if max_scenarios is not None:
        scenarios = scenarios[:max_scenarios]
    samples = [
        Sample(
            id=scenario.scenario_id,
            input=scenario.prompt,
            target="pass",
            metadata={
                "artifact_root": artifact_root,
                "mode": mode,
                "model_adapter": model_adapter,
                "model_id": model_id,
                "scenario_id": scenario.scenario_id,
                "scenario_path": scenario_path,
                "seed": seed,
                "use_docker": use_docker,
            },
        )
        for scenario in scenarios
    ]
    return Task(
        dataset=samples,
        solver=actionlineage_solver(
            artifact_root=artifact_root,
            mode=mode,
            model_adapter=model_adapter,
            model_id=model_id,
            seed=seed,
            use_docker=use_docker,
        ),
        scorer=actionlineage_scorer(),
    )
