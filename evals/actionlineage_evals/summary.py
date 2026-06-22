"""Scorecard summaries for development-only eval artifacts."""

from __future__ import annotations

import json
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from actionlineage_evals.models import FailureClass, JsonMap, ScenarioResult


def summarize_scorecards(root: Path) -> JsonMap:
    """Return a compact summary for every scorecard below an artifact root."""

    root = Path(root)
    scorecard_paths = sorted(root.rglob("scorecard.json")) if root.exists() else []
    items = [_summarize_scorecard(path) for path in scorecard_paths]
    failed = [item for item in items if item["passed"] is not True]
    failure_class_counts: dict[str, int] = {}
    replay_total = 0
    replay_ok = 0
    for item in items:
        failure_class = str(item.get("failure_class") or "none")
        failure_class_counts[failure_class] = failure_class_counts.get(failure_class, 0) + 1
        replay_total += int(item.get("replay_equivalence_count", 0))
        replay_ok += int(item.get("replay_equivalence_ok_count", 0))
    return {
        "failed_count": len(failed),
        "failure_class_counts": failure_class_counts,
        "ok": not failed,
        "replay_equivalence": {"count": replay_total, "ok_count": replay_ok},
        "root": str(root),
        "scenario_count": len(items),
        "scorecards": items,
    }


def summarize_scorecards_text(root: Path) -> str:
    """Return a tabular text summary for humans reading CI logs."""

    summary = summarize_scorecards(root)
    lines = [
        "scenario\tpassed\tfailure_class\tfirst_failing_scorer\treplay_command",
    ]
    for item in summary["scorecards"]:
        if not isinstance(item, dict):
            continue
        lines.append(
            "\t".join(
                (
                    str(item.get("scenario_id", "")),
                    str(item.get("passed", "")),
                    str(item.get("failure_class") or "none"),
                    str(item.get("first_failing_scorer") or "none"),
                    str(item.get("replay_command") or ""),
                )
            )
        )
    return "\n".join(lines) + "\n"


def summarize_scorecards_markdown(root: Path) -> str:
    """Return a compact GitHub Actions Markdown summary."""

    summary = summarize_scorecards(root)
    failure_counts = summary.get("failure_class_counts", {})
    replay = summary.get("replay_equivalence", {})
    lines = [
        "| Metric | Value |",
        "| --- | --- |",
        f"| Root | `{summary['root']}` |",
        f"| Scorecards | {summary['scenario_count']} |",
        f"| Failed | {summary['failed_count']} |",
        f"| Replay equivalence | {replay.get('ok_count', 0)}/{replay.get('count', 0)} OK |",
        f"| Failure classes | `{json.dumps(failure_counts, sort_keys=True)}` |",
        "",
        "| Scenario | Passed | Failure class | First failing scorer | Replay command |",
        "| --- | --- | --- | --- | --- |",
    ]
    for item in summary["scorecards"]:
        if not isinstance(item, dict):
            continue
        lines.append(
            f"| `{item.get('scenario_id', '')}` | {item.get('passed', '')} | "
            f"`{item.get('failure_class') or 'none'}` | "
            f"`{item.get('first_failing_scorer') or 'none'}` | "
            f"`{item.get('replay_command') or ''}` |"
        )
    return "\n".join(lines) + "\n"


def write_suite_summary(path: Path, results: Iterable[ScenarioResult]) -> JsonMap:
    """Write a trendable suite summary beside run artifacts."""

    result_items = tuple(results)
    failure_counts: dict[str, int] = {failure.value: 0 for failure in FailureClass}
    score_counts: dict[str, dict[str, int]] = {}
    for result in result_items:
        if result.failure_class is not None:
            failure_counts[result.failure_class.value] += 1
        for score in result.scores:
            counts = score_counts.setdefault(score.name, {"failed": 0, "passed": 0})
            counts["passed" if score.ok else "failed"] += 1
    value: JsonMap = {
        "failure_class_counts": failure_counts,
        "passed": all(result.passed for result in result_items),
        "scenario_count": len(result_items),
        "scenarios": [
            {
                "failure_class": result.failure_class.value if result.failure_class else None,
                "mode": result.mode.value,
                "passed": result.passed,
                "scenario_id": result.scenario_id,
            }
            for result in result_items
        ],
        "schema_version": "actionlineage.dev/eval-suite-summary/v0",
        "score_counts": score_counts,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return value


def _summarize_scorecard(path: Path) -> JsonMap:
    raw: Any = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError(f"scorecard must be a JSON object: {path}")
    scores = raw.get("scores", ())
    first_failing = None
    if isinstance(scores, list):
        for score in scores:
            if isinstance(score, dict) and score.get("ok") is not True:
                first_failing = str(score.get("name", "unknown"))
                break
    replay_equivalence_scores = (
        [
            score
            for score in scores
            if isinstance(score, dict) and score.get("name") == "replay_equivalence"
        ]
        if isinstance(scores, list)
        else []
    )
    run_dir = path.parent
    replay_bundle = run_dir / "replay-bundle"
    return {
        "failure_class": raw.get("failure_class"),
        "first_failing_scorer": first_failing,
        "passed": raw.get("passed") is True,
        "replay_bundle": str(replay_bundle),
        "replay_command": (
            "PYTHONPATH=evals uv run --group eval python -m actionlineage_evals replay "
            f"{replay_bundle}"
        ),
        "replay_equivalence_count": len(replay_equivalence_scores),
        "replay_equivalence_ok_count": sum(
            1 for score in replay_equivalence_scores if score.get("ok") is True
        ),
        "run_dir": str(run_dir),
        "scenario_id": raw.get("scenario_id"),
        "scorecard": str(path),
    }
