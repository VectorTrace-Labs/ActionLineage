"""Authoritative scorers for Agent Validation Lab runs."""

from __future__ import annotations

import json
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
from actionlineage.journal import LocalJournal
from actionlineage.projection import rebuild_projection
from actionlineage_evals.models import (
    FailureClass,
    JsonMap,
    RunPaths,
    ScenarioDefinition,
    ScoreResult,
)
from actionlineage_evals.scenarios import load_capability_coverage


def score_run(
    *,
    scenario: ScenarioDefinition,
    paths: RunPaths,
    canary_values: tuple[str, ...],
) -> tuple[ScoreResult, ...]:
    """Run all authoritative scorers for one scenario."""

    journal = LocalJournal(paths.journal_path)
    events = tuple(journal.iter_events())
    scores: list[ScoreResult] = []
    scores.append(score_lifecycle(scenario, events))
    scores.append(score_integrity(journal, expected_record_count=len(events)))
    scores.append(score_projection(paths, expected_record_count=len(events)))
    detection_matches = evaluate_detections(events)
    scores.append(score_contracts(scenario, events, detection_matches))
    scores.append(score_detections(scenario, detection_matches))
    scores.append(score_redaction(paths.run_dir, canary_values=canary_values))
    scores.append(score_capability_coverage(scenario))
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
) -> ScoreResult:
    """Validate scenario-specific Lineage Contract requirements."""

    contract = contract_for_scenario(scenario)
    result = validate_contract(events, contract, detection_results=detection_matches)
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
