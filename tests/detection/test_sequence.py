from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

import pytest
from typer.testing import CliRunner

from actionlineage.cli import app
from actionlineage.demo.scenario import build_demo_events
from actionlineage.detection import (
    DetectionRuleLoadError,
    SequenceRule,
    SequenceStage,
    built_in_sequence_rules,
    evaluate_sequence_rule,
    explain_sequence_rule,
    load_sequence_rules,
    sequence_rule_from_dict,
    sequence_rule_to_dict,
)
from actionlineage.domain import (
    Causality,
    Classification,
    Correlation,
    EventEnvelope,
    EventType,
    Principal,
    PrincipalType,
    Source,
    event_to_dict,
)
from actionlineage.journal import LocalJournal

BASE_TIME = datetime(2026, 6, 21, 18, 42, 12, tzinfo=UTC)
runner = CliRunner()


def verified_file_read_rule() -> SequenceRule:
    return SequenceRule(
        name="verified-file-read",
        stages=(
            SequenceStage(
                event_type="tool.execution.acknowledged",
                where={"tool_identity.name": "safe_files.read"},
            ),
            SequenceStage(
                event_type="side_effect.verified",
                where={
                    "evidence_link.verification_status": "verified",
                    "evidence_link.corroboration_type": {
                        "in": [
                            "independent_observer",
                            "fixture_oracle",
                            "post_action_readback",
                        ]
                    },
                },
            ),
        ),
    )


def test_sequence_rule_matches_verified_side_effects_only() -> None:
    matches = evaluate_sequence_rule(build_demo_events(), verified_file_read_rule())

    assert len(matches) == 1
    assert matches[0].event_ids == ("evt_demo_05", "evt_demo_07")
    assert matches[0].as_dict()["evidence"] == [
        {"event_id": "evt_demo_05", "stage_index": 0},
        {"event_id": "evt_demo_07", "stage_index": 1},
    ]


def test_sequence_rule_does_not_treat_acknowledgement_as_verification() -> None:
    unverified_send_rule = SequenceRule(
        name="unverified-send-should-not-match",
        stages=(
            SequenceStage(
                event_type="tool.execution.acknowledged",
                where={"tool_identity.name": "safe_http.send"},
            ),
            SequenceStage(
                event_type="side_effect.verified",
                where={"evidence_link.verification_status": "verified"},
            ),
        ),
    )

    assert evaluate_sequence_rule(build_demo_events(), unverified_send_rule) == ()


def test_sequence_rule_explanation_identifies_stage_candidates_without_payloads() -> None:
    rule = SequenceRule(
        rule_id="AL-TEST-EXPLAIN",
        name="unmatched-verified-send",
        stages=(
            SequenceStage(
                name="acknowledged-send",
                event_type="tool.execution.acknowledged",
                where={"tool_identity.name": "safe_http.send"},
            ),
            SequenceStage(
                name="verified-side-effect",
                event_type="side_effect.verified",
                where={"evidence_link.verification_status": "verified"},
            ),
        ),
    )

    explanation = explain_sequence_rule(build_demo_events(), rule)
    data = explanation.as_dict()
    first_group = data["groups"][0]

    assert data["matched"] is False
    assert data["rule_id"] == "AL-TEST-EXPLAIN"
    assert first_group["stages"][0]["candidate_event_ids"] == ["evt_demo_11"]
    assert first_group["stages"][1]["candidate_count"] == 1
    assert "safe_http.send" not in json.dumps(data, sort_keys=True)


def test_rule_metadata_is_exported_with_detection_match() -> None:
    rule = SequenceRule(
        rule_id="AL-TEST-001",
        name="metadata-export",
        version="1",
        severity="high",
        tags=("unit",),
        rationale="exercise exported detection metadata",
        references=("https://example.invalid/rule",),
        required_evidence_quality=("verified",),
        stages=(SequenceStage(event_type="side_effect.verified", where={}),),
    )

    matches = evaluate_sequence_rule(build_demo_events(), rule)

    assert len(matches) == 1
    assert matches[0].as_dict()["rule_id"] == "AL-TEST-001"
    assert matches[0].as_dict()["severity"] == "high"


