from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

import actionlineage.evidence.ingestion as ingestion_module
from actionlineage.domain import (
    Classification,
    Correlation,
    EventType,
    FixedClock,
    FixedIdGenerator,
    Principal,
    PrincipalType,
    RedactionPolicy,
    ResourceType,
    Sensitivity,
    Source,
    TrustLevel,
)
from actionlineage.evidence import (
    EvidenceNormalizer,
    EvidenceRecord,
    EvidenceSourceKind,
    IngestOutcomeStatus,
    NormalizedAction,
    NormalizedResource,
    StaticEvidenceSourceAdapter,
    ToolIdentity,
    collect_records,
    import_evidence_batch,
    import_evidence_batch_atomically,
)
from actionlineage.journal import JournalAppendError, JournalStoragePermissionError, LocalJournal

BASE_TIME = datetime(2026, 6, 21, 18, 42, 12, tzinfo=UTC)


def make_normalizer() -> EvidenceNormalizer:
    return EvidenceNormalizer(
        correlation=Correlation(trace_id="trace_ingest", run_id="run_ingest"),
        source=Source(component="ingest-test", instance_id="test_01", version="1.0.0"),
        principal=Principal(
            principal_id="agent_ingest",
            principal_type=PrincipalType.AGENT,
            on_behalf_of="user_ingest",
        ),
        classification=Classification(sensitivity=Sensitivity.INTERNAL, trust=TrustLevel.LOCAL),
        clock=FixedClock(BASE_TIME),
        id_generator=FixedIdGenerator(("evt_root", "evt_a", "evt_b", "evt_c")),
    )


def root_record() -> EvidenceRecord:
    return EvidenceRecord(
        idempotency_key="000-root",
        event_type=EventType.AGENT_INTENT_RECORDED,
        payload={"intent": "ingest source-neutral evidence"},
        source_kind=EvidenceSourceKind.EXTERNAL_JSON,
        sort_key="000",
    )


def action_record(idempotency_key: str, sort_key: str, path: str) -> EvidenceRecord:
    action = NormalizedAction(
        action_type="file.read",
        resources=(
            NormalizedResource(
                resource_type=ResourceType.FILE,
                identifier=path,
                attributes={"sensitivity": "restricted"},
            ),
        ),
        tool_identity=ToolIdentity(name="local.read_file", descriptor_hash="sha256:read"),
        attributes={"mode": "read"},
    )
    return EvidenceRecord.from_action(
        idempotency_key=idempotency_key,
        action=action,
        source_kind=EvidenceSourceKind.FILE,
        sort_key=sort_key,
    )


def test_batch_import_orders_records_and_writes_ingest_metadata(tmp_path: Path) -> None:
    journal = LocalJournal(tmp_path / "events.jsonl")
    records = (
        action_record("020-action-b", "020", "docs/b.txt"),
        root_record(),
        action_record("010-action-a", "010", "docs/a.txt"),
    )

    result = import_evidence_batch(records, normalizer=make_normalizer(), journal=journal)
    events = list(journal.iter_events())

    assert result.ok
    assert result.imported_count == 3
    assert [event.event_id for event in events] == ["evt_root", "evt_a", "evt_b"]
    assert [event.payload["ingest"]["idempotency_key"] for event in events] == [
        "000-root",
        "010-action-a",
        "020-action-b",
    ]
    assert events[1].payload["action"]["tool_identity"]["descriptor_hash"] == "sha256:read"


def test_batch_import_is_idempotent_against_existing_journal(tmp_path: Path) -> None:
    journal = LocalJournal(tmp_path / "events.jsonl")
    records = (root_record(), action_record("010-action-a", "010", "docs/a.txt"))

    first = import_evidence_batch(records, normalizer=make_normalizer(), journal=journal)
    second = import_evidence_batch(
        records,
        normalizer=make_normalizer(),
        journal=journal,
        existing_events=journal,
    )

    assert first.imported_count == 2
    assert second.imported_count == 0
    assert second.duplicate_count == 2
    assert {outcome.status for outcome in second.outcomes} == {IngestOutcomeStatus.DUPLICATE}
    assert journal.verify().records_verified == 2


def test_batch_import_reports_duplicate_within_same_batch(tmp_path: Path) -> None:
    journal = LocalJournal(tmp_path / "events.jsonl")
    duplicate = action_record("010-action-a", "010", "docs/a.txt")

    result = import_evidence_batch(
        (root_record(), duplicate, duplicate),
        normalizer=make_normalizer(),
        journal=journal,
    )

    assert result.imported_count == 2
    assert result.duplicate_count == 1
    assert result.outcomes[-1].status == IngestOutcomeStatus.DUPLICATE


def test_batch_import_reports_conflicting_idempotency_key(tmp_path: Path) -> None:
    journal = LocalJournal(tmp_path / "events.jsonl")
    original = action_record("010-action-a", "010", "docs/a.txt")
    changed = action_record("010-action-a", "010", "docs/changed.txt")

    first = import_evidence_batch(
        (root_record(), original), normalizer=make_normalizer(), journal=journal
    )
    second = import_evidence_batch(
        (changed,),
        normalizer=make_normalizer(),
        journal=journal,
        existing_events=journal,
    )

    assert first.imported_count == 2
    assert second.imported_count == 0
    assert second.conflict_count == 1
    assert second.ok is False
    assert second.outcomes[0].status == IngestOutcomeStatus.CONFLICT
    assert second.outcomes[0].event_id == "evt_a"
    assert journal.verify().records_verified == 2


