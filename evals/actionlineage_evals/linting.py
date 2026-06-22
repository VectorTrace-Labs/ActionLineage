"""Semantic lint checks for Agent Validation Lab scenarios."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from actionlineage_evals.models import JsonMap, ScenarioDefinition
from actionlineage_evals.scenarios import (
    CAPABILITY_COVERAGE_PATH,
    SCENARIO_DIR,
    load_capability_coverage,
    load_scenarios,
)

REQUIRED_REPLAY_ARTIFACTS = {
    "scenario_manifest",
    "seed",
    "mutation_sequence",
    "model_metadata",
    "prompt_hashes",
    "transcript",
    "tool_calls",
    "oracle_observations",
    "journal",
    "scorecard",
}
REQUIRED_SCORERS = {
    "capability_coverage",
    "failure_classification",
    "integrity",
    "lifecycle",
    "redaction",
    "replayability",
}


@dataclass(frozen=True, slots=True)
class ScenarioLintIssue:
    """One semantic scenario-lint finding."""

    check: str
    message: str
    scenario_id: str | None = None

    def as_dict(self) -> JsonMap:
        data: JsonMap = {"check": self.check, "message": self.message}
        if self.scenario_id is not None:
            data["scenario_id"] = self.scenario_id
        return data


def lint_scenarios(
    *,
    scenario_path: Path = SCENARIO_DIR,
    coverage_path: Path = CAPABILITY_COVERAGE_PATH,
) -> JsonMap:
    """Run semantic lint checks that sit above JSON Schema validation."""

    scenarios = load_scenarios(scenario_path)
    coverage = load_capability_coverage(coverage_path)
    coverage_scenarios = {
        str(item["id"]): item
        for item in coverage.get("scenarios", ())
        if isinstance(item, dict) and "id" in item
    }
    issues: list[ScenarioLintIssue] = []
    issues.extend(_lint_scenario_ids(scenarios))
    for scenario in scenarios:
        coverage_entry = coverage_scenarios.get(scenario.scenario_id)
        issues.extend(_lint_one_scenario(scenario, coverage_entry=coverage_entry))
    return {
        "issue_count": len(issues),
        "issues": [issue.as_dict() for issue in issues],
        "ok": not issues,
        "schema_version": "actionlineage.dev/eval-scenario-lint/v0",
        "scenario_count": len(scenarios),
    }


def _lint_scenario_ids(
    scenarios: tuple[ScenarioDefinition, ...],
) -> tuple[ScenarioLintIssue, ...]:
    ids = [scenario.scenario_id for scenario in scenarios]
    expected = [f"AVL-{index:03d}" for index in range(1, len(ids) + 1)]
    if ids == expected:
        return ()
    return (
        ScenarioLintIssue(
            check="contiguous_ids",
            message=f"scenario IDs must be contiguous: expected {expected}, got {ids}",
        ),
    )


def _lint_one_scenario(
    scenario: ScenarioDefinition,
    *,
    coverage_entry: JsonMap | None,
) -> tuple[ScenarioLintIssue, ...]:
    issues: list[ScenarioLintIssue] = []
    scenario_id = scenario.scenario_id
    if scenario.raw["metadata"]["maturity"] == "planned":
        issues.append(
            ScenarioLintIssue(
                check="development_only_maturity",
                message="implemented eval scenarios must not use planned maturity",
                scenario_id=scenario_id,
            )
        )
    replay = scenario.raw["spec"]["replay"]
    replay_artifacts = set(replay.get("artifacts", ())) if isinstance(replay, dict) else set()
    missing_replay = sorted(REQUIRED_REPLAY_ARTIFACTS - replay_artifacts)
    if missing_replay:
        issues.append(
            ScenarioLintIssue(
                check="replay_artifacts",
                message=f"missing required replay artifacts: {missing_replay}",
                scenario_id=scenario_id,
            )
        )
    oracles = scenario.raw["spec"]["oracles"]
    if isinstance(oracles, list) and any(
        isinstance(oracle, dict) and oracle.get("authoritative") is not True for oracle in oracles
    ):
        issues.append(
            ScenarioLintIssue(
                check="authoritative_oracles",
                message="all declared oracles must be authoritative",
                scenario_id=scenario_id,
            )
        )
    expected = scenario.raw["spec"]["expected"]
    expected_scorers = set(expected.get("scorers", ())) if isinstance(expected, dict) else set()
    missing_scorers = sorted(REQUIRED_SCORERS - expected_scorers)
    if missing_scorers:
        issues.append(
            ScenarioLintIssue(
                check="required_scorers",
                message=f"missing required scorers: {missing_scorers}",
                scenario_id=scenario_id,
            )
        )
    failure_class = str(expected.get("failureClass")) if isinstance(expected, dict) else ""
    if failure_class != "product_failure" and "failure-classification" not in scenario.tags:
        issues.append(
            ScenarioLintIssue(
                check="failure_control_tag",
                message="non-product expected failure classes require failure-classification tag",
                scenario_id=scenario_id,
            )
        )
    if coverage_entry is None:
        issues.append(
            ScenarioLintIssue(
                check="coverage_mapping",
                message="scenario is missing from capability coverage",
                scenario_id=scenario_id,
            )
        )
        return tuple(issues)
    covers = coverage_entry.get("covers", ())
    if not isinstance(covers, list) or not covers:
        issues.append(
            ScenarioLintIssue(
                check="coverage_mapping",
                message="scenario coverage entry must list at least one capability",
                scenario_id=scenario_id,
            )
        )
    oracle_types = {
        str(oracle.get("type"))
        for oracle in oracles
        if isinstance(oracle, dict) and oracle.get("type") is not None
    }
    required_oracles = set(_strings_from_mapping_list(coverage_entry, "required_oracles"))
    missing_oracles = sorted(required_oracles - oracle_types)
    if missing_oracles:
        issues.append(
            ScenarioLintIssue(
                check="required_oracles",
                message=f"coverage-required oracles are not declared: {missing_oracles}",
                scenario_id=scenario_id,
            )
        )
    required_scorers = set(_strings_from_mapping_list(coverage_entry, "required_scorers"))
    missing_declared_scorers = sorted(required_scorers - expected_scorers)
    if missing_declared_scorers:
        issues.append(
            ScenarioLintIssue(
                check="coverage_required_scorers",
                message=(
                    "coverage-required scorers are not declared in expected.scorers: "
                    f"{missing_declared_scorers}"
                ),
                scenario_id=scenario_id,
            )
        )
    return tuple(issues)


def _strings_from_mapping_list(value: JsonMap, key: str) -> tuple[str, ...]:
    raw = value.get(key, ())
    if not isinstance(raw, list):
        return ()
    return tuple(str(item) for item in raw)