def test_sequence_rule_uses_original_event_after_failed_payload_backing_store_attack() -> None:
    event = _event(
        event_id="evt_detection_immutability",
        event_type=EventType.TOOL_EXECUTION_ACKNOWLEDGED,
        payload={"tool_identity": {"name": "safe_files.read"}},
    )
    rule = SequenceRule(
        name="detect-original-tool",
        stages=(
            SequenceStage(
                event_type="tool.execution.acknowledged",
                where={"tool_identity.name": "safe_files.read"},
            ),
        ),
    )

    with pytest.raises(TypeError):
        event.payload["tool_identity"]._items = (("name", "tampered.tool"),)

    matches = evaluate_sequence_rule((event,), rule)

    assert len(matches) == 1
    assert event_to_dict(event)["payload"] == {"tool_identity": {"name": "safe_files.read"}}


def test_bounded_expression_operators_match_known_values() -> None:
    event = _event(
        event_id="evt_expr",
        event_type=EventType.ACTION_NORMALIZED,
        payload={
            "action": {
                "action_type": "data.read",
                "resources": [
                    {
                        "resource_type": "file",
                        "identifier": "demo://workspace/export.csv",
                        "attributes": {"sensitivity": "restricted"},
                    }
                ],
                "attributes": {
                    "path": "demo://workspace/export.csv",
                    "filename": "export.csv",
                    "byte_count": 2048,
                    "completed_at": "2026-06-21T18:42:14Z",
                    "mode": "read",
                },
            }
        },
    )
    rule = SequenceRule(
        name="bounded-operators",
        stages=(
            SequenceStage(
                event_type="action.normalized",
                where={
                    "action.resources.0.attributes.sensitivity": {"in": ["restricted", "secret"]},
                    "action.attributes.path": {"prefix": "demo://workspace/"},
                    "action.attributes.filename": {"suffix": ".csv"},
                    "action.attributes.byte_count": {"gte": 1024},
                    "action.attributes.completed_at": {"gt": "2026-06-21T18:42:13Z"},
                    "action.attributes.mode": {"not": "write"},
                    "action.attributes.optional": {"exists": False},
                },
            ),
        ),
    )

    assert evaluate_sequence_rule((event,), rule)


def test_regex_and_missing_negation_unknown_semantics() -> None:
    event = _event(
        event_id="evt_regex",
        event_type=EventType.ACTION_NORMALIZED,
        payload={"action": {"attributes": {"path": "demo://workspace/export.csv"}}},
    )
    regex_rule = SequenceRule(
        name="safe-regex",
        stages=(
            SequenceStage(
                event_type="action.normalized",
                where={"action.attributes.path": {"regex": r"workspace/.+\.csv$"}},
            ),
        ),
    )
    missing_not_rule = SequenceRule(
        name="missing-not-does-not-match",
        stages=(
            SequenceStage(
                event_type="action.normalized",
                where={"action.attributes.missing": {"not": "blocked"}},
            ),
        ),
    )

    assert evaluate_sequence_rule((event,), regex_rule)
    assert evaluate_sequence_rule((event,), missing_not_rule) == ()


def test_unordered_stages_and_time_windows_are_explicit() -> None:
    verified = _event(
        event_id="evt_verified",
        event_type=EventType.SIDE_EFFECT_VERIFIED,
        payload={"evidence_link": {"verification_status": "verified"}},
        sequence=2,
        seconds=10,
    )
    ack = _event(
        event_id="evt_ack",
        event_type=EventType.TOOL_EXECUTION_ACKNOWLEDGED,
        payload={"acknowledgement": {"status": "succeeded"}},
        sequence=3,
        seconds=20,
    )
    rule = SequenceRule(
        name="unordered-window",
        ordered=False,
        within_seconds=15,
        stages=(
            SequenceStage(event_type="tool.execution.acknowledged", where={}),
            SequenceStage(event_type="side_effect.verified", where={}),
        ),
    )
    too_tight = SequenceRule(
        name="unordered-tight-window",
        ordered=False,
        within_seconds=5,
        stages=rule.stages,
    )

    assert evaluate_sequence_rule((verified, ack), rule)
    assert evaluate_sequence_rule((verified, ack), too_tight) == ()


