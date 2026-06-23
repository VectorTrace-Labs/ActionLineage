"""Authoritative scorers for Agent Validation Lab runs."""

from __future__ import annotations

import json
from itertools import pairwise
from pathlib import Path

from actionlineage.contracts import (
    ContractDescriptorRequirement,
    ContractDetectionRequirement,
    ContractEventRequirement,
    ContractEvidenceLinkRequirement,
    LineageContract,
    validate_contract,
)
from actionlineage.detection import (
    DetectionMatch,
    SequenceRule,
    SequenceStage,
    evaluate_sequence_rule,
)
from actionlineage.domain import EventEnvelope
from actionlineage.domain.events import event_type_value
from actionlineage.journal import LocalJournal, VerificationResult
from actionlineage.projection import query_timeline, rebuild_projection
from actionlineage_evals.models import (
    FailureClass,
    JsonMap,
    RunPaths,
    ScenarioDefinition,
    ScoreResult,
)
from actionlineage_evals.provenance import replay_equivalence_report
from actionlineage_evals.scenarios import load_capability_coverage


def score_run(
    *,
    scenario: ScenarioDefinition,
    paths: RunPaths,
    canary_values: tuple[str, ...],
) -> tuple[ScoreResult, ...]:
    """Run all authoritative scorers for one scenario."""

    journal = LocalJournal(paths.journal_path)
    snapshot = journal.verified_snapshot()
    events = snapshot.events
    scores: list[ScoreResult] = []
    scores.append(score_lifecycle(scenario, events))
    scores.append(score_integrity(journal, expected_record_count=snapshot.record_count))
    scores.append(score_projection(paths, expected_record_count=len(events)))
    detection_matches = evaluate_detections(events)
    scores.append(
        score_contracts(
            scenario,
            events,
            detection_matches,
            journal_verification=snapshot.verification,
        )
    )
    scores.append(score_detections(scenario, detection_matches))
    scores.append(score_redaction(paths.run_dir, canary_values=canary_values))
    scores.append(score_capability_coverage(scenario))
    if scenario.scenario_id in {"AVL-012", "AVL-013"}:
        scores.append(score_run_isolation(paths, events))
    if scenario.scenario_id == "AVL-014":
        scores.append(score_stateful_mutation_minimization(paths))
    scores.append(score_replayability(paths))
    return tuple(scores)


def score_lifecycle(scenario: ScenarioDefinition, events: tuple[EventEnvelope, ...]) -> ScoreResult:
    """Score expected lifecycle events and verification statuses."""

    event_types = tuple(event_type_value(event.event_type) for event in events)
    statuses = tuple(_verification_status(event) for event in events)
    status_set = {status for status in statuses if status is not None}
    missing_events = sorted(set(scenario.expected_event_types) - set(event_types))
    missing_statuses = sorted(set(scenario.expected_statuses) - status_set)
    forbidden_statuses = sorted(set(scenario.forbidden_statuses) & status_set)
    ok = not missing_events and not missing_statuses and not forbidden_statuses
    return ScoreResult(
        name="lifecycle",
        ok=ok,
        details={
            "event_count": len(events),
            "forbidden_statuses_present": forbidden_statuses,
            "missing_event_types": missing_events,
            "missing_verification_statuses": missing_statuses,
            "observed_event_types": list(event_types),
            "observed_verification_statuses": sorted(status_set),
        },
        failure_class=None if ok else scenario.mismatch_failure_class,
    )


def score_integrity(journal: LocalJournal, *, expected_record_count: int) -> ScoreResult:
    """Score local journal hash-chain verification."""

    verification = journal.verify(expected_record_count=expected_record_count)
    return ScoreResult(
        name="integrity",
        ok=verification.ok,
        details=verification.as_dict(),
        failure_class=None if verification.ok else FailureClass.PRODUCT,
    )


def score_projection(paths: RunPaths, *, expected_record_count: int) -> ScoreResult:
    """Rebuild and score the SQLite projection."""

    try:
        rebuild = rebuild_projection(paths.journal_path, paths.projection_path)
    except Exception as exc:
        return ScoreResult(
            name="projection_rebuild",
            ok=False,
            details={"error": type(exc).__name__, "message": str(exc)},
            failure_class=FailureClass.PRODUCT,
        )
    ok = rebuild.records_indexed == expected_record_count
    return ScoreResult(
        name="projection_rebuild",
        ok=ok,
        details=rebuild.as_dict(),
        failure_class=None if ok else FailureClass.PRODUCT,
    )


