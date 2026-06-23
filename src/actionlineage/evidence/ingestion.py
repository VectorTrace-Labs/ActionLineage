"""Source-neutral evidence ingestion models and batch import."""

from __future__ import annotations

from collections.abc import Iterable, Iterator
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
)
from actionlineage.domain.events import JsonObject
from actionlineage.evidence.normalization import EvidenceNormalizer
from actionlineage.journal import (
    JournalError,
    JournalReader,
    JournalWriter,
    VerifiedJournalSnapshot,
)


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
    ) -> VerificationRecord:
        """Build a verified evidence-link record."""

        return cls(
            evidence_link=EvidenceLink(
                subject_event_id=subject_event_id,
                relationship=EvidenceRelationship.CORROBORATES,
                evidence_event_id=evidence_event_id,
                corroboration_type=CorroborationType.INDEPENDENT_OBSERVER,
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
    def failed_count(self) -> int:
        """Number of records that failed validation, normalization, or persistence."""

        return self._count(IngestOutcomeStatus.FAILED)

    @property
    def ok(self) -> bool:
        """Return true when the batch had no failed records."""

        return self.failed_count == 0

    def as_dict(self) -> dict[str, object]:
        """Return a JSON-compatible result object."""

        return {
            "ok": self.ok,
            "imported_count": self.imported_count,
            "duplicate_count": self.duplicate_count,
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

    seen_idempotency_keys = _existing_idempotency_keys(existing_events)
    outcomes: list[IngestOutcome] = []
    batch_seen: set[str] = set()

    for record in sorted(records, key=lambda item: (item.sort_key, item.idempotency_key)):
        if record.idempotency_key in seen_idempotency_keys or record.idempotency_key in batch_seen:
            outcomes.append(
                IngestOutcome(
                    idempotency_key=record.idempotency_key,
                    status=IngestOutcomeStatus.DUPLICATE,
                )
            )
            continue

        try:
            event = normalizer.record(
                record.event_type,
                _payload_with_ingest_metadata(record),
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

        batch_seen.add(record.idempotency_key)
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


def _payload_with_ingest_metadata(record: EvidenceRecord) -> JsonObject:
    payload = dict(record.payload)
    payload["ingest"] = {
        "idempotency_key": record.idempotency_key,
        "source_kind": record.source_kind.value,
    }
    return payload


def _existing_idempotency_keys(
    existing_events: JournalReader | VerifiedJournalSnapshot | None,
) -> set[str]:
    if existing_events is None:
        return set()
    snapshot = (
        existing_events
        if isinstance(existing_events, VerifiedJournalSnapshot)
        else existing_events.verified_snapshot()
    )
    if not snapshot.ok:
        raise JournalError("cannot scan idempotency keys from an unverified journal")

    idempotency_keys: set[str] = set()
    for event in snapshot.events:
        key = _event_idempotency_key(event)
        if key is not None:
            idempotency_keys.add(key)
    return idempotency_keys


def _event_idempotency_key(event: EventEnvelope) -> str | None:
    ingest = event.payload.get("ingest")
    if not isinstance(ingest, dict):
        return None
    key = ingest.get("idempotency_key")
    if isinstance(key, str) and key:
        return key
    return None


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
