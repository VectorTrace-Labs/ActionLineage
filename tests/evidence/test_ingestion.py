from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

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
)
from actionlineage.journal import LocalJournal

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