def test_suppression_limits_repeated_alerts_per_group() -> None:
    events = (
        _event("evt_ack_1", EventType.TOOL_EXECUTION_ACKNOWLEDGED, {}, sequence=1, seconds=1),
        _event("evt_verified_1", EventType.SIDE_EFFECT_VERIFIED, {}, sequence=2, seconds=2),
        _event("evt_ack_2", EventType.TOOL_EXECUTION_ACKNOWLEDGED, {}, sequence=3, seconds=10),
        _event("evt_verified_2", EventType.SIDE_EFFECT_VERIFIED, {}, sequence=4, seconds=11),
    )
    stages = (
        SequenceStage(event_type="tool.execution.acknowledged", where={}),
        SequenceStage(event_type="side_effect.verified", where={}),
    )

    assert (
        len(evaluate_sequence_rule(events, SequenceRule(name="unsuppressed", stages=stages))) == 2
    )
    assert (
        len(
            evaluate_sequence_rule(
                events,
                SequenceRule(name="suppressed", stages=stages, suppression_seconds=60),
            )
        )
        == 1
    )


def test_built_in_rule_pack_is_stable_and_demo_aligned() -> None:
    rules = {rule.rule_id: rule for rule in built_in_sequence_rules()}

    assert set(rules) == {
        "AL-DET-001",
        "AL-DET-002",
        "AL-DET-003",
        "AL-DET-004",
        "AL-DET-005",
    }
    assert evaluate_sequence_rule(build_demo_events(), rules["AL-DET-003"])
    assert evaluate_sequence_rule(build_demo_events(), rules["AL-DET-004"])
    assert evaluate_sequence_rule(build_demo_events(), rules["AL-DET-005"])


def test_sequence_rule_dict_round_trips_without_semantic_changes() -> None:
    original = verified_file_read_rule()

    loaded = sequence_rule_from_dict(sequence_rule_to_dict(original))

    assert loaded == original
    assert evaluate_sequence_rule(build_demo_events(), loaded)


def test_load_sequence_rules_from_json_pack(tmp_path) -> None:
    path = tmp_path / "rules.json"
    path.write_text(
        json.dumps({"rules": [sequence_rule_to_dict(verified_file_read_rule())]}),
        encoding="utf-8",
    )

    rules = load_sequence_rules(path)

    assert len(rules) == 1
    assert rules[0].name == "verified-file-read"
    assert evaluate_sequence_rule(build_demo_events(), rules[0])


def test_load_sequence_rules_from_yaml_package_shape(tmp_path) -> None:
    pytest.importorskip("yaml")
    path = tmp_path / "rules.yaml"
    path.write_text(
        """
apiVersion: actionlineage.dev/v1alpha1
kind: SequenceDetection
metadata:
  id: AL-TEST-YAML
  name: verified-file-read-yaml
spec:
  severity: high
  tags:
    - package
  requiredEvidenceQuality:
    - verified
  groupBy:
    - correlation.run_id
  within: 2m
  ordered: true
  stages:
    - name: acknowledged-read
      eventType: tool.execution.acknowledged
      where:
        tool_identity.name: safe_files.read
    - name: verified-side-effect
      eventType: side_effect.verified
      where:
        evidence_link.verification_status: verified
""".lstrip(),
        encoding="utf-8",
    )

    rules = load_sequence_rules(path)

    assert rules[0].rule_id == "AL-TEST-YAML"
    assert rules[0].name == "verified-file-read-yaml"
    assert rules[0].within_seconds == 120.0
    assert rules[0].required_evidence_quality == ("verified",)
    assert evaluate_sequence_rule(build_demo_events(), rules[0])


