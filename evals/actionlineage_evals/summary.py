"""Scorecard summaries for development-only eval artifacts."""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from collections.abc import Iterable
from itertools import pairwise
from pathlib import Path
from typing import Any

from actionlineage.domain import event_to_dict
from actionlineage.journal import JournalError, LocalJournal
from actionlineage_evals.models import FailureClass, JsonMap, ScenarioResult
from actionlineage_evals.scenarios import (
    CAPABILITY_COVERAGE_PATH,
    SCENARIO_DIR,
    SCENARIO_SCHEMA_PATH,
    load_scenarios,
    load_schema,
    validate_capability_coverage,
)

PUBLIC_REPORT_SCHEMA_VERSION = "actionlineage.dev/agent-validation-public-report-v0"
BASELINE_INPUTS_SCHEMA_VERSION = "actionlineage.dev/agent-validation-baseline-inputs-v0"

BASELINE_INPUT_PATHS = (
    Path(".github/uv-version.txt"),
    Path(".github/workflows/agent-validation.yml"),
    Path("contracts/examples"),
    Path("detections/examples"),
    Path("evals/CAPABILITY_COVERAGE.yaml"),
    Path("evals/SCENARIO_SCHEMA.json"),
    Path("evals/actionlineage_evals"),
    Path("evals/docker"),
    Path("evals/regressions/README.md"),
    Path("evals/scenarios"),
    Path("pyproject.toml"),
    Path("schemas/actionlineage-event-v1alpha1.schema.json"),
    Path("src/actionlineage/contracts"),
    Path("src/actionlineage/detection"),
    Path("src/actionlineage/domain"),
    Path("src/actionlineage/journal"),
    Path("src/actionlineage/observers"),
    Path("src/actionlineage/projection"),
    Path("uv.lock"),
)
BASELINE_INPUT_SUFFIXES = {
    ".json",
    ".lock",
    ".md",
    ".py",
    ".toml",
    ".txt",
    ".yaml",
    ".yml",
}
BASELINE_INPUT_EXCLUDED_PARTS = {
    "__pycache__",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
}


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
        (
            "scenario\tpassed\tfailure_class\tfirst_failing_scorer\t"
            "failure_fingerprint\treplay_command"
        ),
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
                    str(item.get("failure_fingerprint") or "none"),
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
        (
            "| Scenario | Passed | Failure class | First failing scorer | "
            "Failure fingerprint | Replay command |"
        ),
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for item in summary["scorecards"]:
        if not isinstance(item, dict):
            continue
        lines.append(
            f"| `{item.get('scenario_id', '')}` | {item.get('passed', '')} | "
            f"`{item.get('failure_class') or 'none'}` | "
            f"`{item.get('first_failing_scorer') or 'none'}` | "
            f"`{item.get('failure_fingerprint') or 'none'}` | "
            f"`{item.get('replay_command') or ''}` |"
        )
    return "\n".join(lines) + "\n"