def test_batch_import_treats_non_service_ingested_by_as_payload_for_conflicts(
    tmp_path: Path,
) -> None:
    journal = LocalJournal(tmp_path / "events.jsonl")
    original = EvidenceRecord(
        idempotency_key="000-custom-provenance",
        event_type=EventType.AGENT_INTENT_RECORDED,
        payload={"ingested_by": {"custom": "first"}},
        source_kind=EvidenceSourceKind.EXTERNAL_JSON,
        sort_key="000",
    )
    changed = EvidenceRecord(
        idempotency_key="000-custom-provenance",
        event_type=EventType.AGENT_INTENT_RECORDED,
        payload={"ingested_by": {"custom": "second"}},
        source_kind=EvidenceSourceKind.EXTERNAL_JSON,
        sort_key="000",
    )

    first = import_evidence_batch((original,), normalizer=make_normalizer(), journal=journal)
    second = import_evidence_batch(
        (changed,),
        normalizer=make_normalizer(),
        journal=journal,
        existing_events=journal,
    )

    assert first.imported_count == 1
    assert second.conflict_count == 1
    assert second.outcomes[0].status == IngestOutcomeStatus.CONFLICT


def test_atomic_batch_import_assigns_sequence_from_locked_journal_snapshot(
    tmp_path: Path,
) -> None:
    journal = LocalJournal(tmp_path / "events.jsonl")
    import_evidence_batch((root_record(),), normalizer=make_normalizer(), journal=journal)

    result = import_evidence_batch_atomically(
        (
            EvidenceRecord(
                idempotency_key="100-root-2",
                event_type=EventType.AGENT_INTENT_RECORDED,
                payload={"intent": "second imported root"},
                source_kind=EvidenceSourceKind.EXTERNAL_JSON,
                sort_key="100",
            ),
        ),
        normalizer=make_normalizer(),
        journal=journal,
    )
    snapshot = journal.verified_snapshot()

    assert result.imported_count == 1
    assert snapshot.events[-1].causality.sequence == 1
    assert snapshot.events[-1].payload["ingest"]["idempotency_key"] == "100-root-2"


def test_atomic_batch_import_reports_partial_commit_on_later_append_failure(
    monkeypatch,
    tmp_path: Path,
) -> None:
    journal = LocalJournal(tmp_path / "events.jsonl")
    original_append = ingestion_module._append_line
    append_attempts = 0

    def fail_second_append(path: Path, data: bytes) -> None:
        nonlocal append_attempts
        append_attempts += 1
        if append_attempts == 2:
            raise OSError("simulated disk full containing raw detail")
        original_append(path, data)

    monkeypatch.setattr(ingestion_module, "_append_line", fail_second_append)

    result = import_evidence_batch_atomically(
        (
            root_record(),
            EvidenceRecord(
                idempotency_key="100-root-2",
                event_type=EventType.AGENT_INTENT_RECORDED,
                payload={"intent": "second imported root"},
                source_kind=EvidenceSourceKind.EXTERNAL_JSON,
                sort_key="100",
            ),
        ),
        normalizer=make_normalizer(),
        journal=journal,
    )
    snapshot = journal.verified_snapshot()

    assert result.imported_count == 1
    assert result.failed_count == 1
    assert result.outcomes[0].status == IngestOutcomeStatus.IMPORTED
    assert result.outcomes[1].status == IngestOutcomeStatus.FAILED
    assert result.outcomes[1].error == "JournalAppendError"
    assert "simulated disk full" not in str(result.as_dict())
    assert snapshot.ok
    assert snapshot.record_count == 1


def test_atomic_batch_import_directory_permission_failure_redacts_exception_detail(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    journal = LocalJournal(tmp_path / "events.jsonl")
    raw_secret = "batchpermissionsecretvalue123456789"

    def fail_directory_check(_path: Path) -> None:
        raise JournalStoragePermissionError(f"batch path rejected for Bearer {raw_secret}")

    monkeypatch.setattr(ingestion_module, "_ensure_private_directory", fail_directory_check)

    with pytest.raises(JournalAppendError) as error:
        import_evidence_batch_atomically(
            (root_record(),),
            normalizer=make_normalizer(),
            journal=journal,
        )

    message = str(error.value)
    assert raw_secret not in message
    assert "Bearer [REDACTED:bearer_token]" in message


def test_batch_import_redacts_before_persistence(tmp_path: Path) -> None:
    raw_secret = "source-neutral-secret-value"
    journal = LocalJournal(
        tmp_path / "events.jsonl",
        redaction_policy=RedactionPolicy.from_paths(("payload.action.attributes.client_secret",)),
    )
    action = NormalizedAction(
        action_type="http.send",
        attributes={"client_secret": raw_secret, "destination": "local-fixture"},
    )
    records = (
        root_record(),
        EvidenceRecord.from_action(
            idempotency_key="010-send",
            action=action,
            source_kind=EvidenceSourceKind.HTTP,
            sort_key="010",
        ),
    )

    result = import_evidence_batch(records, normalizer=make_normalizer(), journal=journal)

    assert result.ok
    assert raw_secret not in journal.path.read_text(encoding="utf-8")
    assert journal.verify().ok


def test_static_adapter_collects_source_neutral_records() -> None:
    records = (root_record(), action_record("010-action-a", "010", "docs/a.txt"))
    adapter = StaticEvidenceSourceAdapter(records)

    assert collect_records((adapter,)) == records
