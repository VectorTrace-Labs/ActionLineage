from __future__ import annotations

import json
import subprocess
from datetime import UTC, datetime
from pathlib import Path

import pytest
from typer.testing import CliRunner

from actionlineage.cli import app
from actionlineage.journal import (
    ExternalAttestationType,
    JournalAnchorError,
    append_journal_anchor_log,
    create_external_anchor_attestation,
    create_git_anchor_statement,
    create_journal_anchor,
    create_journal_archive_manifest,
    create_segment_manifest,
    export_verified_prefix,
    load_external_anchor_attestation,
    load_git_anchor_statement,
    load_journal_anchor,
    load_journal_anchor_log,
    load_journal_archive_manifest,
    load_segment_manifest,
    locate_first_corrupt_record,
    verify_external_anchor_attestation,
    verify_git_anchor_statement,
    verify_journal,
    verify_journal_anchor,
    verify_journal_anchor_log,
    verify_journal_archive_manifest,
    write_external_anchor_attestation,
    write_git_anchor_statement,
    write_journal_anchor,
    write_journal_archive_manifest,
    write_segment_manifest,
)
from tests.journal.test_local_journal import (
    journal_lines,
    make_event,
    replace_journal_lines,
    write_valid_journal,
)

runner = CliRunner()
ANCHOR_TIME = datetime(2026, 6, 21, 19, 0, 0, tzinfo=UTC)


def test_anchor_verifies_current_journal_and_detects_tail_truncation(tmp_path: Path) -> None:
    path = tmp_path / "events.jsonl"
    journal = write_valid_journal(path, event_count=3)
    anchor = create_journal_anchor(path, created_at=ANCHOR_TIME)

    verified = verify_journal_anchor(path, anchor)
    assert journal.verify().records_verified == 3

    replace_journal_lines(path, journal_lines(path)[:2])
    truncated = verify_journal_anchor(path, anchor)

    assert verified.ok
    assert not truncated.ok
    assert truncated.issues[0].code == "journal_verification_failed"
    assert {issue.code for issue in truncated.journal_verification.issues} == {
        "expected_record_count_mismatch",
        "expected_last_hash_mismatch",
    }


def test_signed_anchor_requires_matching_key(tmp_path: Path) -> None:
    path = tmp_path / "events.jsonl"
    write_valid_journal(path, event_count=2)
    anchor = create_journal_anchor(path, signing_key=b"trusted-key", created_at=ANCHOR_TIME)

    without_key = verify_journal_anchor(path, anchor)
    wrong_key = verify_journal_anchor(path, anchor, signing_key=b"wrong-key")
    right_key = verify_journal_anchor(path, anchor, signing_key=b"trusted-key")

    assert anchor.signature is not None
    assert not without_key.ok
    assert without_key.issues[0].code == "signature_key_missing"
    assert not wrong_key.ok
    assert wrong_key.issues[0].code == "signature_mismatch"
    assert right_key.ok


def test_anchor_and_segment_manifest_round_trip(tmp_path: Path) -> None:
    journal_path = tmp_path / "events.jsonl"
    anchor_path = tmp_path / "events.anchor.json"
    manifest_path = tmp_path / "events.segment.json"
    write_valid_journal(journal_path, event_count=2)
    anchor = create_journal_anchor(journal_path, created_at=ANCHOR_TIME)
    manifest = create_segment_manifest(journal_path, created_at=ANCHOR_TIME)

    write_journal_anchor(anchor, anchor_path)
    write_segment_manifest(manifest, manifest_path)

    loaded_anchor = load_journal_anchor(anchor_path)
    loaded_manifest = load_segment_manifest(manifest_path)

    assert loaded_anchor == anchor
    assert loaded_manifest.anchor == anchor
    assert loaded_manifest.segment_index == 0