def build_public_baseline_report(
    artifact_root: Path,
    *,
    scenario_path: Path = SCENARIO_DIR,
    coverage_path: Path = CAPABILITY_COVERAGE_PATH,
    schema_path: Path = SCENARIO_SCHEMA_PATH,
) -> JsonMap:
    """Build the deterministic public no-model baseline report."""

    artifact_root = Path(artifact_root)
    scenarios = load_scenarios(scenario_path)
    scenario_schema = load_schema(schema_path)
    capability_coverage = validate_capability_coverage(coverage_path, strict=True)
    summary = summarize_scorecards(artifact_root)
    scorecard_paths = (
        sorted(artifact_root.rglob("scorecard.json")) if artifact_root.exists() else []
    )

    event_type_counts: Counter[str] = Counter()
    lifecycle_transition_counts: Counter[str] = Counter()
    verification_status_counts: Counter[str] = Counter()
    evidence_relationship_counts: Counter[str] = Counter()
    evidence_corroboration_counts: Counter[str] = Counter()
    contract_counts: Counter[str] = Counter()
    detection_counts: Counter[str] = Counter()
    score_counts: dict[str, dict[str, int]] = {}
    failure_class_counts: Counter[str] = Counter()
    source_commits: set[str] = set()
    seeds: set[int] = set()
    model_adapters: dict[str, JsonMap] = {}
    environment_identifiers: set[str] = set()
    tool_identities: dict[tuple[str, str], JsonMap] = {}
    run_reports: list[JsonMap] = []
    expected_control_scenarios: list[JsonMap] = []

    for scorecard_path in scorecard_paths:
        run_dir = scorecard_path.parent
        scorecard = _load_json(scorecard_path)
        provenance = _load_optional_json(run_dir / "provenance.json")
        environment = _load_optional_json(run_dir / "environment.json")
        capability_report = _load_optional_json(run_dir / "capability-coverage.json")
        events = _load_journal_events(run_dir / "journal.jsonl")
        event_types = [
            str(event.get("event_type", "")) for event in events if event.get("event_type")
        ]
        event_type_counts.update(event_types)
        lifecycle_transition_counts.update(
            f"{left} -> {right}" for left, right in pairwise(event_types)
        )

        run_tool_identities: dict[tuple[str, str], JsonMap] = {}
        for event in events:
            payload = event.get("payload")
            for identity in _collect_tool_identities(payload):
                key = (str(identity["name"]), str(identity["descriptor_hash"]))
                tool_identities[key] = identity
                run_tool_identities[key] = identity
            evidence_link = payload.get("evidence_link") if isinstance(payload, dict) else None
            if isinstance(evidence_link, dict):
                status = str(evidence_link.get("verification_status", "unknown"))
                relationship = str(evidence_link.get("relationship", "unknown"))
                corroboration = str(evidence_link.get("corroboration_type", "unknown"))
                verification_status_counts[status] += 1
                evidence_relationship_counts[relationship] += 1
                evidence_corroboration_counts[corroboration] += 1

        scores = scorecard.get("scores", ())
        if isinstance(scores, list):
            for score in scores:
                if not isinstance(score, dict):
                    continue
                score_name = str(score.get("name", "unknown"))
                score_bucket = score_counts.setdefault(score_name, {"failed": 0, "passed": 0})
                score_bucket["passed" if score.get("ok") is True else "failed"] += 1
                details = score.get("details")
                if score_name == "contract" and isinstance(details, dict):
                    contract_counts["passed" if details.get("ok") is True else "failed"] += 1
                if score_name == "detection" and isinstance(details, dict):
                    missing = details.get("missing_rule_ids", ())
                    matches = details.get("matches", ())
                    if isinstance(matches, list):
                        detection_counts["matches"] += len(matches)
                    if isinstance(missing, list):
                        detection_counts["missing_rules"] += len(missing)

        failure_class = str(scorecard.get("failure_class") or "none")
        failure_class_counts[failure_class] += 1
        failed_score_names = (
            [
                str(score.get("name", "unknown"))
                for score in scores
                if isinstance(score, dict) and score.get("ok") is not True
            ]
            if isinstance(scores, list)
            else []
        )
        if failure_class != "none" and scorecard.get("passed") is True:
            expected_control_scenarios.append(
                {
                    "failed_scores": failed_score_names,
                    "failure_class": failure_class,
                    "scenario_id": str(scorecard.get("scenario_id")),
                }
            )

        commit = provenance.get("commit") if isinstance(provenance.get("commit"), dict) else {}
        git_head = commit.get("git_head") if isinstance(commit, dict) else None
        if git_head:
            source_commits.add(str(git_head))
        run = provenance.get("run") if isinstance(provenance.get("run"), dict) else {}
        if isinstance(run, dict) and "seed" in run:
            seeds.add(int(run["seed"]))
        model = provenance.get("model") if isinstance(provenance.get("model"), dict) else {}
        adapter = str(model.get("adapter", "unknown")) if isinstance(model, dict) else "unknown"
        model_adapters[adapter] = {
            "adapter": adapter,
            "model_id": model.get("model_id") if isinstance(model, dict) else None,
            "no_model": adapter == "scripted",
        }
        env_start = environment.get("start") if isinstance(environment.get("start"), dict) else {}
        controller = (
            str(env_start.get("controller", "unknown"))
            if isinstance(env_start, dict)
            else "unknown"
        )
        deterministic = (
            bool(env_start.get("deterministic")) if isinstance(env_start, dict) else False
        )
        environment_identifiers.add(
            json.dumps(
                {
                    "controller": controller,
                    "deterministic": deterministic,
                    "image": "fixture" if controller == "fixture" else "external",
                },
                sort_keys=True,
            )
        )

        scenario = (
            provenance.get("scenario") if isinstance(provenance.get("scenario"), dict) else {}
        )
        artifact_paths = {
            "capability_coverage": str(run_dir / "capability-coverage.json"),
            "environment": str(run_dir / "environment.json"),
            "journal": str(run_dir / "journal.jsonl"),
            "mutation_sequence": str(run_dir / "mutation-sequence.json"),
            "oracle_observations": str(run_dir / "oracle-observations.jsonl"),
            "provenance": str(run_dir / "provenance.json"),
            "replay_bundle": str(run_dir / "replay-bundle"),
            "scorecard": str(scorecard_path),
            "tool_calls": str(run_dir / "tool-calls.json"),
            "transcript": str(run_dir / "transcript.json"),
            "triage": str(run_dir / "triage.md"),
        }
        run_reports.append(
            {
                "artifact_paths": artifact_paths,
                "capabilities": capability_report.get("capabilities", [])
                if isinstance(capability_report, dict)
                else [],
                "descriptor_hashes": sorted(
                    identity["descriptor_hash"] for identity in run_tool_identities.values()
                ),
                "event_count": len(events),
                "event_types": sorted(set(event_types)),
                "expected_failure_class": scorecard.get("expected_failure_class"),
                "failure_class": failure_class,
                "failure_fingerprint": _scorecard_failure_fingerprint(scorecard),
                "model_adapter": adapter,
                "mode": run.get("mode") if isinstance(run, dict) else None,
                "passed": scorecard.get("passed") is True,
                "scenario_id": scorecard.get("scenario_id"),
                "scenario_name": scenario.get("name") if isinstance(scenario, dict) else None,
                "seed": run.get("seed") if isinstance(run, dict) else None,
                "verification_statuses": sorted(_run_verification_statuses(events)),
            }
        )

    scenario_api_versions = sorted({str(scenario.raw.get("apiVersion")) for scenario in scenarios})
    report: JsonMap = {
        "artifact_root": str(artifact_root),
        "baseline_inputs": baseline_input_fingerprint(),
        "capability_coverage": capability_coverage,
        "commit_sha": sorted(source_commits)[0] if len(source_commits) == 1 else None,
        "coverage": {
            "contract_coverage": dict(sorted(contract_counts.items())),
            "detection_coverage": dict(sorted(detection_counts.items())),
            "event_type_coverage": dict(sorted(event_type_counts.items())),
            "evidence_link_coverage": {
                "corroboration_types": dict(sorted(evidence_corroboration_counts.items())),
                "relationships": dict(sorted(evidence_relationship_counts.items())),
                "verification_statuses": dict(sorted(verification_status_counts.items())),
            },
            "lifecycle_transition_coverage": dict(sorted(lifecycle_transition_counts.items())),
        },
        "environment_identifiers": [json.loads(value) for value in sorted(environment_identifiers)],
        "failure_classification": {
            "counts": dict(sorted(failure_class_counts.items())),
            "classes_remain_distinct": True,
            "expected_control_scenarios": sorted(
                expected_control_scenarios,
                key=lambda item: str(item["scenario_id"]),
            ),
        },
        "hard_assertion_results": {
            "score_counts": {key: score_counts[key] for key in sorted(score_counts)},
            "suite_passed": summary["ok"],
        },
        "limitations": [
            "Development-only deterministic baseline; not a live-model reliability claim.",
            "Scripted adapter output is not treated as an authoritative product oracle.",
            (
                "Generated run artifacts are reproducible under the artifact root "
                "and are not committed."
            ),
        ],
        "model_adapters": [model_adapters[key] for key in sorted(model_adapters)],
        "ok": summary["ok"] is True and capability_coverage.get("ok") is True,
        "reproduction_commands": _public_report_reproduction_commands(artifact_root),
        "runs": sorted(run_reports, key=lambda item: str(item.get("scenario_id", ""))),
        "scenario_ids": [scenario.scenario_id for scenario in scenarios],
        "scenario_schema": {
            "api_versions": scenario_api_versions,
            "schema_path": str(schema_path),
            "schema_version": scenario_schema.get("$id"),
        },
        "schema_version": PUBLIC_REPORT_SCHEMA_VERSION,
        "seeds": sorted(seeds),
        "source_commits": sorted(source_commits),
        "suite": {
            "failed_count": summary["failed_count"],
            "scorecard_count": summary["scenario_count"],
            "scenario_count": len(scenarios),
        },
        "tool_schema_hashes": sorted(
            tool_identities.values(),
            key=lambda item: (str(item["name"]), str(item["descriptor_hash"])),
        ),
    }
    return report


