"""Source-neutral evidence ingestion models and batch import."""

from __future__ import annotations

import hashlib
from collections.abc import Iterable, Iterator, Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field, field_validator

from actionlineage.domain import (
    Classification,
    CorroborationType,
    EventEnvelope,
    EventType,
    EvidenceLink,
    EvidenceRelationship,
    Principal,
    ResourceType,
    Source,
    VerificationStatus,
    deterministic_json_bytes,
)
from actionlineage.domain.events import JsonObject, event_type_value, model_json, thaw_json_value
from actionlineage.errors import safe_error_detail
from actionlineage.evidence.normalization import EvidenceNormalizer
from actionlineage.journal import (
    JournalAppendError,
    JournalError,
    JournalReader,
    JournalStoragePermissionError,
    JournalWriter,
    LocalJournal,
    VerifiedJournalSnapshot,
)
from actionlineage.journal.hashing import prepare_event_for_append
from actionlineage.journal.local import (
    _append_line,
    _ensure_private_directory,
    _journal_lock,
    verified_journal_snapshot,
)

INGEST_RECORD_FINGERPRINT_VERSION = "actionlineage.dev/ingest-record-fingerprint-v1"
INGESTION_PROVENANCE_VERSION = "actionlineage.dev/ingestion-provenance-v1"


class EvidenceSourceKind(StrEnum):
    """Source categories that can feed the neutral ingestion boundary."""

    LOCAL_FUNCTION = "local_function"
    FILE = "file"
    HTTP = "http"
    MCP = "mcp"
    EXTERNAL_JSON = "external_json"
    FIXTURE = "fixture"
    UNKNOWN = "unknown"


class IngestOutcomeStatus(StrEnum):
    """Result of importing one source record."""

    IMPORTED = "imported"
    DUPLICATE = "duplicate"
    CONFLICT = "conflict"
    FAILED = "failed"


class FrozenIngestionModel(BaseModel):
    """Base model for immutable ingestion boundary objects."""

    model_config = ConfigDict(extra="forbid", frozen=True)


class ToolIdentity(FrozenIngestionModel):
    """Transport-neutral tool identity."""

    name: str = Field(min_length=1)
    descriptor_hash: str | None = Field(default=None, min_length=1)
    adapter: str | None = Field(default=None, min_length=1)
    version: str | None = Field(default=None, min_length=1)

    def as_payload(self) -> JsonObject:
        """Return a JSON-compatible payload fragment."""

        return self.model_dump(mode="json", exclude_none=True)


