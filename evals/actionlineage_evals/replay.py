"""Transcript and tool-call replay bundles."""

from __future__ import annotations

import json
import re
import shutil
from datetime import UTC, datetime
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
        "reviewed": False,
        "mutation_sequence": str(copied_mutation_sequence.name)
        if copied_mutation_sequence.exists()
        else None,
        "tool_calls": str(paths.tool_calls_path),
        "triage": str(copied_triage.name) if copied_triage.exists() else None,
        "transcript": str(copied_transcript.name),
    }
    _write_json(bundle_dir / "manifest.json", manifest)


def promote_regression_bundle(
    bundle_dir: Path,
    regression_dir: Path,
    *,
    reviewed: bool = False,
    reviewed_by: str | None = None,
    reason: str | None = None,
    source_run: str | None = None,
) -> Path:
    """Promote a minimized/dynamic failure bundle into a reviewed corpus path."""

    manifest_path = bundle_dir / "manifest.json"
    raw: Any = json.loads(manifest_path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError("replay bundle manifest must be an object")
    scenario = raw.get("scenario", {})
    scenario_id = scenario.get("id", "unknown") if isinstance(scenario, dict) else "unknown"
    if reviewed:
        _validate_review_metadata(
            reviewed_by=reviewed_by,
            reason=reason,
            source_run=source_run,
        )
        _validate_reviewed_bundle(bundle_dir, raw)
    parent = regression_dir if reviewed else regression_dir / "_candidates"
    destination = parent / f"{scenario_id}-{_sha256_file(manifest_path)[:16]}"
    if destination.exists():
        shutil.rmtree(destination)
    shutil.copytree(bundle_dir, destination)
    promoted_manifest: Any = json.loads((destination / "manifest.json").read_text(encoding="utf-8"))
    if not isinstance(promoted_manifest, dict):
        raise ValueError("promoted replay bundle manifest must be an object")
    promoted_manifest["reviewed"] = reviewed
    if reviewed:
        promoted_manifest["review"] = {
            "failure_class": _manifest_failure_class(promoted_manifest),
            "policy": "synthetic redacted reviewed regression corpus",
            "reason": reason,
            "reviewed_at": _utc_now(),
            "reviewed_by": reviewed_by,
            "source_run": source_run,
            "status": "reviewed",
        }
    _write_json(destination / "manifest.json", promoted_manifest)
    return destination


def discover_regression_bundles(regression_dir: Path) -> tuple[Path, ...]:
    """Return reviewed regression bundle directories under a corpus root."""

    root = Path(regression_dir)
    if not root.exists():
        return ()
    bundles: list[Path] = []
    for path in sorted(root.glob("*/manifest.json")):
        raw: Any = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            raise ValueError(f"regression manifest must be an object: {path}")
        if raw.get("reviewed") is not True:
            raise ValueError(f"regression bundle is not reviewed: {path.parent}")
        bundles.append(path.parent)
    return tuple(bundles)


def _validate_reviewed_bundle(bundle_dir: Path, manifest: JsonMap) -> None:
    _reject_live_provider_metadata(manifest)
    _manifest_failure_class(manifest)
    forbidden = (
        re.compile(r"AVL_CANARY_[A-Za-z0-9_-]+"),
        re.compile(r"Bearer\s+[A-Za-z0-9._~+/=-]+"),
        re.compile(r"ghp_[A-Za-z0-9_]+"),
        re.compile(r"github_pat_[A-Za-z0-9_]+"),
        re.compile(r"sk-[A-Za-z0-9_-]+"),
    )
    for path in sorted(Path(bundle_dir).rglob("*")):
        if not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        for pattern in forbidden:
            if pattern.search(text):
                raise ValueError(f"reviewed regression bundle contains forbidden text: {path}")


def _validate_review_metadata(
    *,
    reviewed_by: str | None,
    reason: str | None,
    source_run: str | None,
) -> None:
    missing = [
        name
        for name, value in (
            ("reviewed_by", reviewed_by),
            ("reason", reason),
            ("source_run", source_run),
        )
        if value is None or not value.strip()
    ]
    if missing:
        raise ValueError(f"reviewed regression promotion requires: {', '.join(missing)}")


def _manifest_failure_class(manifest: JsonMap) -> str:
    scorecard = manifest.get("scorecard")
    if not isinstance(scorecard, dict):
        raise ValueError("reviewed regression bundle scorecard must be an object")
    failure_class = scorecard.get("failure_class")
    if not isinstance(failure_class, str) or not failure_class:
        raise ValueError("reviewed regression bundle must include scorecard.failure_class")
    return failure_class


def _reject_live_provider_metadata(manifest: JsonMap) -> None:
    metadata = manifest.get("model_metadata", ())
    if not isinstance(metadata, list):
        raise ValueError("replay bundle model_metadata must be a list")
    allowed_providers = {"replay", "scripted"}
    for item in metadata:
        if not isinstance(item, dict):
            raise ValueError("replay bundle model metadata entries must be objects")
        provider = str(item.get("provider", "unknown"))
        if provider not in allowed_providers:
            raise ValueError(f"reviewed regression bundle cannot contain live provider: {provider}")


def _write_json(path: Path, value: JsonMap) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _sha256_text(value: str) -> str:
    import hashlib

    return f"sha256:{hashlib.sha256(value.encode('utf-8')).hexdigest()}"


def _sha256_file(path: Path) -> str:
    import hashlib

    return hashlib.sha256(path.read_bytes()).hexdigest()


def _utc_now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")