def baseline_input_fingerprint(project_root: Path = Path(".")) -> JsonMap:
    """Return the deterministic input fingerprint for public eval evidence."""

    root = Path(project_root)
    file_records: list[JsonMap] = []
    for path in _iter_baseline_input_files(root):
        relative_path = path.relative_to(root)
        file_records.append(
            {
                "path": relative_path.as_posix(),
                "sha256": _hash_file(path),
            }
        )
    digest = hashlib.sha256()
    for record in file_records:
        digest.update(str(record["path"]).encode("utf-8"))
        digest.update(b"\0")
        digest.update(str(record["sha256"]).encode("utf-8"))
        digest.update(b"\n")
    return {
        "digest": f"sha256:{digest.hexdigest()}",
        "file_count": len(file_records),
        "files": file_records,
        "input_roots": [path.as_posix() for path in BASELINE_INPUT_PATHS],
        "schema_version": BASELINE_INPUTS_SCHEMA_VERSION,
    }


def render_public_baseline_report_markdown(report: JsonMap) -> str:
    """Render a public baseline report as deterministic Markdown."""

    coverage = report["coverage"]
    evidence = coverage["evidence_link_coverage"]
    suite = report["suite"]
    failure = report["failure_classification"]["counts"]
    commands = report["reproduction_commands"]
    lines = [
        "# Agent Validation Baseline Evidence",
        "",
        (
            "This deterministic report is generated from the development-only no-model "
            + "Agent Validation Lab artifacts. It is local proof, not external validation "
            + "and not a live-model reliability claim."
        ),
        "",
        "## Summary",
        "",
        "| Field | Value |",
        "| --- | --- |",
        f"| Schema | `{report['schema_version']}` |",
        f"| Source commit under evaluation | `{report.get('commit_sha') or 'mixed'}` |",
        f"| Artifact root | `{report['artifact_root']}` |",
        (
            "| Baseline input digest | "
            f"`{report['baseline_inputs']['digest']}` "
            f"({report['baseline_inputs']['file_count']} files) |"
        ),
        (
            f"| Scenarios | {suite['scorecard_count']} scorecards for "
            f"{suite['scenario_count']} registered scenarios |"
        ),
        f"| Failed scorecards | {suite['failed_count']} |",
        f"| Seeds | `{json.dumps(report['seeds'])}` |",
        f"| Model adapters | `{json.dumps(report['model_adapters'], sort_keys=True)}` |",
        (
            "| Capability coverage | "
            f"{report['capability_coverage']['covered_capability_count']}/"
            f"{report['capability_coverage']['capability_count']} declared capabilities |"
        ),
        f"| Tool descriptor hashes | {len(report['tool_schema_hashes'])} unique tool identities |",
        f"| Event types observed | {len(coverage['event_type_coverage'])} |",
        f"| Lifecycle transitions observed | {len(coverage['lifecycle_transition_coverage'])} |",
        (
            "| Evidence-link statuses | "
            f"`{json.dumps(evidence['verification_statuses'], sort_keys=True)}` |"
        ),
        f"| Contract scores | `{json.dumps(coverage['contract_coverage'], sort_keys=True)}` |",
        f"| Detection scores | `{json.dumps(coverage['detection_coverage'], sort_keys=True)}` |",
        f"| Failure classes | `{json.dumps(failure, sort_keys=True)}` |",
        "",
        (
            "Expected control scenarios intentionally preserve product, agent, "
            + "harness, provider, and budget failure classes when those classes are "
            + "the scenario objective. They do not represent unresolved release "
            + "blockers when the suite passes."
        ),
        "",
        "## Scenario Results",
        "",
        (
            "| Scenario | Passed | Failure class | Failure fingerprint | Seed | "
            + "Event count | Verification statuses | Artifacts |"
        ),
        "| --- | --- | --- | --- | ---: | ---: | --- | --- |",
    ]
    for run in report["runs"]:
        artifacts = run["artifact_paths"]
        lines.append(
            f"| `{run['scenario_id']}` | {run['passed']} | "
            f"`{run['failure_class']}` | "
            f"`{run.get('failure_fingerprint') or 'none'}` | "
            f"{run['seed']} | {run['event_count']} | "
            f"`{json.dumps(run['verification_statuses'])}` | "
            f"`{artifacts['scorecard']}` |"
        )
    lines.extend(
        [
            "",
            "## Reproduction Commands",
            "",
            "```bash",
            *commands,
            "```",
            "",
            "## Limitations",
            "",
        ]
    )
    lines.extend(f"- {item}" for item in report["limitations"])
    lines.append("")
    return "\n".join(lines)


