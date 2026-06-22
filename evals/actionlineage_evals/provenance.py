"""Run provenance and replay-equivalence helpers for eval artifacts."""

from __future__ import annotations

import hashlib
import os
import subprocess
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from actionlineage_evals.eventing import write_json
from actionlineage_evals.models import JsonMap, RunMode, RunPaths, ScenarioDefinition


def write_run_provenance(
    path: Path,
    *,
    scenario: ScenarioDefinition,
    run_id: str,
    seed: int,
    mode: RunMode,
    model_adapter_name: str,
    model_id: str | None,
    paths: RunPaths,
    environment_start: JsonMap,
) -> None:
    """Write enough deterministic metadata to replay and attribute an eval run."""

    artifact_hashes = {
        name: _hash_file(artifact_path)
        for name, artifact_path in (
            ("journal", paths.journal_path),
            ("mutation_sequence", paths.mutation_sequence_path),
            ("oracle_observations", paths.oracle_observations_path),
            ("toxiproxy_timeline", paths.toxiproxy_timeline_path),
            ("tool_calls", paths.tool_calls_path),
            ("transcript", paths.transcript_path),
        )
        if artifact_path.exists()
    }
    write_json(
        path,
        {
            "artifact_hashes": artifact_hashes,
            "commit": {
                "github_sha": os.environ.get("GITHUB_SHA"),
                "git_head": _git_head(),
            },
            "config_hashes": {
                "capability_coverage": _hash_file(Path("evals/CAPABILITY_COVERAGE.yaml")),
                "scenario": _hash_file(scenario.path),
                "scenario_schema": _hash_file(Path("evals/SCENARIO_SCHEMA.json")),
            },
            "environment": environment_start,
            "generated_at": _utc_now(),
            "model": {
                "adapter": model_adapter_name,
                "model_id": model_id,
            },
            "run": {
                "id": run_id,
                "mode": mode.value,
                "seed": seed,
            },
            "scenario": {
                "id": scenario.scenario_id,
                "maturity": scenario.raw["metadata"]["maturity"],
                "name": scenario.name,
                "path": str(scenario.path),
            },
            "schema_version": "actionlineage.dev/eval-run-provenance/v0",
            "workflow": {
                "event_name": os.environ.get("GITHUB_EVENT_NAME"),
                "run_attempt": os.environ.get("GITHUB_RUN_ATTEMPT"),
                "run_id": os.environ.get("GITHUB_RUN_ID"),
                "workflow": os.environ.get("GITHUB_WORKFLOW"),
            },
        },
    )


def replay_equivalence_report(
    *,
    expected_scorecard: Mapping[str, Any],
    actual_scorecard: Mapping[str, Any],
) -> JsonMap:
    """Return a stable comparison of scorecard essentials for live-vs-replay checks."""

    expected = _scorecard_fingerprint(expected_scorecard)
    actual = _scorecard_fingerprint(actual_scorecard)
    mismatches = sorted(key for key in expected if expected.get(key) != actual.get(key))
    return {
        "actual": actual,
        "expected": expected,
        "mismatches": mismatches,
        "ok": not mismatches,
        "schema_version": "actionlineage.dev/eval-replay-equivalence/v0",
    }


def _scorecard_fingerprint(scorecard: Mapping[str, Any]) -> JsonMap:
    scores = scorecard.get("scores", ())
    score_fingerprints: list[JsonMap] = []
    if isinstance(scores, list):
        for score in scores:
            if isinstance(score, dict):
                score_fingerprints.append(_score_fingerprint(score))
    return {
        "failure_class": scorecard.get("failure_class"),
        "passed": scorecard.get("passed") is True,
        "scenario_id": scorecard.get("scenario_id"),
        "scores": score_fingerprints,
    }


def _score_fingerprint(score: Mapping[str, Any]) -> JsonMap:
    details = score.get("details")
    detail_fingerprint: JsonMap = {}
    if isinstance(details, dict):
        name = str(score.get("name", ""))
        if name == "lifecycle":
            detail_fingerprint = {
                "forbidden_statuses_present": details.get("forbidden_statuses_present", []),
                "missing_event_types": details.get("missing_event_types", []),
                "missing_verification_statuses": details.get(
                    "missing_verification_statuses",
                    [],
                ),
                "observed_event_types": details.get("observed_event_types", []),
                "observed_verification_statuses": details.get(
                    "observed_verification_statuses",
                    [],
                ),
            }
        elif name == "contract":
            detail_fingerprint = {"violations": details.get("violations", [])}
        elif name == "detection":
            detail_fingerprint = {
                "expected_rule_ids": details.get("expected_rule_ids", []),
                "missing_rule_ids": details.get("missing_rule_ids", []),
            }
        elif name == "redaction":
            detail_fingerprint = {
                "canary_count": details.get("canary_count", 0),
                "leaks": details.get("leaks", []),
            }
        elif name == "capability_coverage":
            detail_fingerprint = {"capabilities": details.get("capabilities", [])}
        elif name == "replayability":
            detail_fingerprint = {"missing": details.get("missing", [])}
    return {
        "details": detail_fingerprint,
        "failure_class": score.get("failure_class"),
        "name": score.get("name"),
        "ok": score.get("ok") is True,
    }


def _hash_file(path: Path) -> str | None:
    if not path.exists() or not path.is_file():
        return None
    return f"sha256:{hashlib.sha256(path.read_bytes()).hexdigest()}"


def _git_head() -> str | None:
    try:
        result = subprocess.run(
            ("git", "rev-parse", "HEAD"),
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return None
    return result.stdout.strip()


def _utc_now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")