class DelegatedIdentity(FrozenIngestionModel):
    """Initiating, executing, and credential identity evidence."""

    initiating_principal_id: str = Field(min_length=1)
    executing_principal_id: str = Field(min_length=1)
    credential_id: str | None = Field(default=None, min_length=1)
    scopes: tuple[str, ...] = ()

    @field_validator("scopes")
    @classmethod
    def require_nonempty_scopes(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        """Reject empty scope strings."""

        if any(not scope for scope in value):
            raise ValueError("scopes cannot contain empty strings")
        return value

    def as_payload(self) -> JsonObject:
        """Return a JSON-compatible payload fragment."""

        return self.model_dump(mode="json", exclude_none=True)


class NormalizedResource(FrozenIngestionModel):
    """Normalized resource touched by an action or observation."""

    resource_type: ResourceType
    identifier: str = Field(min_length=1)
    attributes: JsonObject = Field(default_factory=dict)

    def as_payload(self) -> JsonObject:
        """Return a JSON-compatible payload fragment."""

        return self.model_dump(mode="json")


class NormalizedAction(FrozenIngestionModel):
    """Normalized action evidence independent of source transport."""

    action_type: str = Field(min_length=1)
    resources: tuple[NormalizedResource, ...] = ()
    tool_identity: ToolIdentity | None = None
    delegated_identity: DelegatedIdentity | None = None
    attributes: JsonObject = Field(default_factory=dict)

    def as_payload(self) -> JsonObject:
        """Return a JSON-compatible payload fragment."""

        return self.model_dump(mode="json", exclude_none=True)


class ObservationRecord(FrozenIngestionModel):
    """Source-neutral observation evidence."""

    observer_identity: str = Field(min_length=1)
    resource: NormalizedResource
    observed_state: JsonObject = Field(default_factory=dict)
    verification_status: VerificationStatus = VerificationStatus.OBSERVED
    limitations: tuple[str, ...] = ()

    def as_payload(self) -> JsonObject:
        """Return a JSON-compatible payload fragment."""

        return self.model_dump(mode="json")


class VerificationRecord(FrozenIngestionModel):
    """Source-neutral verification evidence."""

    evidence_link: EvidenceLink

    @classmethod
    def verified(
        cls,
        *,
        subject_event_id: str,
        evidence_event_id: str,
        observer_identity: str,
        confidence: float,
        limitations: tuple[str, ...],
        corroboration_type: CorroborationType = CorroborationType.UNKNOWN,
    ) -> VerificationRecord:
        """Build a verified evidence-link record."""

        return cls(
            evidence_link=EvidenceLink(
                subject_event_id=subject_event_id,
                relationship=EvidenceRelationship.CORROBORATES,
                evidence_event_id=evidence_event_id,
                corroboration_type=corroboration_type,
                observer_identity=observer_identity,
                confidence=confidence,
                verification_status=VerificationStatus.VERIFIED,
                limitations=limitations,
            )
        )

    def as_payload(self) -> JsonObject:
        """Return a JSON-compatible payload fragment."""

        return {"evidence_link": self.evidence_link.as_payload()}


class EvidenceRecord(FrozenIngestionModel):
    """One source-neutral record ready to normalize into an event."""

    idempotency_key: str = Field(min_length=1)
    event_type: EventType | str
    payload: JsonObject
    source_kind: EvidenceSourceKind = EvidenceSourceKind.UNKNOWN
    sort_key: str = Field(default="", min_length=0)
    source: Source | None = None
    principal: Principal | None = None
    classification: Classification | None = None

    @classmethod
    def from_action(
        cls,
        *,
        idempotency_key: str,
        action: NormalizedAction,
        source_kind: EvidenceSourceKind = EvidenceSourceKind.UNKNOWN,
        event_type: EventType | str = EventType.ACTION_NORMALIZED,
        sort_key: str = "",
    ) -> EvidenceRecord:
        """Create an evidence record from a normalized action."""

        return cls(
            idempotency_key=idempotency_key,
            event_type=event_type,
            payload={"action": action.as_payload()},
            source_kind=source_kind,
            sort_key=sort_key,
        )

    @classmethod
    def from_observation(
        cls,
        *,
        idempotency_key: str,
        observation: ObservationRecord,
        source_kind: EvidenceSourceKind = EvidenceSourceKind.UNKNOWN,
        event_type: EventType | str = EventType.SIDE_EFFECT_OBSERVED,
        sort_key: str = "",
    ) -> EvidenceRecord:
        """Create an evidence record from a normalized observation."""

        return cls(
            idempotency_key=idempotency_key,
            event_type=event_type,
            payload=observation.as_payload(),
            source_kind=source_kind,
            sort_key=sort_key,
        )

    @classmethod
    def from_verification(
        cls,
        *,
        idempotency_key: str,
        verification: VerificationRecord,
        source_kind: EvidenceSourceKind = EvidenceSourceKind.UNKNOWN,
        event_type: EventType | str = EventType.SIDE_EFFECT_VERIFIED,
        sort_key: str = "",
    ) -> EvidenceRecord:
        """Create an evidence record from a normalized verification."""

        return cls(
            idempotency_key=idempotency_key,
            event_type=event_type,
            payload=verification.as_payload(),
            source_kind=source_kind,
            sort_key=sort_key,
        )


class EvidenceSourceAdapter(Protocol):
    """Minimal protocol for source adapters that produce ingestion records."""

    def collect(self) -> Iterable[EvidenceRecord]:
        """Collect source-neutral evidence records."""


@dataclass(frozen=True, slots=True)
class IngestOutcome:
    """Result of importing one evidence record."""

    idempotency_key: str
    status: IngestOutcomeStatus
    event_id: str | None = None
    error: str | None = None

    def as_dict(self) -> dict[str, object]:
        """Return a JSON-compatible result object."""

        return {
            "idempotency_key": self.idempotency_key,
            "status": self.status.value,
            "event_id": self.event_id,
            "error": self.error,
        }


@dataclass(frozen=True, slots=True)
class BatchImportResult:
    """Summary of a source-neutral batch import."""

    outcomes: tuple[IngestOutcome, ...]

    @property
    def imported_count(self) -> int:
        """Number of records imported into the journal."""

        return self._count(IngestOutcomeStatus.IMPORTED)

    @property
    def duplicate_count(self) -> int:
        """Number of records skipped because idempotency keys already existed."""

        return self._count(IngestOutcomeStatus.DUPLICATE)

    @property
    def conflict_count(self) -> int:
        """Number of records rejected because an idempotency key was reused differently."""

        return self._count(IngestOutcomeStatus.CONFLICT)

    @property
    def failed_count(self) -> int:
        """Number of records that failed validation, normalization, or persistence."""

        return self._count(IngestOutcomeStatus.FAILED)

    @property
    def ok(self) -> bool:
        """Return true when the batch had no failed records."""

        return self.failed_count == 0 and self.conflict_count == 0

    def as_dict(self) -> dict[str, object]:
        """Return a JSON-compatible result object."""

        return {
            "ok": self.ok,
            "imported_count": self.imported_count,
            "duplicate_count": self.duplicate_count,
            "conflict_count": self.conflict_count,
            "failed_count": self.failed_count,
            "outcomes": [outcome.as_dict() for outcome in self.outcomes],
        }

    def _count(self, status: IngestOutcomeStatus) -> int:
        return sum(1 for outcome in self.outcomes if outcome.status == status)


def import_evidence_batch(
    records: Iterable[EvidenceRecord],
    *,
    normalizer: EvidenceNormalizer,
    journal: JournalWriter,
    existing_events: JournalReader | VerifiedJournalSnapshot | None = None,
) -> BatchImportResult:
    """Normalize and append a batch of source-neutral evidence records.

    Records are ordered deterministically by `sort_key` and `idempotency_key`.
    Duplicate idempotency keys are reported and skipped instead of creating
    duplicate canonical evidence.
    """

    seen_idempotency_entries = _existing_idempotency_entries(existing_events)
    outcomes: list[IngestOutcome] = []
    batch_seen: dict[str, _IdempotencyEntry] = {}

    for record in sorted(records, key=lambda item: (item.sort_key, item.idempotency_key)):
        record_fingerprint = _record_idempotency_fingerprint(record, normalizer)
        matched_entry = seen_idempotency_entries.get(record.idempotency_key) or batch_seen.get(
            record.idempotency_key
        )
        if matched_entry is not None:
            outcomes.append(_matched_idempotency_outcome(record, matched_entry, record_fingerprint))
            continue

        try:
            event = normalizer.record(
                record.event_type,
                _payload_with_ingest_metadata(record, record_fingerprint=record_fingerprint),
                source=record.source,
                principal=record.principal,
                classification=record.classification,
            )
            persisted = journal.append(event)
        except (JournalError, ValueError) as exc:
            outcomes.append(
                IngestOutcome(
                    idempotency_key=record.idempotency_key,
                    status=IngestOutcomeStatus.FAILED,
                    error=_safe_error_message(exc),
                )
            )
            continue

        batch_seen[record.idempotency_key] = _IdempotencyEntry(
            event_id=persisted.event_id,
            record_fingerprint=record_fingerprint,
        )
        outcomes.append(
            IngestOutcome(
                idempotency_key=record.idempotency_key,
                status=IngestOutcomeStatus.IMPORTED,
                event_id=persisted.event_id,
            )
        )

    return BatchImportResult(outcomes=tuple(outcomes))


def import_evidence_batch_atomically(
    records: Iterable[EvidenceRecord],
    *,
    normalizer: EvidenceNormalizer,
    journal: LocalJournal,
) -> BatchImportResult:
    """Import a batch while holding the local journal append lock.

    The verified snapshot, idempotency scan, sequence assignment, and append are
    performed under one exclusive journal lock so concurrent service requests
    observe deterministic duplicate or conflict outcomes instead of stale
    sequence failures.
    """

    ordered_records = tuple(sorted(records, key=lambda item: (item.sort_key, item.idempotency_key)))
    try:
        _ensure_private_directory(journal.path.parent)
    except OSError as exc:
        raise JournalAppendError("failed to prepare journal directory") from exc
    except JournalStoragePermissionError as exc:
        raise JournalAppendError(safe_error_detail(exc)) from exc

    outcomes: list[IngestOutcome] = []
    with _journal_lock(
        journal.path.with_suffix(f"{journal.path.suffix}.lock"),
        mode="exclusive",
        operation="batch-import",
        timeout_seconds=journal.lock_timeout_seconds,
        poll_seconds=journal.lock_poll_seconds,
    ):
        try:
            snapshot = verified_journal_snapshot(journal.path, lock=False)
        except OSError as exc:
            raise JournalAppendError("failed to verify existing journal before append") from exc
        if not snapshot.ok:
            raise JournalAppendError("cannot append to a journal that fails verification")

        normalizer.rebase_initial_sequence(snapshot.record_count)
        seen_entries = _existing_idempotency_entries(snapshot)
        batch_seen: dict[str, _IdempotencyEntry] = {}
        next_sequence = snapshot.record_count
        previous_event_hash = snapshot.terminal_hash

        for record in ordered_records:
            record_fingerprint = _record_idempotency_fingerprint(record, normalizer)
            matched_entry = seen_entries.get(record.idempotency_key) or batch_seen.get(
                record.idempotency_key
            )
            if matched_entry is not None:
                outcomes.append(
                    _matched_idempotency_outcome(record, matched_entry, record_fingerprint)
                )
                continue

            try:
                event = normalizer.record(
                    record.event_type,
                    _payload_with_ingest_metadata(record, record_fingerprint=record_fingerprint),
                    source=record.source,
                    principal=record.principal,
                    classification=record.classification,
                )
                if event.causality.sequence != next_sequence:
                    raise JournalAppendError(
                        f"event sequence {event.causality.sequence} does not match next journal "
                        f"sequence {next_sequence}"
                    )
                persisted = _append_event_inside_lock(
                    journal,
                    event,
                    previous_event_hash=previous_event_hash,
                )
            except JournalError as exc:
                if not batch_seen:
                    raise
                outcomes.append(
                    IngestOutcome(
                        idempotency_key=record.idempotency_key,
                        status=IngestOutcomeStatus.FAILED,
                        error=_safe_error_message(exc),
                    )
                )
                break
            except ValueError as exc:
                outcomes.append(
                    IngestOutcome(
                        idempotency_key=record.idempotency_key,
                        status=IngestOutcomeStatus.FAILED,
                        error=_safe_error_message(exc),
                    )
                )
                continue

            next_sequence += 1
            previous_event_hash = persisted.integrity.event_hash
            batch_seen[record.idempotency_key] = _IdempotencyEntry(
                event_id=persisted.event_id,
                record_fingerprint=record_fingerprint,
            )
            outcomes.append(
                IngestOutcome(
                    idempotency_key=record.idempotency_key,
                    status=IngestOutcomeStatus.IMPORTED,
                    event_id=persisted.event_id,
                )
            )

    return BatchImportResult(outcomes=tuple(outcomes))


def collect_records(adapters: Iterable[EvidenceSourceAdapter]) -> tuple[EvidenceRecord, ...]:
    """Collect records from source adapters in adapter order."""

    collected: list[EvidenceRecord] = []
    for adapter in adapters:
        collected.extend(adapter.collect())
    return tuple(collected)


@dataclass(frozen=True, slots=True)
class _IdempotencyEntry:
    event_id: str
    record_fingerprint: str | None


def _payload_with_ingest_metadata(
    record: EvidenceRecord,
    *,
    record_fingerprint: str,
) -> JsonObject:
    payload = dict(record.payload)
    payload["ingest"] = {
        "fingerprint_version": INGEST_RECORD_FINGERPRINT_VERSION,
        "idempotency_key": record.idempotency_key,
        "record_fingerprint": record_fingerprint,
        "source_kind": record.source_kind.value,
    }
    return payload


def _existing_idempotency_entries(
    existing_events: JournalReader | VerifiedJournalSnapshot | None,
) -> dict[str, _IdempotencyEntry]:
    if existing_events is None:
        return {}
    snapshot = (
        existing_events
        if isinstance(existing_events, VerifiedJournalSnapshot)
        else existing_events.verified_snapshot()
    )
    if not snapshot.ok:
        raise JournalError("cannot scan idempotency keys from an unverified journal")

    idempotency_entries: dict[str, _IdempotencyEntry] = {}
    for event in snapshot.events:
        ingest = event.payload.get("ingest")
        key = _event_idempotency_key_from_ingest(ingest)
        if key is not None:
            idempotency_entries[key] = _IdempotencyEntry(
                event_id=event.event_id,
                record_fingerprint=_event_idempotency_fingerprint_from_ingest(ingest),
            )
    return idempotency_entries


def _event_idempotency_key(event: EventEnvelope) -> str | None:
    return _event_idempotency_key_from_ingest(event.payload.get("ingest"))


def _event_idempotency_key_from_ingest(ingest: object) -> str | None:
    if not isinstance(ingest, Mapping):
        return None
    key = ingest.get("idempotency_key")
    if isinstance(key, str) and key:
        return key
    return None


def _event_idempotency_fingerprint_from_ingest(ingest: object) -> str | None:
    if not isinstance(ingest, Mapping):
        return None
    fingerprint = ingest.get("record_fingerprint")
    if isinstance(fingerprint, str) and fingerprint:
        return fingerprint
    return None


def _matched_idempotency_outcome(
    record: EvidenceRecord,
    entry: _IdempotencyEntry,
    record_fingerprint: str,
) -> IngestOutcome:
    if entry.record_fingerprint is None or entry.record_fingerprint == record_fingerprint:
        return IngestOutcome(
            idempotency_key=record.idempotency_key,
            status=IngestOutcomeStatus.DUPLICATE,
            event_id=entry.event_id,
        )
    return IngestOutcome(
        idempotency_key=record.idempotency_key,
        status=IngestOutcomeStatus.CONFLICT,
        event_id=entry.event_id,
        error="idempotency key already used for different evidence record",
    )


def _record_idempotency_fingerprint(
    record: EvidenceRecord,
    normalizer: EvidenceNormalizer,
) -> str:
    payload: JsonObject = thaw_json_value(record.payload)
    if _is_service_ingestion_provenance(payload.get("ingested_by")):
        payload.pop("ingested_by", None)
    payload.pop("ingest", None)
    preimage: JsonObject = {
        "classification": model_json(record.classification or normalizer.classification),
        "correlation": model_json(normalizer.correlation),
        "event_type": event_type_value(record.event_type),
        "idempotency_key": record.idempotency_key,
        "payload": payload,
        "principal": model_json(record.principal or normalizer.principal),
        "sort_key": record.sort_key,
        "source": model_json(record.source or normalizer.source),
        "source_kind": record.source_kind.value,
        "version": INGEST_RECORD_FINGERPRINT_VERSION,
    }
    digest = hashlib.sha256(deterministic_json_bytes(preimage)).hexdigest()
    return f"sha256:{digest}"


def _is_service_ingestion_provenance(value: object) -> bool:
    return (
        isinstance(value, Mapping) and value.get("schema_version") == INGESTION_PROVENANCE_VERSION
    )


def _append_event_inside_lock(
    journal: LocalJournal,
    event: EventEnvelope,
    *,
    previous_event_hash: str | None,
) -> EventEnvelope:
    redacted_event, canonical_bytes = prepare_event_for_append(
        event,
        previous_event_hash=previous_event_hash,
        redaction_policy=journal.redaction_policy,
    )
    try:
        _append_line(journal.path, canonical_bytes)
    except OSError as exc:
        raise JournalAppendError("failed to append event to journal") from exc
    return redacted_event


def _safe_error_message(exc: Exception) -> str:
    if isinstance(exc, JournalError):
        return type(exc).__name__
    return "evidence record could not be imported"


class StaticEvidenceSourceAdapter:
    """Simple adapter for already-collected source-neutral records."""

    def __init__(self, records: Iterable[EvidenceRecord]) -> None:
        self._records = tuple(records)

    def collect(self) -> Iterator[EvidenceRecord]:
        """Yield configured records."""

        yield from self._records