def write_public_baseline_report(
    artifact_root: Path,
    *,
    json_output: Path,
    markdown_output: Path,
    scenario_path: Path = SCENARIO_DIR,
    coverage_path: Path = CAPABILITY_COVERAGE_PATH,
    schema_path: Path = SCENARIO_SCHEMA_PATH,
) -> JsonMap:
    """Write deterministic public Agent Validation baseline reports."""

    report = build_public_baseline_report(
        artifact_root,
        scenario_path=scenario_path,
        coverage_path=coverage_path,
        schema_path=schema_path,
    )
    json_output.parent.mkdir(parents=True, exist_ok=True)
    markdown_output.parent.mkdir(parents=True, exist_ok=True)
    json_output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    markdown_output.write_text(render_public_baseline_report_markdown(report), encoding="utf-8")
    return report


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
                "failure_fingerprint": _scenario_result_failure_fingerprint(result),
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


def _public_report_reproduction_commands(artifact_root: Path) -> list[str]:
    root = str(artifact_root)
    return [
        "PYTHONPATH=evals uv run --group eval python -m actionlineage_evals validate-scenarios",
        "PYTHONPATH=evals uv run --group eval python -m actionlineage_evals lint-scenarios",
        "PYTHONPATH=evals uv run --group eval python -m actionlineage_evals coverage --strict",
        "PYTHONPATH=evals uv run --group eval python -m actionlineage_evals check-boundaries",
        (
            "PYTHONPATH=evals uv run --group eval python -m actionlineage_evals run "
            f"--scenario-path evals/scenarios --artifact-root {root} --mode scripted "
            "--model-adapter scripted --seeds 1"
        ),
        (
            "PYTHONPATH=evals uv run --group eval python -m actionlineage_evals "
            f"audit-artifacts {root}"
        ),
        (
            "PYTHONPATH=evals uv run --group eval python -m actionlineage_evals "
            f"public-report {root} --json-output docs/evidence/agent-validation-baseline.json "
            "--markdown-output docs/evidence/agent-validation-baseline.md"
        ),
    ]


