from __future__ import annotations

import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from actionlineage import (
    CompatibilityStatus,
    EventParseError,
    assess_event_compatibility,
    parse_event,
)
from actionlineage.domain import event_to_dict
from actionlineage.journal import iter_events, verify_journal
from actionlineage.projection import query_timeline, rebuild_projection

FIXTURE_DIR = Path("tests/fixtures/journals")
EVIDENCE_LINK_SCHEMA_PATH = Path("schemas/evidence-link-v1alpha1.schema.json")
GOLDEN_JOURNALS = (
    "baseline-v1alpha1.jsonl",
    "legacy-agent-tool-v1alpha1.jsonl",
    "evidence-plane-v1alpha1.jsonl",
)


@pytest.mark.parametrize("fixture_name", GOLDEN_JOURNALS)
def test_golden_journals_remain_readable_and_projectable(
    tmp_path: Path,
    fixture_name: str,
) -> None:
    journal_path = FIXTURE_DIR / fixture_name
    result = verify_journal(journal_path)

    assert result.ok
    assert result.records_verified == len(journal_path.read_text(encoding="utf-8").splitlines())

    projection_path = tmp_path / f"{fixture_name}.sqlite"
    rebuild = rebuild_projection(journal_path, projection_path)
    timeline = query_timeline(
        projection_path,
        journal_path=journal_path,
        trace_id="trace_golden",
    )

    assert rebuild.records_indexed == result.records_verified
    assert timeline.as_dict()["event_count"] == result.records_verified


def test_legacy_agent_tool_event_is_preserved_as_known_compatibility_event() -> None:
    events = list(iter_events(FIXTURE_DIR / "legacy-agent-tool-v1alpha1.jsonl"))
    legacy_event = events[-1]
    assessment = assess_event_compatibility(legacy_event)

    assert legacy_event.event_type == "agent.tool.call.completed"
    assert assessment.status == CompatibilityStatus.SUPPORTED_KNOWN_EVENT
    assert assessment.can_read
    assert assessment.can_interpret_semantics


def test_evidence_plane_fixture_indexes_evidence_link() -> None:
    events = list(iter_events(FIXTURE_DIR / "evidence-plane-v1alpha1.jsonl"))
    verified_event = events[-1]

    assert verified_event.payload["evidence_link"]["subject_event_id"] == "evt_tool_ack"
    assert verified_event.payload["evidence_link"]["evidence_event_id"] == "evt_observed"
    assert verified_event.payload["evidence_link"]["verification_status"] == "verified"


def test_evidence_link_payload_validates_against_json_schema() -> None:
    schema = json.loads(EVIDENCE_LINK_SCHEMA_PATH.read_text(encoding="utf-8"))
    validator = Draft202012Validator(schema)
    events = list(iter_events(FIXTURE_DIR / "evidence-plane-v1alpha1.jsonl"))
    evidence_link = event_to_dict(events[-1])["payload"]["evidence_link"]

    errors = sorted(validator.iter_errors(evidence_link), key=lambda error: error.path)

    assert errors == []


def test_public_parse_error_does_not_echo_raw_payload() -> None:
    raw_secret = "Bearer should-not-appear-in-error"
    invalid_event = (
        '{"spec_version":"actionlineage.dev/v1alpha1",'
        f'"payload":{{"authorization":"{raw_secret}"}},'
        '"event_type":"agent.run.started"}'
    )

    with pytest.raises(EventParseError) as exc_info:
        parse_event(invalid_event)

    assert raw_secret not in str(exc_info.value)
    assert "payload" not in str(exc_info.value)
    assert exc_info.value.error_count > 0