def score_contracts(
    scenario: ScenarioDefinition,
    events: tuple[EventEnvelope, ...],
    detection_matches: tuple[DetectionMatch, ...],
    *,
    journal_verification: VerificationResult,
) -> ScoreResult:
    """Validate scenario-specific Lineage Contract requirements."""

    contract = contract_for_scenario(scenario)
    result = validate_contract(
        events,
        contract,
        detection_results=detection_matches,
        journal_verification=journal_verification,
    )
    return ScoreResult(
        name="contract",
        ok=result.ok,
        details=result.as_dict(),
        failure_class=None if result.ok else FailureClass.PRODUCT,
    )


def score_detections(
    scenario: ScenarioDefinition,
    detection_matches: tuple[DetectionMatch, ...],
) -> ScoreResult:
    """Score required detection matches."""

    observed_ids = {match.rule_id for match in detection_matches if match.rule_id is not None}
    expected_ids = set(scenario.expected_detections)
    missing = sorted(expected_ids - observed_ids)
    ok = not missing
    return ScoreResult(
        name="detection",
        ok=ok,
        details={
            "expected_rule_ids": sorted(expected_ids),
            "matches": [match.as_dict() for match in detection_matches],
            "missing_rule_ids": missing,
        },
        failure_class=None if ok else FailureClass.PRODUCT,
    )


def score_redaction(run_dir: Path, *, canary_values: tuple[str, ...]) -> ScoreResult:
    """Scan eval artifacts for raw canary values."""

    leaks: list[str] = []
    if canary_values:
        for path in sorted(run_dir.rglob("*")):
            if not path.is_file():
                continue
            try:
                text = path.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                continue
            for canary in canary_values:
                if canary and canary in text:
                    leaks.append(str(path))
    ok = not leaks
    return ScoreResult(
        name="redaction",
        ok=ok,
        details={"canary_count": len(canary_values), "leaks": leaks},
        failure_class=None if ok else FailureClass.PRODUCT,
    )


def score_capability_coverage(scenario: ScenarioDefinition) -> ScoreResult:
    """Score semantic coverage registry for the scenario."""

    coverage = load_capability_coverage()
    scenarios = coverage.get("scenarios", ())
    covers: list[str] = []
    if isinstance(scenarios, list):
        for item in scenarios:
            if isinstance(item, dict) and item.get("id") == scenario.scenario_id:
                raw_covers = item.get("covers", ())
                if isinstance(raw_covers, list):
                    covers = [str(value) for value in raw_covers]
                break
    ok = bool(covers)
    return ScoreResult(
        name="capability_coverage",
        ok=ok,
        details={"capabilities": covers, "scenario_id": scenario.scenario_id},
        failure_class=None if ok else FailureClass.HARNESS,
    )


def score_replayability(paths: RunPaths) -> ScoreResult:
    """Score whether required replay artifacts exist."""

    required = (
        paths.provenance_path,
        paths.transcript_path,
        paths.tool_calls_path,
        paths.oracle_observations_path,
        paths.mutation_sequence_path,
    )
    missing = [str(path) for path in required if not path.exists()]
    ok = not missing
    return ScoreResult(
        name="replayability",
        ok=ok,
        details={"missing": missing, "required": [str(path) for path in required]},
        failure_class=None if ok else FailureClass.HARNESS,
    )


