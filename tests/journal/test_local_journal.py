from __future__ import annotations

import hashlib
import json
import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
from pytest import MonkeyPatch
from typer.testing import CliRunner

import actionlineage.journal.local as local_journal_module
from actionlineage.cli import app
from actionlineage.domain import (
    PLANNED_CANONICALIZATION_VERSION,
    EventEnvelope,
    EventType,
    IntegrityMetadata,
    RedactionPolicy,
    serialize_event,
)
from actionlineage.journal import (
    JournalAppendError,
    JournalLockError,
    LocalJournal,
    verify_journal,
)
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


def journal_raw_lines(path: Path) -> list[bytes]:
    return path.read_bytes().splitlines(keepends=True)


def replace_journal_lines(path: Path, lines: list[bytes]) -> None:
    path.write_bytes(b"\n".join(lines) + b"\n")


def write_private_bytes(path: Path, payload: bytes) -> None:
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        os.write(fd, payload)
        os.fsync(fd)
    finally:
        os.close(fd)


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


def test_valid_journal_records_are_exact_canonical_lines(tmp_path: Path) -> None:
    path = tmp_path / "events.jsonl"
    journal = write_valid_journal(path)
    snapshot = journal.verified_snapshot()

    assert snapshot.journal_sha256 == f"sha256:{hashlib.sha256(path.read_bytes()).hexdigest()}"
    assert journal_raw_lines(path) == [serialize_event(event) + b"\n" for event in snapshot.events]


def test_append_rejects_planned_v1_canonicalization_label(tmp_path: Path) -> None:
    path = tmp_path / "events.jsonl"
    event = make_event(0).model_copy(
        update={
            "integrity": IntegrityMetadata(
                canonicalization=PLANNED_CANONICALIZATION_VERSION,
                previous_event_hash=None,
                event_hash=None,
            )
        }
    )

    with pytest.raises(ValueError, match="unsupported persisted event canonicalization"):
        LocalJournal(path).append(event)

    assert not path.exists()


def test_append_creates_private_storage_under_default_umask(tmp_path: Path) -> None:
    if os.name != "posix":
        pytest.skip("POSIX mode-bit assertions do not apply on this platform")
    path = tmp_path / "storage" / "events.jsonl"
    original_umask = os.umask(0o022)
    try:
        LocalJournal(path).append(make_event(0))
    finally:
        os.umask(original_umask)

    assert path.parent.stat().st_mode & 0o777 == 0o700
    assert path.stat().st_mode & 0o777 == 0o600
    assert path.with_suffix(f"{path.suffix}.lock").stat().st_mode & 0o777 == 0o600


def test_verified_snapshot_is_immutable_after_source_file_changes(tmp_path: Path) -> None:
    path = tmp_path / "events.jsonl"
    journal = write_valid_journal(path)
    snapshot = journal.verified_snapshot()
    original_events = snapshot.events
    original_terminal_hash = snapshot.terminal_hash

    journal.append(make_event(3))

    assert snapshot.ok
    assert snapshot.events == original_events
    assert snapshot.record_count == 3
    assert snapshot.terminal_hash == original_terminal_hash
    assert journal.verified_snapshot().record_count == 4


def test_journal_source_identity_is_path_independent_for_same_verified_bytes(
    tmp_path: Path,
) -> None:
    path = tmp_path / "events.jsonl"
    copied_path = tmp_path / "copied-events.jsonl"
    journal = write_valid_journal(path)
    snapshot = journal.verified_snapshot()
    copied_path.write_bytes(path.read_bytes())
    copied_snapshot = LocalJournal(copied_path).verified_snapshot()

    assert snapshot.source_identity.startswith("actionlineage.dev/journal-source-identity-v1:")
    assert copied_snapshot.source_identity == snapshot.source_identity

    LocalJournal(copied_path).append(make_event(3))

    assert LocalJournal(copied_path).verified_snapshot().source_identity != snapshot.source_identity


def test_verified_snapshot_events_reject_nested_payload_mutation(tmp_path: Path) -> None:
    path = tmp_path / "events.jsonl"
    journal = LocalJournal(path)
    journal.append(
        make_event(0).model_copy(
            update={
                "payload": {
                    "metadata": {"reviewed": True},
                    "evidence": [{"id": "ev_1", "tags": ["observed"]}],
                }
            }
        )
    )
    snapshot = journal.verified_snapshot()
    event = snapshot.events[0]
    original_serialized = serialize_event(event)
    original_hash = event.integrity.event_hash

    with pytest.raises(TypeError):
        event.payload["metadata"]["reviewed"] = False  # type: ignore[index]
    with pytest.raises(TypeError):
        event.payload["evidence"].append({"id": "ev_2"})  # type: ignore[union-attr]
    with pytest.raises(TypeError):
        event.payload["evidence"][0]["id"] = "ev_tampered"  # type: ignore[index]

    assert serialize_event(snapshot.events[0]) == original_serialized
    assert snapshot.events[0].integrity.event_hash == original_hash
    assert journal.verify().ok