def test_external_anchor_attestation_round_trip_and_mismatch(tmp_path: Path) -> None:
    journal_path = tmp_path / "events.jsonl"
    attestation_path = tmp_path / "events.attestation.json"
    write_valid_journal(journal_path, event_count=2)
    anchor = create_journal_anchor(journal_path, created_at=ANCHOR_TIME)
    attestation = create_external_anchor_attestation(
        anchor,
        attester="reviewed-hsm",
        attestation_type=ExternalAttestationType.HARDWARE_KEY,
        statement_bytes=b"external-signature-or-timestamp",
        statement_reference="hsm://cluster/key/statement/1",
        created_at=ANCHOR_TIME,
    )

    write_external_anchor_attestation(attestation, attestation_path)
    loaded = load_external_anchor_attestation(attestation_path)
    verified = verify_external_anchor_attestation(
        anchor,
        loaded,
        statement_bytes=b"external-signature-or-timestamp",
    )
    wrong_statement = verify_external_anchor_attestation(
        anchor,
        loaded,
        statement_bytes=b"other-statement",
    )
    changed_anchor = create_journal_anchor(journal_path, signing_key=b"key", created_at=ANCHOR_TIME)
    wrong_anchor = verify_external_anchor_attestation(
        changed_anchor,
        loaded,
        statement_bytes=b"external-signature-or-timestamp",
    )

    assert loaded == attestation
    assert verified.ok
    assert not wrong_statement.ok
    assert wrong_statement.issues[0].code == "statement_digest_mismatch"
    assert not wrong_anchor.ok
    assert wrong_anchor.issues[0].code == "anchor_hash_mismatch"
    assert "external attestation statement" in loaded.limitations[0]


def test_locate_corrupt_record_and_export_verified_prefix(tmp_path: Path) -> None:
    path = tmp_path / "events.jsonl"
    prefix_path = tmp_path / "verified-prefix.jsonl"
    write_valid_journal(path, event_count=3)
    lines = journal_lines(path)
    lines[1] = lines[1].replace(b"child-1", b"child-X")
    replace_journal_lines(path, lines)

    issue = locate_first_corrupt_record(path)
    export = export_verified_prefix(path, prefix_path)

    assert issue is not None
    assert issue.record_number == 2
    assert export.records_exported == 1
    assert verify_journal(prefix_path).ok
    assert len(prefix_path.read_text(encoding="utf-8").splitlines()) == 1


def test_export_verified_prefix_rejects_in_place_output(tmp_path: Path) -> None:
    path = tmp_path / "events.jsonl"
    write_valid_journal(path, event_count=3)
    lines = journal_lines(path)
    lines[1] = lines[1].replace(b"child-1", b"child-X")
    replace_journal_lines(path, lines)
    original_bytes = path.read_bytes()

    with pytest.raises(JournalAnchorError, match="output path must differ"):
        export_verified_prefix(path, path)

    assert path.read_bytes() == original_bytes


def test_cli_export_verified_prefix_rejects_in_place_output(tmp_path: Path) -> None:
    path = tmp_path / "events.jsonl"
    write_valid_journal(path, event_count=3)
    lines = journal_lines(path)
    lines[1] = lines[1].replace(b"child-1", b"child-X")
    replace_journal_lines(path, lines)
    original_bytes = path.read_bytes()

    result = runner.invoke(app, ["journal", "export-verified-prefix", str(path), str(path)])
    data = json.loads(result.stdout)

    assert result.exit_code == 1
    assert data == {
        "error": "verified-prefix output path must differ from source journal",
        "ok": False,
    }
    assert path.read_bytes() == original_bytes


def test_cli_anchor_create_and_verify(tmp_path: Path) -> None:
    journal_path = tmp_path / "events.jsonl"
    anchor_path = tmp_path / "events.anchor.json"
    write_valid_journal(journal_path, event_count=2)

    create_result = runner.invoke(
        app,
        ["journal", "create-anchor", str(journal_path), str(anchor_path)],
    )
    verify_result = runner.invoke(
        app,
        ["journal", "verify-anchor", str(journal_path), str(anchor_path)],
    )

    assert create_result.exit_code == 0
    assert anchor_path.exists()
    assert json.loads(create_result.stdout)["record_count"] == 2
    assert verify_result.exit_code == 0
    assert json.loads(verify_result.stdout)["ok"] is True


