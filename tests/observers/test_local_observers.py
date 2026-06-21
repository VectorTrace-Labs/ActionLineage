from __future__ import annotations

import sqlite3

from actionlineage.domain import (
    CorroborationType,
    EventType,
    ResourceType,
    TrustLevel,
    VerificationStatus,
)
from actionlineage.observers import (
    FilesystemObserver,
    HttpResponseReadbackObserver,
    HttpServerLogObserver,
    MockHttpReceiverObserver,
    ObserverOutcome,
    ProcessObserver,
    SqliteReadbackObserver,
    WebhookReceiptObserver,
    self_reported_verification,
    verify_observation,
)


def test_filesystem_observer_reports_observed_and_verified(tmp_path) -> None:
    path = tmp_path / "observed.txt"
    path.write_text("evidence", encoding="utf-8")
    observation = FilesystemObserver().observe_file_state(path, expected_exists=True)
    decision = verify_observation(
        subject_event_id="evt_ack",
        evidence_event_id="evt_observed",
        observation=observation,
        confidence=0.95,
    )

    assert observation.outcome == ObserverOutcome.OBSERVED
    assert observation.verification_status == VerificationStatus.OBSERVED
    assert observation.event_type == EventType.SIDE_EFFECT_OBSERVED
    assert decision.event_type == EventType.SIDE_EFFECT_VERIFIED
    assert decision.evidence_link.verification_status == VerificationStatus.VERIFIED
    assert decision.evidence_link.corroboration_type == CorroborationType.INDEPENDENT_OBSERVER


def test_filesystem_absence_is_unverified_not_proof_of_absence(tmp_path) -> None:
    path = tmp_path / "missing.txt"
    observation = FilesystemObserver().observe_file_state(path)
    payload = observation.as_payload()

    assert observation.outcome == ObserverOutcome.UNVERIFIED
    assert observation.event_type == EventType.SIDE_EFFECT_UNVERIFIED
    assert payload["verification_status"] == "unverified"
    assert "not proof of absence" in " ".join(payload["limitations"])


def test_filesystem_conflict_and_timeout_are_first_class(tmp_path) -> None:
    path = tmp_path / "missing-expected.txt"
    conflict = FilesystemObserver().observe_file_state(path, expected_exists=True)
    timeout = FilesystemObserver().timed_out(path)
    conflict_decision = verify_observation(
        subject_event_id="evt_ack",
        evidence_event_id="evt_conflict",
        observation=conflict,
        confidence=0.7,
    )
    timeout_decision = verify_observation(
        subject_event_id="evt_ack",
        evidence_event_id="evt_timeout",
        observation=timeout,
        confidence=0.0,
    )

    assert conflict.outcome == ObserverOutcome.CONFLICTING
    assert conflict_decision.event_type == EventType.SIDE_EFFECT_CONFLICT_DETECTED
    assert conflict_decision.evidence_link.verification_status == VerificationStatus.CONFLICTING
    assert timeout.outcome == ObserverOutcome.TIMED_OUT
    assert timeout_decision.event_type == EventType.SIDE_EFFECT_TIMED_OUT
    assert timeout_decision.evidence_link.verification_status == VerificationStatus.TIMED_OUT


def test_http_receiver_observer_reports_verified_and_conflicting_receipts() -> None:
    observer = MockHttpReceiverObserver()
    observer.record_receipt(destination="http://receiver.local/collect", body_digest="sha256:body")

    observed = observer.observe_receipt(
        destination="http://receiver.local/collect",
        expected_body_digest="sha256:body",
    )
    conflicting = observer.observe_receipt(
        destination="http://receiver.local/collect",
        expected_body_digest="sha256:other",
    )

    assert observed.outcome == ObserverOutcome.OBSERVED
    assert observed.trust == TrustLevel.LOCAL
    assert conflicting.outcome == ObserverOutcome.CONFLICTING


