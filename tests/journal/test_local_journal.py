from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
from typer.testing import CliRunner

from actionlineage.cli import app
from actionlineage.domain import EventEnvelope, EventType, RedactionPolicy
from actionlineage.journal import JournalAppendError, JournalLockError, LocalJournal, verify_journal
from tests.domain.test_events import build_event

runner = CliRunner()


def make_event(index: int, *, label: str | None = None) -> EventEnvelope:
    if index == 0:
        return build_event(
            event_id="evt_0",
            event_type=EventType.AGENT_RUN_STARTED,
            root_event_id="evt_0",
            parent_event_id=None,
            sequence=0,
            payload={"label": label or "root-0"},
        )

    return build_event(
        event_id=f"evt_{index}",
        event_type=EventType.ACTION_NORMALIZED,
        root_event_id="evt_0",
        parent_event_id=f"evt_{index - 1}",
        sequence=index,
        payload={"label": label or f"child-{index}"},
    )


def write_valid_journal(path: Path, *, event_count: int = 3) -> LocalJournal:
    journal = LocalJournal(path)
    for index in range(event_count):
        journal.append(make_event(index))
    return journal


def journal_lines(path: Path) -> list[bytes]:
    return path.read_bytes().splitlines()


def replace_journal_lines(path: Path, lines: list[bytes]) -> None:
    path.write_bytes(b"\n".join(lines) + b"\n")


def assert_failed_at(result_code: str, path: Path, record_number: int) -> None:
    result = verify_journal(path)

    assert not result.ok
    assert result.issues
    assert result.issues[0].record_number == record_number
    assert result.issues[0].code == result_code


def test_valid_journal_verifies_successfully(tmp_path: Path) -> None:
    path = tmp_path / "events.jsonl"
    journal = write_valid_journal(path)

    result = journal.verify()
    events = list(journal.iter_events())

    assert result.ok
    assert result.records_verified == 3
    assert result.last_event_hash is not None
    assert result.issues == ()
    assert events[0].integrity.previous_event_hash is None
    assert events[0].integrity.event_hash is not None
    assert events[1].integrity.previous_event_hash == events[0].integrity.event_hash
    assert events[2].integrity.previous_event_hash == events[1].integrity.event_hash


def test_mutating_one_byte_fails_at_the_affected_record(tmp_path: Path) -> None:
    path = tmp_path / "events.jsonl"
    write_valid_journal(path)
    lines = journal_lines(path)
    lines[1] = lines[1].replace(b"child-1", b"child-X")
    replace_journal_lines(path, lines)

    assert_failed_at("event_hash_mismatch", path, record_number=2)


def test_deleting_middle_event_fails_verification(tmp_path: Path) -> None:
    path = tmp_path / "events.jsonl"
    write_valid_journal(path)
    lines = journal_lines(path)
    replace_journal_lines(path, [lines[0], lines[2]])

    assert_failed_at("sequence_mismatch", path, record_number=2)


def test_inserting_event_fails_verification(tmp_path: Path) -> None:
    path = tmp_path / "events.jsonl"
    write_valid_journal(path)
    lines = journal_lines(path)
    replace_journal_lines(path, [lines[0], lines[0], lines[1], lines[2]])

    assert_failed_at("sequence_mismatch", path, record_number=2)


def test_duplicating_event_fails_verification(tmp_path: Path) -> None:
    path = tmp_path / "events.jsonl"
    write_valid_journal(path)
    lines = journal_lines(path)
    replace_journal_lines(path, [*lines, lines[1]])

    assert_failed_at("sequence_mismatch", path, record_number=4)


def test_reordering_events_fails_verification(tmp_path: Path) -> None:
    path = tmp_path / "events.jsonl"
    write_valid_journal(path)
    lines = journal_lines(path)
    replace_journal_lines(path, [lines[0], lines[2], lines[1]])

    assert_failed_at("sequence_mismatch", path, record_number=2)


def test_tail_deletion_requires_trusted_anchor_to_detect(tmp_path: Path) -> None:
    path = tmp_path / "events.jsonl"
    journal = write_valid_journal(path)
    original_result = journal.verify()
    lines = journal_lines(path)
    replace_journal_lines(path, lines[:2])

    local_only_result = verify_journal(path)
    anchored_result = verify_journal(
        path,
        expected_record_count=original_result.records_verified,
        expected_last_event_hash=original_result.last_event_hash,
    )

    assert local_only_result.ok
    assert not anchored_result.ok
    assert {issue.code for issue in anchored_result.issues} == {
        "expected_record_count_mismatch",
        "expected_last_hash_mismatch",
    }