def test_mutating_one_byte_fails_at_the_affected_record(tmp_path: Path) -> None:
    path = tmp_path / "events.jsonl"
    write_valid_journal(path)
    lines = journal_lines(path)
    lines[1] = lines[1].replace(b"child-1", b"child-X")
    replace_journal_lines(path, lines)

    assert_failed_at("event_hash_mismatch", path, record_number=2)


@pytest.mark.parametrize(
    ("original", "replacement"),
    (
        (b'"event_id":"evt_0"', b'"event_id":"evt_0","event_id":"evt_0"'),
        (b'"sequence":0', b'"sequence":0,"sequence":0'),
        (b'"trust":"trusted"', b'"trust":"trusted","trust":"trusted"'),
        (b'"trace_id":"trace_01"', b'"trace_id":"trace_01","trace_id":"trace_01"'),
        (b'"canonicalization":', b'"canonicalization":"duplicate","canonicalization":'),
        (b'"label":"root-0"', b'"label":"root-0","label":"root-0"'),
        (
            b'"principal_id":"agent_demo"',
            b'"principal_id":"agent_demo","principal_id":"agent_demo"',
        ),
        (b'"component":"unit-test"', b'"component":"unit-test","component":"unit-test"'),
    ),
)
def test_duplicate_json_keys_fail_journal_parsing(
    tmp_path: Path,
    original: bytes,
    replacement: bytes,
) -> None:
    path = tmp_path / "events.jsonl"
    write_valid_journal(path)
    lines = journal_lines(path)
    assert original in lines[0]
    lines[0] = lines[0].replace(original, replacement, 1)
    replace_journal_lines(path, lines)

    assert_failed_at("parse_error", path, record_number=1)


def test_planned_v1_canonicalization_label_fails_journal_verification(
    tmp_path: Path,
) -> None:
    path = tmp_path / "events.jsonl"
    write_valid_journal(path, event_count=1)
    lines = journal_lines(path)
    lines[0] = lines[0].replace(
        b"actionlineage.dev/json-deterministic-v0",
        b"actionlineage.dev/json-canonicalization-v1",
    )
    replace_journal_lines(path, lines)

    result = verify_journal(path)

    assert not result.ok
    assert result.records_verified == 0
    assert result.issues[0].record_number == 1
    assert result.issues[0].code == "unsupported_canonicalization"
    assert result.issues[0].actual == PLANNED_CANONICALIZATION_VERSION


@pytest.mark.parametrize(
    "mutate",
    (
        lambda line: _move_spec_version_to_front(line),
        lambda line: line.replace(b'":{"', b'": {"', 1),
    ),
)
def test_noncanonical_json_format_fails_even_when_semantics_match(
    tmp_path: Path,
    mutate,
) -> None:
    path = tmp_path / "events.jsonl"
    write_valid_journal(path)
    lines = journal_raw_lines(path)
    lines[0] = mutate(lines[0].removesuffix(b"\n")) + b"\n"
    path.write_bytes(b"".join(lines))

    result = verify_journal(path)

    assert not result.ok
    assert result.records_verified == 0
    assert result.issues[0].record_number == 1
    assert result.issues[0].code == "noncanonical_record"
    assert result.issues[0].message == (
        "journal record bytes do not exactly match canonical serialization"
    )


def _move_spec_version_to_front(line: bytes) -> bytes:
    data = json.loads(line)
    return json.dumps(
        {"spec_version": data.pop("spec_version"), **data},
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=False,
        allow_nan=False,
    ).encode("utf-8")


def test_crlf_line_ending_fails_canonical_byte_verification(tmp_path: Path) -> None:
    path = tmp_path / "events.jsonl"
    write_valid_journal(path)
    path.write_bytes(path.read_bytes().replace(b"\n", b"\r\n", 1))

    assert_failed_at("noncanonical_record", path, record_number=1)


@pytest.mark.parametrize(
    "payload",
    (
        b"\xff\n",
        b'{"spec_version":"actionlineage.dev/v1alpha1"}{}\n',
        b'{"spec_version":"actionlineage.dev/v1alpha1"} {"event_id":"evt_extra"}\n',
        b'{"spec_version":"actionlineage.dev/v1alpha1","payload":{"value":NaN}}\n',
    ),
)
def test_invalid_json_bytes_or_tokens_fail_journal_parsing(
    tmp_path: Path,
    payload: bytes,
) -> None:
    path = tmp_path / "events.jsonl"
    write_private_bytes(path, payload)

    assert_failed_at("parse_error", path, record_number=1)


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