def test_http_server_log_observer_reports_observed_conflicting_and_unverified() -> None:
    observer = HttpServerLogObserver()
    observer.record_access(
        url="https://receiver.local/collect",
        method="post",
        status_code=202,
        request_id="req-1",
        body_digest="sha256:log-body",
    )

    observed = observer.observe_access(
        url="https://receiver.local/collect",
        method="POST",
        expected_status_code=202,
        expected_body_digest="sha256:log-body",
    )
    conflicting = observer.observe_access(
        url="https://receiver.local/collect",
        method="POST",
        expected_status_code=500,
        expected_body_digest="sha256:other-body",
    )
    unverified = observer.observe_access(url="https://receiver.local/missing", method="POST")

    assert observed.outcome == ObserverOutcome.OBSERVED
    assert observed.as_payload()["observed_state"]["log_entry"]["request_id"] == "req-1"
    assert conflicting.outcome == ObserverOutcome.CONFLICTING
    assert conflicting.as_payload()["observed_state"]["conflicts"] == [
        "body_digest",
        "status_code",
    ]
    assert unverified.outcome == ObserverOutcome.UNVERIFIED
    assert "not proof of absence" in " ".join(unverified.as_payload()["limitations"])


def test_http_response_readback_observer_reports_observed_conflicting_and_unverified() -> None:
    observer = HttpResponseReadbackObserver()
    observer.record_response(
        url="https://receiver.local/status/123",
        status_code=200,
        body_digest="sha256:response-body",
        etag="etag-1",
    )

    observed = observer.observe_response(
        url="https://receiver.local/status/123",
        expected_status_code=200,
        expected_body_digest="sha256:response-body",
        expected_etag="etag-1",
    )
    conflicting = observer.observe_response(
        url="https://receiver.local/status/123",
        expected_status_code=404,
        expected_body_digest="sha256:other-body",
        expected_etag="etag-2",
    )
    unverified = observer.observe_response(url="https://receiver.local/status/missing")

    assert observed.outcome == ObserverOutcome.OBSERVED
    assert observed.as_payload()["observed_state"]["response"]["etag"] == "etag-1"
    assert conflicting.outcome == ObserverOutcome.CONFLICTING
    assert conflicting.as_payload()["observed_state"]["conflicts"] == [
        "body_digest",
        "etag",
        "status_code",
    ]
    assert unverified.outcome == ObserverOutcome.UNVERIFIED
    assert "not proof of absence" in " ".join(unverified.as_payload()["limitations"])


def test_webhook_receipt_observer_reports_observed_conflicting_and_unverified() -> None:
    observer = WebhookReceiptObserver()
    observer.record_delivery(
        callback_url="https://receiver.local/hooks/actionlineage",
        delivery_id="delivery-1",
        body_digest="sha256:webhook-body",
        status_code=202,
        signature_digest="sha256:signature",
    )

    observed = observer.observe_delivery(
        callback_url="https://receiver.local/hooks/actionlineage",
        delivery_id="delivery-1",
        expected_body_digest="sha256:webhook-body",
        expected_status_code=202,
    )
    conflicting = observer.observe_delivery(
        callback_url="https://receiver.local/hooks/actionlineage",
        delivery_id="delivery-1",
        expected_body_digest="sha256:other-body",
        expected_status_code=500,
    )
    unverified = observer.observe_delivery(
        callback_url="https://receiver.local/hooks/actionlineage",
        delivery_id="delivery-missing",
    )

    assert observed.outcome == ObserverOutcome.OBSERVED
    assert observed.as_payload()["observed_state"]["receipt"]["signature_digest"] == (
        "sha256:signature"
    )
    assert conflicting.outcome == ObserverOutcome.CONFLICTING
    assert conflicting.as_payload()["observed_state"]["conflicts"] == [
        "body_digest",
        "status_code",
    ]
    assert unverified.outcome == ObserverOutcome.UNVERIFIED
    assert "not proof of absence" in " ".join(unverified.as_payload()["limitations"])