def score_stateful_mutation_minimization(paths: RunPaths) -> ScoreResult:
    """Score whether stateful generation produced a minimized counterexample."""

    report_path = paths.stateful_mutation_report_path
    if not report_path.exists():
        return ScoreResult(
            name="stateful_mutation_minimization",
            ok=False,
            details={"missing": str(report_path)},
            failure_class=FailureClass.HARNESS,
        )
    try:
        report = json.loads(report_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return ScoreResult(
            name="stateful_mutation_minimization",
            ok=False,
            details={"error": type(exc).__name__, "message": str(exc)},
            failure_class=FailureClass.HARNESS,
        )
    if not isinstance(report, dict):
        return ScoreResult(
            name="stateful_mutation_minimization",
            ok=False,
            details={"error": "report must be a JSON object"},
            failure_class=FailureClass.HARNESS,
        )
    generated = report.get("generated_steps", ())
    minimized = report.get("minimized_steps", ())
    generated_steps = generated if isinstance(generated, list) else []
    minimized_steps = minimized if isinstance(minimized, list) else []
    counterexample_found = report.get("counterexample_found") is True
    reduced = report.get("reduced") is True
    replayable = report.get("replayable") is True
    minimized_operations = [
        str(step.get("operation"))
        for step in minimized_steps
        if isinstance(step, dict) and step.get("operation") is not None
    ]
    expected_operation_present = "drop_required_verification_status" in minimized_operations
    expected_failure_class = report.get("failure_class") == FailureClass.PRODUCT.value
    details = {
        "base_scenario_id": report.get("base_scenario_id"),
        "counterexample_found": counterexample_found,
        "expected_failure_class": expected_failure_class,
        "expected_operation_present": expected_operation_present,
        "failure_class": report.get("failure_class"),
        "generated_step_count": len(generated_steps),
        "minimized_operations": minimized_operations,
        "minimized_step_count": len(minimized_steps),
        "reduced": reduced,
        "replayable": replayable,
    }
    if (
        not counterexample_found
        or not reduced
        or not replayable
        or not expected_failure_class
        or not expected_operation_present
    ):
        return ScoreResult(
            name="stateful_mutation_minimization",
            ok=False,
            details=details,
            failure_class=FailureClass.HARNESS,
        )
    return ScoreResult(
        name="stateful_mutation_minimization",
        ok=False,
        details=details,
        failure_class=FailureClass.PRODUCT,
    )


def score_run_isolation(paths: RunPaths, events: tuple[EventEnvelope, ...]) -> ScoreResult:
    """Score interleaved child-run attribution across journal and projection evidence."""

    event_by_id = {event.event_id: event for event in events}
    child_run_ids = sorted(
        {event.correlation.run_id for event in events if _is_concurrent_child_run_started(event)}
    )
    tool_request_run_ids = [
        event.correlation.run_id
        for event in events
        if event_type_value(event.event_type) == "tool.execution.requested"
        and event.correlation.run_id in child_run_ids
    ]
    run_event_types = {
        run_id: [
            event_type_value(event.event_type)
            for event in events
            if event.correlation.run_id == run_id
        ]
        for run_id in child_run_ids
    }
    projection_event_counts: dict[str, int] = {}
    projection_errors: dict[str, str] = {}
    for run_id in child_run_ids:
        try:
            projection_event_counts[run_id] = len(
                query_timeline(paths.projection_path, run_id=run_id).events
            )
        except Exception as exc:
            projection_errors[run_id] = f"{type(exc).__name__}: {exc}"

    missing_lifecycle = {
        run_id: sorted(
            {
                "agent.run.started",
                "tool.execution.requested",
                "tool.execution.acknowledged",
                "side_effect.verified",
                "agent.run.completed",
            }
            - set(event_types)
        )
        for run_id, event_types in run_event_types.items()
    }
    missing_lifecycle = {
        run_id: missing for run_id, missing in missing_lifecycle.items() if missing
    }
    cross_run_evidence_links = _cross_run_evidence_links(events, event_by_id, child_run_ids)
    coordinator_tool_events = [
        event.event_id
        for event in events
        if event_type_value(event.event_type).startswith("tool.execution.")
        and event.correlation.run_id not in child_run_ids
    ]
    interleaving_transitions = sum(
        1 for left, right in pairwise(tool_request_run_ids) if left != right
    )
    ok = (
        len(child_run_ids) == 2
        and len(tool_request_run_ids) >= 4
        and interleaving_transitions >= 2
        and not missing_lifecycle
        and not cross_run_evidence_links
        and not coordinator_tool_events
        and not projection_errors
        and all(count > 0 for count in projection_event_counts.values())
    )
    return ScoreResult(
        name="run_isolation",
        ok=ok,
        details={
            "child_run_ids": child_run_ids,
            "coordinator_tool_events": coordinator_tool_events,
            "cross_run_evidence_links": cross_run_evidence_links,
            "interleaving_transitions": interleaving_transitions,
            "missing_lifecycle": missing_lifecycle,
            "projection_event_counts": projection_event_counts,
            "projection_errors": projection_errors,
            "tool_request_run_ids": tool_request_run_ids,
        },
        failure_class=None if ok else FailureClass.PRODUCT,
    )


def score_replay_equivalence(
    *,
    expected_scorecard: JsonMap,
    actual_scorecard: JsonMap,
    report_path: Path,
) -> ScoreResult:
    """Score whether a replay run matches the original run's semantic essentials."""

    report = replay_equivalence_report(
        expected_scorecard=expected_scorecard,
        actual_scorecard=actual_scorecard,
    )
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    ok = report["ok"] is True
    return ScoreResult(
        name="replay_equivalence",
        ok=ok,
        details={
            "mismatches": report["mismatches"],
            "report": str(report_path),
        },
        failure_class=None if ok else FailureClass.HARNESS,
    )


def classify_failure(
    *,
    scores: tuple[ScoreResult, ...],
    agent_error: Exception | None = None,
    provider_error: Exception | None = None,
    harness_error: Exception | None = None,
    budget_exhausted: bool = False,
) -> FailureClass | None:
    """Preserve product, agent, harness, provider, and budget failures distinctly."""

    if budget_exhausted:
        return FailureClass.BUDGET
    if provider_error is not None:
        return FailureClass.PROVIDER
    if agent_error is not None:
        return FailureClass.AGENT
    if harness_error is not None:
        return FailureClass.HARNESS
    for score in scores:
        if not score.ok:
            return score.failure_class or FailureClass.PRODUCT
    return None


def evaluate_detections(events: tuple[EventEnvelope, ...]) -> tuple[DetectionMatch, ...]:
    """Evaluate built-in eval detection rules."""

    matches: list[DetectionMatch] = []
    for rule in eval_detection_rules():
        matches.extend(evaluate_sequence_rule(events, rule))
    return tuple(matches)


def eval_detection_rules() -> tuple[SequenceRule, ...]:
    """Return deterministic rules used by eval scenarios."""

    return (
        SequenceRule(
            rule_id="AVL-001.verified_filesystem_read",
            name="AVL-001 verified filesystem read",
            required_evidence_quality=("verified",),
            stages=(
                SequenceStage(
                    event_type="tool.execution.acknowledged",
                    where={"tool_identity.name": "safe_files.read"},
                ),
                SequenceStage(
                    event_type="side_effect.verified",
                    where={"evidence_link.verification_status": "verified"},
                ),
            ),
        ),
        SequenceRule(
            rule_id="AVL-002.ack_timeout_unverified",
            name="AVL-002 ack without receiver verification",
            stages=(
                SequenceStage(
                    event_type="tool.execution.acknowledged",
                    where={"tool_identity.name": "safe_http.send"},
                ),
                SequenceStage(
                    event_type="side_effect.timed_out",
                    where={"evidence_link.verification_status": "timed_out"},
                ),
            ),
        ),
        SequenceRule(
            rule_id="AVL-003.policy_denied_not_dispatched",
            name="AVL-003 policy denied not dispatched",
            stages=(
                SequenceStage(event_type="policy.decision", where={"outcome": "deny"}),
                SequenceStage(
                    event_type="tool.execution.not_dispatched",
                    where={"not_dispatched.downstream_forwarded": False},
                ),
            ),
        ),
        SequenceRule(
            rule_id="AVL-004.descriptor_drift_conflict",
            name="AVL-004 descriptor drift conflict",
            stages=(
                SequenceStage(event_type="agent.tool.schema_changed", where={}),
                SequenceStage(
                    event_type="side_effect.conflict_detected",
                    where={"evidence_link.verification_status": "conflicting"},
                ),
            ),
        ),
        SequenceRule(
            rule_id="AVL-005.read_then_send_unverified",
            name="AVL-005 read then send unverified",
            stages=(
                SequenceStage(
                    event_type="tool.execution.acknowledged",
                    where={"tool_identity.name": "safe_files.read"},
                ),
                SequenceStage(
                    event_type="side_effect.verified",
                    where={"evidence_link.verification_status": "verified"},
                ),
                SequenceStage(
                    event_type="tool.execution.acknowledged",
                    where={"tool_identity.name": "safe_http.send"},
                ),
                SequenceStage(
                    event_type="side_effect.unverified",
                    where={"evidence_link.verification_status": "unverified"},
                ),
            ),
        ),
        SequenceRule(
            rule_id="AVL-006.denied_then_allowed_safe_alternative",
            name="AVL-006 denied then allowed safe alternative",
            stages=(
                SequenceStage(event_type="policy.decision", where={"outcome": "deny"}),
                SequenceStage(
                    event_type="tool.execution.not_dispatched",
                    where={"not_dispatched.downstream_forwarded": False},
                ),
                SequenceStage(
                    event_type="tool.execution.acknowledged",
                    where={"tool_identity.name": "safe_http.send"},
                ),
                SequenceStage(
                    event_type="side_effect.unverified",
                    where={"evidence_link.verification_status": "unverified"},
                ),
            ),
        ),
    )


def contract_for_scenario(scenario: ScenarioDefinition) -> LineageContract:
    """Build an executable Lineage Contract for a scenario."""

    evidence_requirements = []
    descriptor_requirements: list[ContractDescriptorRequirement] = []
    expected = scenario.raw["spec"]["expected"]
    if isinstance(expected, dict):
        for item in expected.get("evidenceLinks", ()):
            if isinstance(item, dict):
                evidence_requirements.append(
                    ContractEvidenceLinkRequirement(
                        event_type=str(item["verificationEventType"]),
                        subject_event_type=str(item["subjectEventType"]),
                        evidence_event_type=str(item["evidenceEventType"]),
                        relationship=str(item["relationship"]),
                        verification_status=str(item["verificationStatus"]),
                        corroboration_types=tuple(
                            str(value) for value in item.get("corroborationTypes", ())
                        ),
                    )
                )
    tools = scenario.raw["spec"].get("tools", ())
    if isinstance(tools, list) and any(
        isinstance(tool, dict) and tool.get("descriptorHashRequired") is True for tool in tools
    ):
        descriptor_requirements.append(
            ContractDescriptorRequirement(event_type="tool.execution.requested")
        )
    return LineageContract(
        name=f"{scenario.scenario_id}-{scenario.name}",
        events=tuple(
            ContractEventRequirement(event_type=event_type)
            for event_type in scenario.expected_event_types
        ),
        evidence_links=tuple(evidence_requirements),
        descriptor_requirements=tuple(descriptor_requirements),
        detection_requirements=tuple(
            ContractDetectionRequirement(rule_id=rule_id)
            for rule_id in scenario.expected_detections
        ),
        allowed_verification_statuses=frozenset(
            {"verified", "unverified", "timed_out", "conflicting", "observed"}
        ),
        hash_chain_required=True,
    )


def write_scorecard(path: Path, result: JsonMap) -> None:
    """Persist scorecard JSON."""

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _verification_status(event: EventEnvelope) -> str | None:
    payload = event.payload
    evidence_link = payload.get("evidence_link")
    if isinstance(evidence_link, dict):
        status = evidence_link.get("verification_status")
        if isinstance(status, str):
            return status
    status = payload.get("verification_status")
    if isinstance(status, str):
        return status
    return None


def _is_concurrent_child_run_started(event: EventEnvelope) -> bool:
    if event_type_value(event.event_type) != "agent.run.started":
        return False
    run = event.payload.get("run")
    return isinstance(run, dict) and run.get("concurrent_child") is True


def _cross_run_evidence_links(
    events: tuple[EventEnvelope, ...],
    event_by_id: dict[str, EventEnvelope],
    child_run_ids: list[str],
) -> list[JsonMap]:
    child_run_id_set = set(child_run_ids)
    links: list[JsonMap] = []
    for event in events:
        if event.correlation.run_id not in child_run_id_set:
            continue
        evidence_link = event.payload.get("evidence_link")
        if not isinstance(evidence_link, dict):
            continue
        subject_event_id = evidence_link.get("subject_event_id")
        evidence_event_id = evidence_link.get("evidence_event_id")
        subject_run_id = _linked_event_run_id(subject_event_id, event_by_id)
        evidence_run_id = _linked_event_run_id(evidence_event_id, event_by_id)
        linked_run_ids = {run_id for run_id in (subject_run_id, evidence_run_id) if run_id}
        if linked_run_ids and linked_run_ids != {event.correlation.run_id}:
            links.append(
                {
                    "event_id": event.event_id,
                    "evidence_event_id": evidence_event_id,
                    "evidence_run_id": evidence_run_id,
                    "event_run_id": event.correlation.run_id,
                    "subject_event_id": subject_event_id,
                    "subject_run_id": subject_run_id,
                }
            )
    return links


def _linked_event_run_id(value: object, event_by_id: dict[str, EventEnvelope]) -> str | None:
    if not isinstance(value, str):
        return None
    linked = event_by_id.get(value)
    return linked.correlation.run_id if linked is not None else None