def test_truncated_final_record_without_newline_fails_verification(tmp_path: Path) -> None:
    path = tmp_path / "events.jsonl"
    write_valid_journal(path)
    path.write_bytes(path.read_bytes().removesuffix(b"\n"))

    result = verify_journal(path)

    assert not result.ok
    assert result.records_verified == 2
    assert result.issues[0].record_number == 3
    assert result.issues[0].code == "truncated_record"
    assert "child-2" not in result.issues[0].message


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


def test_stale_lock_metadata_does_not_block_next_writer(tmp_path: Path) -> None:
    path = tmp_path / "events.jsonl"
    lock_path = path.with_suffix(f"{path.suffix}.lock")
    lock_path.write_text("held", encoding="utf-8")
    if os.name == "posix":
        lock_path.chmod(0o600)

    journal = LocalJournal(path, lock_timeout_seconds=0.01, lock_poll_seconds=0.001)
    persisted = journal.append(make_event(0))

    assert persisted.event_id == "evt_0"
    assert journal.verify().ok
    assert lock_path.exists()
    if os.name == "posix":
        assert lock_path.stat().st_mode & 0o777 == 0o600


def test_active_lock_contention_fails_visibly(tmp_path: Path) -> None:
    path = tmp_path / "events.jsonl"
    lock_path = path.with_suffix(f"{path.suffix}.lock")
    journal = LocalJournal(path, lock_timeout_seconds=0.01, lock_poll_seconds=0.001)

    with (
        local_journal_module._journal_lock(
            lock_path,
            mode="exclusive",
            operation="test",
            timeout_seconds=0.01,
            poll_seconds=0.001,
        ),
        pytest.raises(JournalLockError),
    ):
        journal.append(make_event(0))


def test_append_directory_permission_failure_redacts_exception_detail(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    path = tmp_path / "events.jsonl"
    raw_secret = "journalpermissionsecretvalue123456789"

    def fail_directory_check(_path: Path) -> None:
        raise local_journal_module.JournalStoragePermissionError(
            f"storage path rejected for Bearer {raw_secret}"
        )

    monkeypatch.setattr(local_journal_module, "_ensure_private_directory", fail_directory_check)

    with pytest.raises(JournalAppendError) as error:
        LocalJournal(path).append(make_event(0))

    message = str(error.value)
    assert raw_secret not in message
    assert "Bearer [REDACTED:bearer_token]" in message
    assert not path.exists()


def test_append_preflight_io_failure_is_bounded_and_releases_lock(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    path = tmp_path / "events.jsonl"
    raw_secret = "preflight-secret-value"
    event = make_event(0).model_copy(update={"payload": {"secret": raw_secret}})

    def fail_preflight(*_args: object, **_kwargs: object) -> object:
        raise OSError(f"permission denied while reading {raw_secret}")

    monkeypatch.setattr(local_journal_module, "verified_journal_snapshot", fail_preflight)

    with pytest.raises(JournalAppendError) as error:
        LocalJournal(path).append(event)

    assert str(error.value) == "failed to verify existing journal before append"
    assert raw_secret not in str(error.value)
    assert path.with_suffix(f"{path.suffix}.lock").exists()
    assert not path.exists()


def test_append_write_io_failure_is_bounded_and_releases_lock(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    path = tmp_path / "events.jsonl"
    raw_secret = "write-secret-value"
    event = make_event(0).model_copy(update={"payload": {"secret": raw_secret}})

    def fail_write(_path: Path, _canonical_bytes: bytes) -> None:
        raise OSError(f"no space left while writing {raw_secret}")

    monkeypatch.setattr(local_journal_module, "_append_line", fail_write)

    with pytest.raises(JournalAppendError) as error:
        LocalJournal(path).append(event)

    assert str(error.value) == "failed to append event to journal"
    assert raw_secret not in str(error.value)
    assert path.with_suffix(f"{path.suffix}.lock").exists()
    assert not path.exists()


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


def test_cli_verify_reports_truncated_final_record(tmp_path: Path) -> None:
    path = tmp_path / "events.jsonl"
    write_valid_journal(path)
    path.write_bytes(path.read_bytes().removesuffix(b"\n"))

    result = runner.invoke(app, ["journal", "verify", str(path)])
    data = json.loads(result.stdout)

    assert result.exit_code == 1
    assert data["ok"] is False
    assert data["records_verified"] == 2
    assert data["issues"][0]["code"] == "truncated_record"


def test_journal_verify_parse_error_does_not_echo_raw_payload(tmp_path: Path) -> None:
    path = tmp_path / "events.jsonl"
    raw_secret = "Bearer journal-parse-secret-value"
    write_private_bytes(
        path,
        (
            '{"spec_version":"actionlineage.dev/v1alpha1",'
            f'"payload":{{"authorization":"{raw_secret}"}},'
            '"event_type":"agent.run.started"}\n'
        ).encode(),
    )

    result = verify_journal(path)

    assert not result.ok
    assert result.issues[0].code == "parse_error"
    assert raw_secret not in result.issues[0].message
