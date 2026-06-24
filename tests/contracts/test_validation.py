from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from actionlineage.cli import app
from actionlineage.contracts import (
    ContractDescriptorRequirement,
    ContractDetectionRequirement,
    ContractEventRequirement,
    ContractEvidenceLinkRequirement,
    ContractLatencyRequirement,
    ContractRelationshipRequirement,
    LineageContract,
    contract_from_dict,
    contract_to_dict,
    load_contract,
    validate_contract,
    write_contract_template,
)
from actionlineage.demo import run_demo
from actionlineage.detection import built_in_sequence_rules, evaluate_sequence_rule
from actionlineage.journal import LocalJournal, VerifiedJournalSnapshot

runner = CliRunner()


def demo_journal_snapshot(tmp_path: Path) -> VerifiedJournalSnapshot:
    result = run_demo(tmp_path / "demo")
    return LocalJournal(result.journal_path).verified_snapshot()


def demo_journal_events(tmp_path: Path):
    return demo_journal_snapshot(tmp_path).events


def evidence_contract(*, hash_chain_required: bool = True) -> LineageContract:
    return LineageContract(
        name="demo-evidence-contract",
        events=(
            ContractEventRequirement(
                event_type="tool.execution.requested",
                required_fields=("payload.tool_identity.name",),
            ),
            ContractEventRequirement(
                event_type="tool.execution.acknowledged",
                required_fields=("payload.acknowledgement.status",),
            ),
            ContractEventRequirement(
                event_type="side_effect.observed",
                required_fields=("payload.observer_identity",),
            ),
            ContractEventRequirement(
                event_type="side_effect.verified",
                required_fields=(
                    "payload.evidence_link.subject_event_id",
                    "payload.evidence_link.evidence_event_id",
                    "payload.evidence_link.verification_status",
                ),
            ),
            ContractEventRequirement(
                event_type="tool.execution.not_dispatched",
                required_fields=("payload.not_dispatched.policy_decision_event_id",),
            ),
        ),
        relationships=(
            ContractRelationshipRequirement(
                child_event_type="tool.execution.acknowledged",
                parent_event_type="tool.execution.dispatched",
            ),
            ContractRelationshipRequirement(
                child_event_type="side_effect.verified",
                parent_event_type="side_effect.observed",
            ),
            ContractRelationshipRequirement(
                child_event_type="tool.execution.not_dispatched",
                parent_event_type="policy.decision",
                reference_field="payload.not_dispatched.policy_decision_event_id",
            ),
        ),
        evidence_links=(
            ContractEvidenceLinkRequirement(
                event_type="side_effect.verified",
                subject_event_type="tool.execution.acknowledged",
                evidence_event_type="side_effect.observed",
                relationship="corroborates",
                verification_status="verified",
                corroboration_types=(
                    "independent_observer",
                    "fixture_oracle",
                    "post_action_readback",
                ),
            ),
        ),
        latency_requirements=(
            ContractLatencyRequirement(
                start_event_type="tool.execution.dispatched",
                end_event_type="tool.execution.acknowledged",
                max_seconds=1.0,
            ),
        ),
        descriptor_requirements=(
            ContractDescriptorRequirement(event_type="tool.execution.requested"),
        ),
        allowed_verification_statuses=frozenset(
            {"conflicting", "observed", "verified", "unverified"}
        ),
        required_verification_status="verified",
        hash_chain_required=hash_chain_required,
    )


def test_contract_accepts_demo_evidence_and_control_dependencies(tmp_path: Path) -> None:
    snapshot = demo_journal_snapshot(tmp_path)
    result = validate_contract(
        snapshot.events,
        evidence_contract(),
        journal_verification=snapshot.verification,
    )

    assert result.ok
    assert result.violations == ()


def test_contract_reports_missing_required_evidence_link(tmp_path: Path) -> None:
    events = list(demo_journal_events(tmp_path))
    verified_index = next(
        index
        for index, event in enumerate(events)
        if str(event.event_type) == "side_effect.verified"
    )
    events[verified_index] = events[verified_index].model_copy(update={"payload": {}})

    result = validate_contract(tuple(events), evidence_contract(hash_chain_required=False))

    assert not result.ok
    assert any(violation.code == "required_field_missing" for violation in result.violations)


def test_contract_reports_broken_control_dependency_reference(tmp_path: Path) -> None:
    events = list(demo_journal_events(tmp_path))
    not_dispatched_index = next(
        index
        for index, event in enumerate(events)
        if str(event.event_type) == "tool.execution.not_dispatched"
    )
    broken_payload = {
        "not_dispatched": {
            "policy_decision_event_id": "evt_missing",
            "downstream_forwarded": False,
        }
    }
    events[not_dispatched_index] = events[not_dispatched_index].model_copy(
        update={"payload": broken_payload}
    )

    result = validate_contract(tuple(events), evidence_contract(hash_chain_required=False))

    assert not result.ok
    assert any(violation.code == "relationship_missing" for violation in result.violations)


def test_contract_reports_broken_evidence_link_reference(tmp_path: Path) -> None:
    events = list(demo_journal_events(tmp_path))
    verified_index = next(
        index
        for index, event in enumerate(events)
        if str(event.event_type) == "side_effect.verified"
    )
    broken_payload = dict(events[verified_index].payload)
    evidence_link = dict(broken_payload["evidence_link"])
    evidence_link["evidence_event_id"] = "evt_missing"
    broken_payload["evidence_link"] = evidence_link
    events[verified_index] = events[verified_index].model_copy(update={"payload": broken_payload})

    result = validate_contract(tuple(events), evidence_contract(hash_chain_required=False))

    assert not result.ok
    assert any(
        violation.code == "evidence_link_reference_missing" for violation in result.violations
    )