def test_process_observer_and_self_reported_verification() -> None:
    process = ProcessObserver().observe_exit(process_identifier="pid:123", return_code=0)
    self_reported = self_reported_verification(
        subject_event_id="evt_ack",
        observer_identity="tool.self.report",
    )

    assert process.outcome == ObserverOutcome.OBSERVED
    assert process.as_payload()["observed_state"]["return_code"] == 0
    assert self_reported.event_type == EventType.SIDE_EFFECT_UNVERIFIED
    assert self_reported.evidence_link.corroboration_type == CorroborationType.SELF_REPORTED
    assert self_reported.evidence_link.confidence == 0.2


def test_observer_unavailable_remains_unverified(tmp_path) -> None:
    unavailable = FilesystemObserver().unavailable(tmp_path / "x", reason="permission denied")
    decision = verify_observation(
        subject_event_id="evt_ack",
        evidence_event_id="evt_unavailable",
        observation=unavailable,
        confidence=0.0,
    )

    assert unavailable.outcome == ObserverOutcome.UNAVAILABLE
    assert unavailable.verification_status == VerificationStatus.UNVERIFIED
    assert decision.event_type == EventType.SIDE_EFFECT_UNVERIFIED


def test_sqlite_readback_observer_reports_matching_row(tmp_path) -> None:
    database_path = tmp_path / "readback.sqlite"
    with sqlite3.connect(database_path) as connection:
        connection.execute("create table audit_log (event_id text primary key, status text)")
        connection.execute(
            "insert into audit_log (event_id, status) values (?, ?)",
            ("evt_db", "written"),
        )

    observation = SqliteReadbackObserver().observe_row(
        database_path,
        table="audit_log",
        where={"event_id": "evt_db", "status": "written"},
    )

    assert observation.outcome == ObserverOutcome.OBSERVED
    assert observation.resource_type == ResourceType.DATABASE_RECORD
    assert observation.as_payload()["observed_state"]["matching_rows"] == 1


def test_sqlite_readback_observer_reports_observed_absence_for_expected_absent_row(
    tmp_path,
) -> None:
    database_path = tmp_path / "readback.sqlite"
    with sqlite3.connect(database_path) as connection:
        connection.execute("create table audit_log (event_id text primary key)")

    observation = SqliteReadbackObserver().observe_row(
        database_path,
        table="audit_log",
        where={"event_id": "evt_deleted"},
        expected_exists=False,
    )

    assert observation.outcome == ObserverOutcome.OBSERVED
    assert observation.as_payload()["observed_state"]["matching_rows"] == 0
    assert "proof " + "of absence" not in " ".join(observation.as_payload()["limitations"])


def test_sqlite_readback_observer_reports_conflict_for_unexpected_row_state(tmp_path) -> None:
    database_path = tmp_path / "readback.sqlite"
    with sqlite3.connect(database_path) as connection:
        connection.execute("create table audit_log (event_id text primary key)")

    observation = SqliteReadbackObserver().observe_row(
        database_path,
        table="audit_log",
        where={"event_id": "evt_missing"},
    )

    assert observation.outcome == ObserverOutcome.CONFLICTING
    assert observation.verification_status == VerificationStatus.CONFLICTING


def test_sqlite_readback_observer_unverified_when_database_missing(tmp_path) -> None:
    observation = SqliteReadbackObserver().observe_row(
        tmp_path / "missing.sqlite",
        table="audit_log",
        where={"event_id": "evt_missing"},
    )

    assert observation.outcome == ObserverOutcome.UNVERIFIED
    assert observation.verification_status == VerificationStatus.UNVERIFIED
    assert "not evidence of absence" in " ".join(observation.as_payload()["limitations"])


def test_sqlite_readback_observer_invalid_identifier_is_unavailable(tmp_path) -> None:
    database_path = tmp_path / "readback.sqlite"
    with sqlite3.connect(database_path) as connection:
        connection.execute("create table audit_log (event_id text primary key)")

    observation = SqliteReadbackObserver().observe_row(
        database_path,
        table="audit_log;drop table audit_log",
        where={"event_id": "evt_db"},
    )

    assert observation.outcome == ObserverOutcome.UNAVAILABLE
    assert observation.as_payload()["observed_state"]["error_type"] == "OperationalError"