def test_cli_signed_anchor_uses_key_file_without_leaking_key(tmp_path: Path) -> None:
    journal_path = tmp_path / "events.jsonl"
    anchor_path = tmp_path / "events.anchor.json"
    key_path = tmp_path / "anchor.key"
    wrong_key_path = tmp_path / "wrong.key"
    write_valid_journal(journal_path, event_count=2)
    key_path.write_bytes(b"trusted-cli-key")
    wrong_key_path.write_bytes(b"wrong-cli-key")

    create_result = runner.invoke(
        app,
        [
            "journal",
            "create-anchor",
            str(journal_path),
            str(anchor_path),
            "--signing-key-file",
            str(key_path),
        ],
    )
    without_key = runner.invoke(
        app,
        ["journal", "verify-anchor", str(journal_path), str(anchor_path)],
    )
    wrong_key = runner.invoke(
        app,
        [
            "journal",
            "verify-anchor",
            str(journal_path),
            str(anchor_path),
            "--signing-key-file",
            str(wrong_key_path),
        ],
    )
    right_key = runner.invoke(
        app,
        [
            "journal",
            "verify-anchor",
            str(journal_path),
            str(anchor_path),
            "--signing-key-file",
            str(key_path),
        ],
    )

    anchor = json.loads(create_result.stdout)
    assert create_result.exit_code == 0
    assert anchor["signature_algorithm"] == "hmac-sha256"
    assert "trusted-cli-key" not in create_result.stdout
    assert without_key.exit_code == 1
    assert json.loads(without_key.stdout)["issues"][0]["code"] == "signature_key_missing"
    assert wrong_key.exit_code == 1
    assert json.loads(wrong_key.stdout)["issues"][0]["code"] == "signature_mismatch"
    assert right_key.exit_code == 0
    assert json.loads(right_key.stdout)["ok"] is True


def test_cli_external_attestation_create_and_verify(tmp_path: Path) -> None:
    journal_path = tmp_path / "events.jsonl"
    anchor_path = tmp_path / "events.anchor.json"
    attestation_path = tmp_path / "events.attestation.json"
    statement_path = tmp_path / "statement.bin"
    wrong_statement_path = tmp_path / "wrong-statement.bin"
    write_valid_journal(journal_path, event_count=2)
    statement_path.write_bytes(b"external timestamp response")
    wrong_statement_path.write_bytes(b"other response")
    write_journal_anchor(create_journal_anchor(journal_path, created_at=ANCHOR_TIME), anchor_path)

    create_result = runner.invoke(
        app,
        [
            "journal",
            "create-external-attestation",
            str(anchor_path),
            str(attestation_path),
            "--statement-file",
            str(statement_path),
            "--attester",
            "tsa.example",
            "--attestation-type",
            "timestamp_authority",
            "--statement-reference",
            "urn:example:tsa:1",
        ],
    )
    verify_result = runner.invoke(
        app,
        [
            "journal",
            "verify-external-attestation",
            str(anchor_path),
            str(attestation_path),
            "--statement-file",
            str(statement_path),
        ],
    )
    wrong_result = runner.invoke(
        app,
        [
            "journal",
            "verify-external-attestation",
            str(anchor_path),
            str(attestation_path),
            "--statement-file",
            str(wrong_statement_path),
        ],
    )

    created = json.loads(create_result.stdout)
    assert create_result.exit_code == 0
    assert created["attester"] == "tsa.example"
    assert created["statement_reference"] == "urn:example:tsa:1"
    assert verify_result.exit_code == 0
    assert json.loads(verify_result.stdout)["ok"] is True
    assert wrong_result.exit_code == 1
    assert json.loads(wrong_result.stdout)["issues"][0]["code"] == "statement_digest_mismatch"


def test_anchor_log_appends_and_verifies_local_hash_chain(tmp_path: Path) -> None:
    journal_path = tmp_path / "events.jsonl"
    log_path = tmp_path / "anchors.log"
    journal = write_valid_journal(journal_path, event_count=1)
    first_anchor = create_journal_anchor(journal_path, created_at=ANCHOR_TIME)
    first_entry = append_journal_anchor_log(log_path, first_anchor, created_at=ANCHOR_TIME)
    journal.append(make_event(1))
    second_anchor = create_journal_anchor(journal_path, created_at=ANCHOR_TIME)
    second_entry = append_journal_anchor_log(log_path, second_anchor, created_at=ANCHOR_TIME)

    verification = verify_journal_anchor_log(log_path)
    entries = load_journal_anchor_log(log_path)

    assert verification.ok
    assert verification.records_verified == 2
    assert verification.last_entry_hash == second_entry.entry_hash
    assert second_entry.previous_entry_hash == first_entry.entry_hash
    assert [entry.sequence for entry in entries] == [1, 2]
    assert [entry.anchor.record_count for entry in entries] == [1, 2]