def _load_json(path: Path) -> JsonMap:
    raw: Any = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError(f"expected JSON object: {path}")
    return raw


def _iter_baseline_input_files(project_root: Path) -> tuple[Path, ...]:
    files: set[Path] = set()
    for input_path in BASELINE_INPUT_PATHS:
        path = project_root / input_path
        if path.is_file() and _is_baseline_input_file(path):
            files.add(path)
        elif path.is_dir():
            for candidate in path.rglob("*"):
                if candidate.is_file() and _is_baseline_input_file(candidate):
                    files.add(candidate)
    return tuple(sorted(files, key=lambda item: item.relative_to(project_root).as_posix()))


def _is_baseline_input_file(path: Path) -> bool:
    if any(part in BASELINE_INPUT_EXCLUDED_PARTS for part in path.parts):
        return False
    return path.suffix in BASELINE_INPUT_SUFFIXES


def _load_optional_json(path: Path) -> JsonMap:
    if not path.exists():
        return {}
    return _load_json(path)


def _load_journal_events(path: Path) -> list[JsonMap]:
    if not path.exists():
        return []
    snapshot = LocalJournal(path).verified_snapshot()
    if not snapshot.ok:
        codes = ",".join(issue.code for issue in snapshot.verification.issues)
        raise JournalError(f"agent validation journal verification failed: {path}: {codes}")
    return [event_to_dict(event) for event in snapshot.events]