def test_journal_append_redacts_before_hashing_and_persistence(tmp_path: Path) -> None:
    path = tmp_path / "events.jsonl"
    raw_secret = "journal-secret-value-123456789"
    event = make_event(0).model_copy(
        update={
            "payload": {
                "arguments": {
                    "client_secret_value": raw_secret,
                    "benign": "kept",
                }
            }
        }
    )
    journal = LocalJournal(
        path,
        redaction_policy=RedactionPolicy.from_paths(("payload.arguments.client_secret_value",)),
    )

    persisted_event = journal.append(event)
    persisted_text = path.read_text(encoding="utf-8")

    assert raw_secret not in persisted_text
    assert persisted_event.payload["arguments"]["client_secret_value"]["marker"] == (
        "actionlineage.redacted.v1"
    )
    assert verify_journal(path).ok


def test_concurrent_duplicate_sequence_attempt_fails_visibly(tmp_path: Path) -> None:
    path = tmp_path / "events.jsonl"
    journal = LocalJournal(path)
    journal.append(make_event(0))
    event_a = make_event(1, label="child-a")
    event_b = make_event(1, label="child-b")

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(
            executor.map(
                lambda event: append_or_return_error(journal, event),
                (event_a, event_b),
            )
        )

    assert sum(isinstance(result, EventEnvelope) for result in results) == 1
    assert sum(isinstance(result, JournalAppendError) for result in results) == 1
    assert journal.verify().ok
    assert journal.verify().records_verified == 2


def append_or_return_error(
    journal: LocalJournal,
    event: EventEnvelope,
) -> EventEnvelope | JournalAppendError:
    try:
        return journal.append(event)
    except JournalAppendError as exc:
        return exc


def test_lock_contention_fails_visibly(tmp_path: Path) -> None:
    path = tmp_path / "events.jsonl"
    lock_path = path.with_suffix(f"{path.suffix}.lock")
    lock_path.write_text("held", encoding="utf-8")
    journal = LocalJournal(path, lock_timeout_seconds=0.01, lock_poll_seconds=0.001)

    with pytest.raises(JournalLockError):
        journal.append(make_event(0))


def test_cli_verify_outputs_machine_readable_json(tmp_path: Path) -> None:
    path = tmp_path / "events.jsonl"
    journal = write_valid_journal(path)
    expected = journal.verify()

    result = runner.invoke(
        app,
        [
            "journal",
            "verify",
            str(path),
            "--expected-record-count",
            str(expected.records_verified),
            "--expected-last-event-hash",
            expected.last_event_hash or "",
        ],
    )
    data = json.loads(result.stdout)

    assert result.exit_code == 0
    assert data["ok"] is True
    assert data["records_verified"] == 3
    assert data["last_event_hash"] == expected.last_event_hash
    assert data["issues"] == []


def test_cli_verify_returns_nonzero_for_invalid_journal(tmp_path: Path) -> None:
    path = tmp_path / "events.jsonl"
    write_valid_journal(path)
    lines = journal_lines(path)
    lines[1] = lines[1].replace(b"child-1", b"child-X")
    replace_journal_lines(path, lines)

    result = runner.invoke(app, ["journal", "verify", str(path)])
    data = json.loads(result.stdout)

    assert result.exit_code == 1
    assert data["ok"] is False
    assert data["issues"][0]["code"] == "event_hash_mismatch"


def test_journal_verify_parse_error_does_not_echo_raw_payload(tmp_path: Path) -> None:
    path = tmp_path / "events.jsonl"
    raw_secret = "Bearer journal-parse-secret-value"
    path.write_text(
        '{"spec_version":"actionlineage.dev/v1alpha1",'
        f'"payload":{{"authorization":"{raw_secret}"}},'
        '"event_type":"agent.run.started"}\n',
        encoding="utf-8",
    )

    result = verify_journal(path)

    assert not result.ok
    assert result.issues[0].code == "parse_error"
    assert raw_secret not in result.issues[0].message