def test_cli_explain_sequence_outputs_stage_candidates(tmp_path) -> None:
    journal_path = tmp_path / "demo.jsonl"
    rule_path = tmp_path / "rules.json"
    journal = LocalJournal(journal_path)
    for event in build_demo_events():
        journal.append(event)
    rule_path.write_text(
        json.dumps({"rules": [sequence_rule_to_dict(verified_file_read_rule())]}),
        encoding="utf-8",
    )

    result = runner.invoke(
        app,
        ["detection", "explain-sequence", str(rule_path), str(journal_path)],
    )
    data = json.loads(result.stdout)

    assert result.exit_code == 0
    assert data["ok"] is True
    assert data["rules"][0]["matched"] is True
    assert data["rules"][0]["matches"][0]["event_ids"] == ["evt_demo_05", "evt_demo_07"]


def test_cli_explain_sequence_rejects_tampered_journal_before_evaluation(tmp_path) -> None:
    journal_path = tmp_path / "demo.jsonl"
    rule_path = tmp_path / "rules.json"
    journal = LocalJournal(journal_path)
    for event in build_demo_events():
        journal.append(event)
    lines = journal_path.read_bytes().splitlines()
    lines[2] = lines[2].replace(b'"requested_state":"requested"', b'"requested_state":"tampered"')
    journal_path.write_bytes(b"\n".join(lines) + b"\n")
    rule_path.write_text(
        json.dumps({"rules": [sequence_rule_to_dict(verified_file_read_rule())]}),
        encoding="utf-8",
    )

    result = runner.invoke(
        app,
        ["detection", "explain-sequence", str(rule_path), str(journal_path)],
    )
    data = json.loads(result.stdout)

    assert result.exit_code == 1
    assert data["ok"] is False
    assert data["error"] == "journal_integrity_error"
    assert data["verification"]["issues"][0]["code"] == "event_hash_mismatch"
    assert "rules" not in data


def test_rule_loader_rejects_unsupported_suffix_without_payload_echo(tmp_path) -> None:
    path = tmp_path / "rules.txt"
    path.write_text("token-value", encoding="utf-8")

    with pytest.raises(DetectionRuleLoadError) as exc_info:
        load_sequence_rules(path)

    assert "token-value" not in str(exc_info.value)
    assert ".json" in str(exc_info.value)


def test_rule_loader_rejects_malformed_predicate_without_value_leak(tmp_path) -> None:
    path = tmp_path / "rules.json"
    path.write_text(
        json.dumps(
            {
                "rules": [
                    {
                        "name": "bad-rule",
                        "stages": [
                            {
                                "event_type": "tool.execution.acknowledged",
                                "where": {"payload.secret": {"contains": "bearer-token-canary"}},
                            }
                        ],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(DetectionRuleLoadError) as exc_info:
        load_sequence_rules(path)

    assert "bearer-token-canary" not in str(exc_info.value)
    assert "unsupported operator" in str(exc_info.value)


def _event(
    event_id: str,
    event_type: EventType | str,
    payload: dict[str, object],
    *,
    sequence: int = 1,
    seconds: int = 0,
) -> EventEnvelope:
    occurred_at = BASE_TIME + timedelta(seconds=seconds)
    return EventEnvelope(
        event_id=event_id,
        event_type=event_type,
        occurred_at=occurred_at,
        observed_at=occurred_at,
        source=Source(component="detection-test", instance_id="test", version="1"),
        correlation=Correlation(trace_id="trace_detection", run_id="run_detection"),
        causality=Causality(
            root_event_id="evt_root",
            parent_event_id="evt_root",
            sequence=sequence,
        ),
        principal=Principal(principal_id="agent_test", principal_type=PrincipalType.AGENT),
        classification=Classification(),
        payload=payload,
    )
