"""Inspect AI task definitions for the development-only Agent Validation Lab."""

# mypy: ignore-errors

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from inspect_ai import Task, task
from inspect_ai import eval as inspect_eval
from inspect_ai.dataset import Sample
from inspect_ai.scorer import Score, Target, accuracy, scorer
from inspect_ai.solver import TaskState, solver

from actionlineage_evals.models import RunMode
from actionlineage_evals.runner import run_scenario
from actionlineage_evals.scenarios import SCENARIO_DIR, load_scenarios

INSPECT_RUN_SUMMARY_SCHEMA_VERSION = "actionlineage.dev/eval-inspect-run-summary-v0"


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


def run_inspect_eval(
    *,
    scenario_path: Path = SCENARIO_DIR,
    artifact_root: Path = Path("build/evals/inspect"),
    mode: str = RunMode.SCRIPTED.value,
    model_adapter: str = "scripted",
    model_id: str | None = None,
    seed: int = 0,
    use_docker: bool = False,
    max_scenarios: int | None = None,
    inspect_model: str = "mockllm/model",
    log_dir: Path | None = None,
    summary_path: Path | None = None,
) -> dict[str, object]:
    """Run the lab through Inspect and write a compact provenance summary."""

    active_log_dir = Path(log_dir) if log_dir is not None else Path(artifact_root) / "inspect-logs"
    logs = inspect_eval(
        agent_validation_lab,
        model=inspect_model,
        task_args={
            "artifact_root": str(artifact_root),
            "max_scenarios": max_scenarios,
            "mode": mode,
            "model_adapter": model_adapter,
            "model_id": model_id,
            "scenario_path": str(scenario_path),
            "seed": seed,
            "use_docker": use_docker,
        },
        display="none",
        log_dir=str(active_log_dir),
        log_format="json",
    )
    log_entries = [_inspect_log_entry(log) for log in logs]
    summary = {
        "artifact_root": str(artifact_root),
        "inspect_log_dir": str(active_log_dir),
        "inspect_model": inspect_model,
        "logs": log_entries,
        "mode": mode,
        "model_adapter": model_adapter,
        "model_id": model_id,
        "ok": all(entry.get("status") == "success" for entry in log_entries),
        "scenario_path": str(scenario_path),
        "schema_version": INSPECT_RUN_SUMMARY_SCHEMA_VERSION,
        "seed": seed,
        "use_docker": use_docker,
    }
    active_summary_path = (
        Path(summary_path)
        if summary_path is not None
        else Path(artifact_root) / "inspect-run-summary.json"
    )
    active_summary_path.parent.mkdir(parents=True, exist_ok=True)
    active_summary_path.write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return summary


def _inspect_log_entry(log: object) -> dict[str, object]:
    status = getattr(log, "status", None)
    location = getattr(log, "location", None)
    eval_info = getattr(log, "eval", None)
    task = getattr(eval_info, "task", None) if eval_info is not None else None
    samples = getattr(log, "samples", None)
    return {
        "location": str(location) if location is not None else None,
        "sample_count": len(samples) if isinstance(samples, list) else None,
        "status": str(status) if status is not None else "unknown",
        "task": str(task) if task is not None else "agent_validation_lab",
    }
