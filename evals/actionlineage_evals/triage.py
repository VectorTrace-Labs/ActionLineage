"""Failure triage reports for development-only eval runs."""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path

from actionlineage_evals.models import ModelTurn, RunMode, RunPaths, ScenarioDefinition, ScoreResult


def write_triage_report(
    path: Path,
    *,
    scenario: ScenarioDefinition,
    mode: RunMode,
    seed: int,
    scorecard: Mapping[str, object],
    scores: tuple[ScoreResult, ...],
    turns: tuple[ModelTurn, ...],
    paths: RunPaths,
) -> None:
    """Write a compact human-readable triage report for one scenario run."""

    failing = next((score for score in scores if not score.ok), None)
    lifecycle = next((score for score in scores if score.name == "lifecycle"), None)
    lines = [
        f"# {scenario.scenario_id} {scenario.name}",
        "",
        f"- verdict: {'passed' if scorecard.get('passed') is True else 'failed'}",
        f"- mode: {mode.value}",
        f"- seed: {seed}",
        f"- failure_class: {scorecard.get('failure_class') or 'none'}",
        f"- first_failing_scorer: {failing.name if failing else 'none'}",
        "",
        "## Errors",
        "",
        *_error_lines(scorecard),
        "",
        "## Lifecycle",
        "",
        *_lifecycle_lines(lifecycle),
        "",
        "## Tool Calls",
        "",
        *_tool_call_lines(turns),
        "",
        "## Replay",
        "",
        "```bash",
        "PYTHONPATH=evals uv run --group eval python -m actionlineage_evals replay \\",
        f"  {paths.replay_bundle_path}",
        "```",
        "",
        "## Artifacts",
        "",
        f"- scorecard: `{paths.scorecard_path}`",
        f"- transcript: `{paths.transcript_path}`",
        f"- tool_calls: `{paths.tool_calls_path}`",
        f"- journal: `{paths.journal_path}`",
        f"- oracle_observations: `{paths.oracle_observations_path}`",
        f"- provenance: `{paths.provenance_path}`",
        f"- replay_equivalence: `{paths.replay_equivalence_path}`",
        f"- minimization_report: `{paths.minimization_report_path}`",
        f"- replay_bundle: `{paths.replay_bundle_path}`",
        "",
        "Authoritative pass/fail comes from scorers and oracles, not model output.",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _error_lines(scorecard: Mapping[str, object]) -> list[str]:
    lines: list[str] = []
    for key in ("provider_error", "agent_error", "harness_error"):
        value = scorecard.get(key)
        if isinstance(value, dict):
            lines.append(f"- {key}: `{value.get('type', 'unknown')}` {value.get('message', '')}")
    return lines or ["- none"]


def _lifecycle_lines(score: ScoreResult | None) -> list[str]:
    if score is None:
        return ["- lifecycle scorer did not run"]
    details = score.details
    missing_statuses = _json_list(details.get("missing_verification_statuses"))
    observed_statuses = _json_list(details.get("observed_verification_statuses"))
    return [
        f"- event_count: {details.get('event_count', 0)}",
        f"- missing_event_types: {_json_list(details.get('missing_event_types'))}",
        f"- missing_verification_statuses: {missing_statuses}",
        f"- forbidden_statuses_present: {_json_list(details.get('forbidden_statuses_present'))}",
        f"- observed_verification_statuses: {observed_statuses}",
    ]


def _tool_call_lines(turns: tuple[ModelTurn, ...]) -> list[str]:
    lines: list[str] = []
    for turn in turns:
        for call in turn.tool_calls:
            safe_fields = {}
            for key in ("mode", "path", "url"):
                value = call.arguments.get(key)
                if isinstance(value, str):
                    safe_fields[key] = value
            lines.append(
                "- "
                f"request_index={turn.request_index} name={call.name} "
                f"argument_keys={sorted(call.arguments)} safe_fields={safe_fields}"
            )
    return lines or ["- none"]


def _json_list(value: object) -> str:
    if isinstance(value, list):
        return json.dumps(value, sort_keys=True)
    return "[]"