def test_contract_reports_latency_breach(tmp_path: Path) -> None:
    events = list(demo_journal_events(tmp_path))
    acknowledged_index = next(
        index
        for index, event in enumerate(events)
        if str(event.event_type) == "tool.execution.acknowledged"
    )
    events[acknowledged_index] = events[acknowledged_index].model_copy(
        update={"occurred_at": events[acknowledged_index].occurred_at.replace(minute=55)}
    )

    result = validate_contract(tuple(events), evidence_contract(hash_chain_required=False))

    assert not result.ok
    assert any(violation.code == "latency_breach" for violation in result.violations)


def test_contract_reports_missing_descriptor_identity(tmp_path: Path) -> None:
    events = list(demo_journal_events(tmp_path))
    requested_index = next(
        index
        for index, event in enumerate(events)
        if str(event.event_type) == "tool.execution.requested"
    )
    payload = dict(events[requested_index].payload)
    tool_identity = dict(payload["tool_identity"])
    tool_identity.pop("descriptor_hash")
    payload["tool_identity"] = tool_identity
    events[requested_index] = events[requested_index].model_copy(update={"payload": payload})

    result = validate_contract(tuple(events), evidence_contract(hash_chain_required=False))

    assert not result.ok
    assert any(violation.code == "descriptor_identity_missing" for violation in result.violations)


def test_contract_validates_required_detection_coverage(tmp_path: Path) -> None:
    events = demo_journal_events(tmp_path)
    rule = next(rule for rule in built_in_sequence_rules() if rule.rule_id == "AL-DET-003")
    contract = LineageContract(
        name="detection-coverage",
        events=(),
        detection_requirements=(
            ContractDetectionRequirement(
                rule_id="AL-DET-003",
                required_event_types=("side_effect.unverified",),
                required_verification_statuses=("unverified",),
            ),
        ),
        hash_chain_required=False,
    )

    assert validate_contract(
        events, contract, detection_results=evaluate_sequence_rule(events, rule)
    ).ok
    missing_detection = validate_contract(events, contract)
    assert not missing_detection.ok
    assert any(
        violation.code == "required_detection_missing" for violation in missing_detection.violations
    )


def test_contract_reports_detection_control_dependency_gap(tmp_path: Path) -> None:
    events = demo_journal_events(tmp_path)
    rule = next(rule for rule in built_in_sequence_rules() if rule.rule_id == "AL-DET-003")
    contract = LineageContract(
        name="detection-control-gap",
        events=(),
        detection_requirements=(
            ContractDetectionRequirement(
                rule_id="AL-DET-003",
                required_event_types=("side_effect.timed_out",),
            ),
        ),
        hash_chain_required=False,
    )

    result = validate_contract(
        events, contract, detection_results=evaluate_sequence_rule(events, rule)
    )

    assert not result.ok
    assert any(
        violation.code == "detection_control_dependency_missing" for violation in result.violations
    )


def test_contract_json_roundtrip_and_template(tmp_path: Path) -> None:
    contract_path = tmp_path / "contract.json"
    template = write_contract_template(contract_path, name="template-contract")
    loaded = load_contract(contract_path)
    roundtrip = contract_from_dict(contract_to_dict(evidence_contract()))

    assert loaded.name == template.name
    assert roundtrip.name == "demo-evidence-contract"
    assert json.loads(contract_path.read_text(encoding="utf-8"))["kind"] == "LineageContract"


def test_contract_cli_init_explain_and_validate(tmp_path: Path) -> None:
    demo = run_demo(tmp_path / "demo")
    contract_path = tmp_path / "contract.json"

    init_result = runner.invoke(
        app,
        ["contract", "init", str(contract_path), "--name", "cli-contract"],
    )
    explain_result = runner.invoke(app, ["contract", "explain", str(contract_path)])
    validate_result = runner.invoke(
        app,
        [
            "contract",
            "validate",
            str(contract_path),
            str(demo.journal_path),
            "--format",
            "annotations",
        ],
    )

    assert init_result.exit_code == 0
    assert explain_result.exit_code == 0
    assert validate_result.exit_code == 0
    assert "contract cli-contract: ok" in validate_result.stdout


def test_contract_cli_rejects_tampered_journal_hash_chain(tmp_path: Path) -> None:
    demo = run_demo(tmp_path / "demo")
    _tamper_record_three(demo.journal_path)
    contract_path = tmp_path / "contract.json"
    contract_path.write_text(json.dumps(contract_to_dict(evidence_contract())), encoding="utf-8")

    verify_result = runner.invoke(app, ["journal", "verify", str(demo.journal_path)])
    validate_result = runner.invoke(
        app,
        ["contract", "validate", str(contract_path), str(demo.journal_path)],
    )
    verify_data = json.loads(verify_result.stdout)
    validate_data = json.loads(validate_result.stdout)

    assert verify_result.exit_code == 1
    assert verify_data["issues"][0]["code"] == "event_hash_mismatch"
    assert validate_result.exit_code == 1
    assert validate_data["ok"] is False
    assert validate_data["violations"][0]["code"] == "journal_integrity_violation"
    assert "event_hash_mismatch" in validate_data["violations"][0]["message"]


def test_hash_chain_required_rejects_unverified_event_tuples(tmp_path: Path) -> None:
    result = validate_contract(demo_journal_events(tmp_path), evidence_contract())

    assert not result.ok
    assert result.violations[0].code == "journal_integrity_unverified"


def _tamper_record_three(journal_path: Path) -> None:
    lines = journal_path.read_bytes().splitlines()
    lines[2] = lines[2].replace(b'"requested_state":"requested"', b'"requested_state":"tampered"')
    journal_path.write_bytes(b"\n".join(lines) + b"\n")
