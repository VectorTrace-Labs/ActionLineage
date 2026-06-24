"""Source-neutral evidence normalization boundaries."""

from actionlineage.evidence.ingestion import (
    BatchImportResult,
    DelegatedIdentity,
    EvidenceRecord,
    EvidenceSourceAdapter,
    EvidenceSourceKind,
    IngestOutcome,
    IngestOutcomeStatus,
    NormalizedAction,
    NormalizedResource,
    ObservationRecord,
    StaticEvidenceSourceAdapter,
    ToolIdentity,
    VerificationRecord,
    collect_records,
    import_evidence_batch,
    import_evidence_batch_atomically,
)
from actionlineage.evidence.normalization import EvidenceNormalizer

__all__ = [
    "BatchImportResult",
    "DelegatedIdentity",
    "EvidenceNormalizer",
    "EvidenceRecord",
    "EvidenceSourceAdapter",
    "EvidenceSourceKind",
    "IngestOutcome",
    "IngestOutcomeStatus",
    "NormalizedAction",
    "NormalizedResource",
    "ObservationRecord",
    "StaticEvidenceSourceAdapter",
    "ToolIdentity",
    "VerificationRecord",
    "collect_records",
    "import_evidence_batch",
    "import_evidence_batch_atomically",
]