def _collect_tool_identities(value: object) -> list[JsonMap]:
    identities: list[JsonMap] = []
    if isinstance(value, dict):
        descriptor_hash = value.get("descriptor_hash")
        name = value.get("name")
        if descriptor_hash and name:
            identities.append(
                {
                    "descriptor_hash": str(descriptor_hash),
                    "name": str(name),
                    "server_identity": str(value.get("server_identity", "")),
                }
            )
        for item in value.values():
            identities.extend(_collect_tool_identities(item))
    elif isinstance(value, list):
        for item in value:
            identities.extend(_collect_tool_identities(item))
    return identities


def _run_verification_statuses(events: list[JsonMap]) -> set[str]:
    statuses: set[str] = set()
    for event in events:
        payload = event.get("payload")
        if not isinstance(payload, dict):
            continue
        direct = payload.get("verification_status")
        if direct:
            statuses.add(str(direct))
        evidence_link = payload.get("evidence_link")
        if isinstance(evidence_link, dict) and evidence_link.get("verification_status"):
            statuses.add(str(evidence_link["verification_status"]))
    return statuses


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
        "failure_fingerprint": _scorecard_failure_fingerprint(raw),
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


def _scorecard_failure_fingerprint(scorecard: JsonMap) -> str | None:
    failure_class = scorecard.get("failure_class")
    if scorecard.get("passed") is True and not failure_class:
        return None
    scores = scorecard.get("scores", ())
    score_fingerprints: list[JsonMap] = []
    if isinstance(scores, list):
        for score in scores:
            if not isinstance(score, dict):
                continue
            if score.get("ok") is True and not score.get("failure_class"):
                continue
            score_fingerprints.append(
                {
                    "failure_class": score.get("failure_class"),
                    "name": score.get("name"),
                    "ok": score.get("ok") is True,
                }
            )
    return _sha256_json(
        {
            "failure_class": failure_class,
            "passed": scorecard.get("passed") is True,
            "scenario_id": scorecard.get("scenario_id"),
            "scores": score_fingerprints,
        }
    )


def _scenario_result_failure_fingerprint(result: ScenarioResult) -> str | None:
    if result.passed and result.failure_class is None:
        return None
    score_fingerprints = [
        {
            "failure_class": score.failure_class.value if score.failure_class else None,
            "name": score.name,
            "ok": score.ok,
        }
        for score in result.scores
        if not score.ok or score.failure_class is not None
    ]
    return _sha256_json(
        {
            "failure_class": result.failure_class.value if result.failure_class else None,
            "passed": result.passed,
            "scenario_id": result.scenario_id,
            "scores": score_fingerprints,
        }
    )


def _sha256_json(value: JsonMap) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return f"sha256:{hashlib.sha256(payload).hexdigest()}"


def _hash_file(path: Path) -> str:
    return f"sha256:{hashlib.sha256(path.read_bytes()).hexdigest()}"
