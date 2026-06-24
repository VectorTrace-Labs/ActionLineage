"""Freshness checks for committed Agent Validation baseline evidence."""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from actionlineage_evals.models import JsonMap
from actionlineage_evals.scenarios import (
    CAPABILITY_COVERAGE_PATH,
    SCENARIO_DIR,
    SCENARIO_SCHEMA_PATH,
)
from actionlineage_evals.summary import build_public_baseline_report

BASELINE_CHECK_SCHEMA_VERSION = "actionlineage.dev/agent-validation-baseline-check-v0"
DEFAULT_COMMITTED_BASELINE = Path("docs/evidence/agent-validation-baseline.json")


def check_public_baseline(
    artifact_root: Path,
    *,
    committed_report_path: Path = DEFAULT_COMMITTED_BASELINE,
    scenario_path: Path = SCENARIO_DIR,
    coverage_path: Path = CAPABILITY_COVERAGE_PATH,
    schema_path: Path = SCENARIO_SCHEMA_PATH,
) -> JsonMap:
    """Compare committed public baseline evidence with regenerated artifacts."""

    committed = _load_json(committed_report_path)
    current = build_public_baseline_report(
        artifact_root,
        scenario_path=scenario_path,
        coverage_path=coverage_path,
        schema_path=schema_path,
    )
    committed_semantic = semantic_public_baseline_report(committed)
    current_semantic = semantic_public_baseline_report(current)
    semantic_differences = _diff_json(committed_semantic, current_semantic)
    input_differences = _diff_baseline_inputs(committed, current)
    provenance_differences = _provenance_differences(committed, current)

    if semantic_differences:
        status = "semantic_drift"
    elif input_differences:
        status = "input_drift"
    elif provenance_differences:
        status = "provenance_only_drift"
    else:
        status = "matched"

    return {
        "committed_report": {
            "baseline_input_digest": _baseline_input_digest(committed),
            "commit_sha": committed.get("commit_sha"),
            "path": str(committed_report_path),
            "source_commits": committed.get("source_commits", []),
        },
        "current_report": {
            "artifact_root": str(artifact_root),
            "baseline_input_digest": _baseline_input_digest(current),
            "commit_sha": current.get("commit_sha"),
            "source_commits": current.get("source_commits", []),
        },
        "input_differences": input_differences,
        "ok": not semantic_differences and not input_differences,
        "provenance_differences": provenance_differences,
        "schema_version": BASELINE_CHECK_SCHEMA_VERSION,
        "semantic_differences": semantic_differences,
        "status": status,
    }


def baseline_check_passes(report: Mapping[str, Any], *, allow_input_drift: bool = False) -> bool:
    """Return whether a baseline-check report passes the selected gate policy."""

    if allow_input_drift:
        return not bool(report.get("semantic_differences"))
    return bool(report.get("ok"))


def semantic_public_baseline_report(report: Mapping[str, Any]) -> JsonMap:
    """Return only release-relevant public-baseline semantics."""

    return {
        "capability_coverage": report.get("capability_coverage"),
        "coverage": report.get("coverage"),
        "environment_identifiers": report.get("environment_identifiers"),
        "failure_classification": report.get("failure_classification"),
        "hard_assertion_results": report.get("hard_assertion_results"),
        "limitations": report.get("limitations"),
        "model_adapters": report.get("model_adapters"),
        "ok": report.get("ok"),
        "runs": _semantic_runs(report),
        "scenario_ids": report.get("scenario_ids"),
        "scenario_schema": _semantic_scenario_schema(report),
        "schema_version": report.get("schema_version"),
        "seeds": report.get("seeds"),
        "suite": report.get("suite"),
        "tool_schema_hashes": report.get("tool_schema_hashes"),
    }


def _semantic_runs(report: Mapping[str, Any]) -> list[JsonMap]:
    runs = report.get("runs", [])
    if not isinstance(runs, list):
        return []
    semantic_runs: list[JsonMap] = []
    for run in runs:
        if not isinstance(run, dict):
            continue
        semantic_runs.append(
            {
                "capabilities": run.get("capabilities", []),
                "descriptor_hashes": run.get("descriptor_hashes", []),
                "event_count": run.get("event_count"),
                "event_types": run.get("event_types", []),
                "expected_failure_class": run.get("expected_failure_class"),
                "failure_class": run.get("failure_class"),
                "failure_fingerprint": run.get("failure_fingerprint"),
                "mode": run.get("mode"),
                "model_adapter": run.get("model_adapter"),
                "passed": run.get("passed"),
                "scenario_id": run.get("scenario_id"),
                "scenario_name": run.get("scenario_name"),
                "seed": run.get("seed"),
                "verification_statuses": run.get("verification_statuses", []),
            }
        )
    return sorted(semantic_runs, key=lambda item: str(item.get("scenario_id", "")))