def test_anchor_log_detects_mutation_reorder_and_trusted_tail_truncation(
    tmp_path: Path,
) -> None:
    journal_path = tmp_path / "events.jsonl"
    log_path = tmp_path / "anchors.log"
    journal = write_valid_journal(journal_path, event_count=1)
    first_anchor = create_journal_anchor(journal_path, created_at=ANCHOR_TIME)
    append_journal_anchor_log(log_path, first_anchor, created_at=ANCHOR_TIME)
    journal.append(make_event(1))
    second_anchor = create_journal_anchor(journal_path, created_at=ANCHOR_TIME)
    second_entry = append_journal_anchor_log(log_path, second_anchor, created_at=ANCHOR_TIME)
    lines = journal_lines(log_path)

    mutated_path = tmp_path / "anchors-mutated.log"
    mutated_path.write_bytes(
        b"\n".join([lines[0].replace(b'"record_count":1', b'"record_count":9'), lines[1]]) + b"\n"
    )
    reordered_path = tmp_path / "anchors-reordered.log"
    reordered_path.write_bytes(b"\n".join([lines[1], lines[0]]) + b"\n")
    truncated_path = tmp_path / "anchors-truncated.log"
    truncated_path.write_bytes(lines[0] + b"\n")

    mutated = verify_journal_anchor_log(mutated_path)
    reordered = verify_journal_anchor_log(reordered_path)
    truncated = verify_journal_anchor_log(
        truncated_path,
        expected_record_count=2,
        expected_last_entry_hash=second_entry.entry_hash,
    )

    assert not mutated.ok
    assert mutated.issues[0].code == "entry_hash_mismatch"
    assert not reordered.ok
    assert reordered.issues[0].code == "sequence_mismatch"
    assert not truncated.ok
    assert {issue.code for issue in truncated.issues} == {
        "expected_record_count_mismatch",
        "expected_last_hash_mismatch",
    }


def test_cli_anchor_log_append_and_verify(tmp_path: Path) -> None:
    journal_path = tmp_path / "events.jsonl"
    anchor_path = tmp_path / "events.anchor.json"
    log_path = tmp_path / "anchors.log"
    write_valid_journal(journal_path, event_count=2)
    write_journal_anchor(create_journal_anchor(journal_path, created_at=ANCHOR_TIME), anchor_path)

    append_result = runner.invoke(
        app,
        ["journal", "append-anchor-log", str(anchor_path), str(log_path)],
    )
    verify_result = runner.invoke(
        app,
        ["journal", "verify-anchor-log", str(log_path), "--expected-record-count", "1"],
    )

    assert append_result.exit_code == 0
    assert json.loads(append_result.stdout)["sequence"] == 1
    assert verify_result.exit_code == 0
    assert json.loads(verify_result.stdout)["ok"] is True


def test_git_anchor_statement_verifies_committed_anchor_and_ref(
    tmp_path: Path,
) -> None:
    repo_path = _init_git_repo(tmp_path / "repo")
    journal_path = repo_path / "events.jsonl"
    anchor_path = repo_path / "events.anchor.json"
    statement_path = repo_path / "events.anchor.git.json"
    write_valid_journal(journal_path, event_count=2)
    write_journal_anchor(create_journal_anchor(journal_path, created_at=ANCHOR_TIME), anchor_path)
    _git(repo_path, "add", "events.anchor.json")
    _git(repo_path, "commit", "-m", "anchor journal")

    statement = create_git_anchor_statement(
        anchor_path,
        repository_path=repo_path,
        created_at=ANCHOR_TIME,
    )
    write_git_anchor_statement(statement, statement_path)
    loaded = load_git_anchor_statement(statement_path)
    verification = verify_git_anchor_statement(loaded, ref="HEAD")

    assert loaded == statement
    assert statement.anchor_git_path == "events.anchor.json"
    assert verification.ok


def test_journal_archive_manifest_round_trip_and_verifies_bytes(tmp_path: Path) -> None:
    journal_path = tmp_path / "events.jsonl"
    manifest_path = tmp_path / "events.archive.json"
    write_valid_journal(journal_path, event_count=2)

    manifest = create_journal_archive_manifest(
        journal_path,
        object_uri="s3://evidence-bucket/events.jsonl",
        retention_mode="governance",
        storage_class="STANDARD",
        created_at=ANCHOR_TIME,
    )
    write_journal_archive_manifest(manifest, manifest_path)
    loaded = load_journal_archive_manifest(manifest_path)
    verification = verify_journal_archive_manifest(loaded)

    assert loaded == manifest
    assert loaded.retention_mode == "governance"
    assert loaded.record_count == 2
    assert verification.ok


