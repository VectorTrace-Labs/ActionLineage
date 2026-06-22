"""Scorecard summaries for development-only eval artifacts."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from actionlineage_evals.models import JsonMap


def summarize_scorecards(root: Path) -> JsonMap:
    """Return a compact summary for every scorecard below an artifact root."""

    root = Path(root)
    scorecard_paths = sorted(root.rglob("scorecard.json")) if root.exists() else []
    items = [_summarize_scorecard(path) for path in scorecard_paths]
    failed = [item for item in items if item["passed"] is not True]
    return {
        "failed_count": len(failed),
        "ok": not failed,
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
        "run_dir": str(run_dir),
        "scenario_id": raw.get("scenario_id"),
        "scorecard": str(path),
    }