def _semantic_scenario_schema(report: Mapping[str, Any]) -> JsonMap:
    raw = report.get("scenario_schema")
    if not isinstance(raw, dict):
        return {}
    return {
        "api_versions": raw.get("api_versions", []),
        "schema_version": raw.get("schema_version"),
    }


def _diff_baseline_inputs(committed: Mapping[str, Any], current: Mapping[str, Any]) -> JsonMap:
    committed_inputs = committed.get("baseline_inputs")
    current_inputs = current.get("baseline_inputs")
    if not isinstance(committed_inputs, dict) or not isinstance(current_inputs, dict):
        return {
            "reason": "missing_baseline_inputs",
            "committed_has_inputs": isinstance(committed_inputs, dict),
            "current_has_inputs": isinstance(current_inputs, dict),
        }
    committed_digest = committed_inputs.get("digest")
    current_digest = current_inputs.get("digest")
    if committed_digest == current_digest:
        return {}

    committed_files = _input_files_by_path(committed_inputs)
    current_files = _input_files_by_path(current_inputs)
    committed_paths = set(committed_files)
    current_paths = set(current_files)
    shared_paths = committed_paths & current_paths
    return {
        "added_paths": sorted(current_paths - committed_paths),
        "changed_paths": sorted(
            path
            for path in shared_paths
            if committed_files[path].get("sha256") != current_files[path].get("sha256")
        ),
        "committed_digest": committed_digest,
        "current_digest": current_digest,
        "removed_paths": sorted(committed_paths - current_paths),
    }


def _input_files_by_path(inputs: Mapping[str, Any]) -> dict[str, JsonMap]:
    raw_files = inputs.get("files", [])
    if not isinstance(raw_files, list):
        return {}
    files: dict[str, JsonMap] = {}
    for item in raw_files:
        if isinstance(item, dict) and item.get("path"):
            files[str(item["path"])] = dict(item)
    return files


def _provenance_differences(committed: Mapping[str, Any], current: Mapping[str, Any]) -> JsonMap:
    differences: JsonMap = {}
    for key in ("artifact_root", "commit_sha", "source_commits", "reproduction_commands"):
        if committed.get(key) != current.get(key):
            differences[key] = {
                "committed": committed.get(key),
                "current": current.get(key),
            }
    return differences


def _diff_json(left: object, right: object, *, path: str = "$") -> list[JsonMap]:
    if type(left) is not type(right):
        return [{"path": path, "committed": left, "current": right}]
    if isinstance(left, dict) and isinstance(right, dict):
        differences: list[JsonMap] = []
        for key in sorted(set(left) | set(right)):
            child_path = f"{path}.{key}"
            if key not in left:
                differences.append({"path": child_path, "committed": None, "current": right[key]})
            elif key not in right:
                differences.append({"path": child_path, "committed": left[key], "current": None})
            else:
                differences.extend(_diff_json(left[key], right[key], path=child_path))
        return differences
    if isinstance(left, list) and isinstance(right, list):
        differences = []
        if len(left) != len(right):
            differences.append(
                {"path": f"{path}.length", "committed": len(left), "current": len(right)}
            )
        for index, (left_item, right_item) in enumerate(zip(left, right, strict=False)):
            differences.extend(_diff_json(left_item, right_item, path=f"{path}[{index}]"))
        return differences
    if left != right:
        return [{"path": path, "committed": left, "current": right}]
    return []


def _baseline_input_digest(report: Mapping[str, Any]) -> str | None:
    inputs = report.get("baseline_inputs")
    if not isinstance(inputs, dict):
        return None
    digest = inputs.get("digest")
    return str(digest) if digest else None


def _load_json(path: Path) -> JsonMap:
    raw: object = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError(f"expected JSON object: {path}")
    return raw
