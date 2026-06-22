"""Transcript and tool-call replay bundles."""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

from actionlineage_evals.models import JsonMap, ModelTurn, RunPaths, ScenarioDefinition, ToolCall


def write_transcript(path: Path, turns: tuple[ModelTurn, ...]) -> None:
    """Write model transcript metadata without secrets."""

    _write_json(
        path,
        {
            "schema_version": "actionlineage.dev/eval-transcript/v0",
            "turns": [turn.as_dict() for turn in turns],
        },
    )


def write_tool_calls(path: Path, turns: tuple[ModelTurn, ...]) -> None:
    """Write flattened tool calls for replay."""

    calls = [
        {"request_index": turn.request_index, "tool_call": call.as_dict()}
        for turn in turns
        for call in turn.tool_calls
    ]
    _write_json(path, {"schema_version": "actionlineage.dev/eval-tool-calls/v0", "calls": calls})


def load_transcript(path: Path) -> tuple[ModelTurn, ...]:
    """Load a transcript as replay model turns."""

    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError("transcript must contain a JSON object")
    turns = raw.get("turns", ())
    if not isinstance(turns, list):
        raise ValueError("transcript turns must be a list")
    parsed: list[ModelTurn] = []
    for item in turns:
        if not isinstance(item, dict):
            raise ValueError("transcript turn must be an object")
        raw_calls = item.get("tool_calls", ())
        if not isinstance(raw_calls, list):
            raise ValueError("transcript tool_calls must be a list")
        calls = tuple(
            ToolCall(name=str(call["name"]), arguments=dict(call.get("arguments", {})))
            for call in raw_calls
            if isinstance(call, dict)
        )
        parsed.append(
            ModelTurn(
                content=str(item.get("content", "")),
                tool_calls=calls,
                provider="replay",
                model_id=str(item.get("model_id", "replay/transcript")),
                request_index=int(item.get("request_index", len(parsed))),
                raw={},
            )
        )
    return tuple(parsed)


def write_replay_bundle(
    *,
    scenario: ScenarioDefinition,
    seed: int,
    paths: RunPaths,
    turns: tuple[ModelTurn, ...],
    environment_start: JsonMap,
    scorecard: JsonMap,
) -> None:
    """Write a replay bundle with enough provenance to rerun deterministically."""

    bundle_dir = paths.replay_bundle_path
    bundle_dir.mkdir(parents=True, exist_ok=True)
    copied_journal = bundle_dir / "journal.jsonl"
    copied_mutation_sequence = bundle_dir / "mutation-sequence.json"
    copied_triage = bundle_dir / "triage.md"
    copied_transcript = bundle_dir / "transcript.json"
    shutil.copy2(paths.journal_path, copied_journal)
    if paths.mutation_sequence_path.exists():
        shutil.copy2(paths.mutation_sequence_path, copied_mutation_sequence)
    if paths.triage_path.exists():
        shutil.copy2(paths.triage_path, copied_triage)
    shutil.copy2(paths.transcript_path, copied_transcript)
    manifest: JsonMap = {
        "schema_version": "actionlineage.dev/eval-replay-bundle/v0",
        "environment": environment_start,
        "journal": str(copied_journal.name),
        "model_metadata": [
            {
                "model_id": turn.model_id,
                "provider": turn.provider,
                "request_index": turn.request_index,
            }
            for turn in turns
        ],
        "prompt_hashes": {
            "scenario_path": str(scenario.path),
            "scenario_prompt_digest": _sha256_text(scenario.prompt),
        },
        "scenario": {
            "id": scenario.scenario_id,
            "name": scenario.name,
            "path": str(scenario.path),
        },
        "scorecard": scorecard,
        "seed": seed,
        "mutation_sequence": str(copied_mutation_sequence.name)
        if copied_mutation_sequence.exists()
        else None,
        "tool_calls": str(paths.tool_calls_path),
        "triage": str(copied_triage.name) if copied_triage.exists() else None,
        "transcript": str(copied_transcript.name),
    }
    _write_json(bundle_dir / "manifest.json", manifest)


def promote_regression_bundle(bundle_dir: Path, regression_dir: Path) -> Path:
    """Promote a minimized/dynamic failure bundle into a reviewed corpus path."""

    manifest_path = bundle_dir / "manifest.json"
    raw: Any = json.loads(manifest_path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError("replay bundle manifest must be an object")
    scenario = raw.get("scenario", {})
    scenario_id = scenario.get("id", "unknown") if isinstance(scenario, dict) else "unknown"
    destination = regression_dir / f"{scenario_id}-{_sha256_file(manifest_path)[:16]}"
    if destination.exists():
        shutil.rmtree(destination)
    shutil.copytree(bundle_dir, destination)
    return destination


def discover_regression_bundles(regression_dir: Path) -> tuple[Path, ...]:
    """Return reviewed regression bundle directories under a corpus root."""

    root = Path(regression_dir)
    if not root.exists():
        return ()
    return tuple(sorted(path.parent for path in root.glob("*/manifest.json")))


def _write_json(path: Path, value: JsonMap) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _sha256_text(value: str) -> str:
    import hashlib

    return f"sha256:{hashlib.sha256(value.encode('utf-8')).hexdigest()}"


def _sha256_file(path: Path) -> str:
    import hashlib

    return hashlib.sha256(path.read_bytes()).hexdigest()