def test_journal_archive_manifest_detects_mutated_journal_bytes(tmp_path: Path) -> None:
    journal_path = tmp_path / "events.jsonl"
    write_valid_journal(journal_path, event_count=2)
    manifest = create_journal_archive_manifest(
        journal_path,
        object_uri="s3://evidence-bucket/events.jsonl",
        created_at=ANCHOR_TIME,
    )

    lines = journal_lines(journal_path)
    lines[0] = lines[0].replace(b"evt_0", b"evt_X", 1)
    replace_journal_lines(journal_path, lines)
    verification = verify_journal_archive_manifest(manifest)

    assert not verification.ok
    assert {issue.code for issue in verification.issues} == {
        "journal_hash_mismatch",
        "journal_verification_failed",
    }


def test_cli_archive_manifest_create_and_verify(tmp_path: Path) -> None:
    journal_path = tmp_path / "events.jsonl"
    manifest_path = tmp_path / "events.archive.json"
    write_valid_journal(journal_path, event_count=2)

    create_result = runner.invoke(
        app,
        [
            "journal",
            "create-archive-manifest",
            str(journal_path),
            str(manifest_path),
            "--object-uri",
            "s3://evidence-bucket/events.jsonl",
            "--retention-mode",
            "governance",
        ],
    )
    verify_result = runner.invoke(
        app,
        ["journal", "verify-archive-manifest", str(manifest_path)],
    )

    assert create_result.exit_code == 0
    assert json.loads(create_result.stdout)["object_uri"] == "s3://evidence-bucket/events.jsonl"
    assert verify_result.exit_code == 0
    assert json.loads(verify_result.stdout)["ok"] is True


def test_git_anchor_statement_detects_anchor_mutation_and_ref_drift(
    tmp_path: Path,
) -> None:
    repo_path = _init_git_repo(tmp_path / "repo")
    journal_path = repo_path / "events.jsonl"
    anchor_path = repo_path / "events.anchor.json"
    write_valid_journal(journal_path, event_count=2)
    write_journal_anchor(create_journal_anchor(journal_path, created_at=ANCHOR_TIME), anchor_path)
    _git(repo_path, "add", "events.anchor.json")
    _git(repo_path, "commit", "-m", "anchor journal")
    statement = create_git_anchor_statement(
        anchor_path,
        repository_path=repo_path,
        created_at=ANCHOR_TIME,
    )

    anchor_path.write_text('{"mutated":true}\n', encoding="utf-8")
    mutated = verify_git_anchor_statement(statement)
    write_journal_anchor(create_journal_anchor(journal_path, created_at=ANCHOR_TIME), anchor_path)
    (repo_path / "later.txt").write_text("later\n", encoding="utf-8")
    _git(repo_path, "add", "later.txt")
    _git(repo_path, "commit", "-m", "later commit")
    drifted = verify_git_anchor_statement(statement, anchor_path=anchor_path, ref="HEAD")

    assert not mutated.ok
    assert mutated.issues[0].code == "anchor_hash_mismatch"
    assert not drifted.ok
    assert {issue.code for issue in drifted.issues} == {"git_ref_mismatch"}


def test_cli_git_anchor_statement_create_and_verify(tmp_path: Path) -> None:
    repo_path = _init_git_repo(tmp_path / "repo")
    journal_path = repo_path / "events.jsonl"
    anchor_path = repo_path / "events.anchor.json"
    statement_path = repo_path / "events.anchor.git.json"
    write_valid_journal(journal_path, event_count=2)
    write_journal_anchor(create_journal_anchor(journal_path, created_at=ANCHOR_TIME), anchor_path)
    _git(repo_path, "add", "events.anchor.json")
    _git(repo_path, "commit", "-m", "anchor journal")

    create_result = runner.invoke(
        app,
        [
            "journal",
            "create-git-anchor-statement",
            str(anchor_path),
            str(statement_path),
            "--repo",
            str(repo_path),
        ],
    )
    verify_result = runner.invoke(
        app,
        [
            "journal",
            "verify-git-anchor-statement",
            str(anchor_path),
            str(statement_path),
            "--repo",
            str(repo_path),
            "--ref",
            "HEAD",
        ],
    )

    assert create_result.exit_code == 0
    assert statement_path.exists()
    assert json.loads(create_result.stdout)["anchor_git_path"] == "events.anchor.json"
    assert verify_result.exit_code == 0
    assert json.loads(verify_result.stdout)["ok"] is True


def _init_git_repo(repo_path: Path) -> Path:
    repo_path.mkdir(parents=True)
    _git(repo_path, "init")
    _git(repo_path, "config", "user.name", "ActionLineage Test")
    _git(repo_path, "config", "user.email", "actionlineage@example.invalid")
    return repo_path


def _git(repo_path: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-C", str(repo_path), *args],
        capture_output=True,
        check=True,
        text=True,
    )
