"""Optional FastAPI service factory."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from pydantic import ValidationError

from actionlineage.contracts import contract_from_dict, validate_contract
from actionlineage.detection import DetectionMatch, built_in_sequence_rules, evaluate_sequence_rule
from actionlineage.domain import (
    Classification,
    Correlation,
    EventEnvelope,
    PrefixedUuidGenerator,
    Principal,
    PrincipalType,
    Sensitivity,
    Source,
    SystemClock,
    TrustLevel,
)
from actionlineage.errors import ActionLineageValidationError
from actionlineage.evidence import (
    BatchImportResult,
    EvidenceNormalizer,
    EvidenceRecord,
    import_evidence_batch_atomically,
)
from actionlineage.journal import JournalError, LocalJournal, VerifiedJournalSnapshot
from actionlineage.projection import (
    ProjectionError,
    export_case_bundle,
    query_timeline,
    rebuild_projection,
)
from actionlineage.service.auth import (
    ServiceAuthError,
    ServiceCapability,
    ServicePrincipal,
    StaticTokenAuthenticator,
    require_capability,
)
from actionlineage.service.health import check_local_health


class ServiceDependencyError(RuntimeError):
    """Raised when optional service dependencies are unavailable."""


def create_app(
    *,
    journal_path: Path,
    database_path: Path,
    authenticator: StaticTokenAuthenticator,
    export_root: Path | None = None,
    service_instance_id: str = "local_service",
) -> Any:
    """Create the optional FastAPI service application."""

    try:
        from fastapi import Depends, FastAPI, Header, HTTPException
        from fastapi.responses import JSONResponse
    except ImportError as exc:
        raise ServiceDependencyError("install actionlineage[service] to use service mode") from exc

    app = FastAPI(title="ActionLineage Evidence Service")
    service_export_root = (
        Path(export_root) if export_root is not None else Path(database_path).parent / "exports"
    )

    def principal(authorization: str | None = Header(default=None)) -> Any:
        token = authorization.removeprefix("Bearer ").strip() if authorization else None
        try:
            return authenticator.authenticate(token)
        except ServiceAuthError as exc:
            raise HTTPException(status_code=401, detail=str(exc)) from exc

    principal_dependency = Depends(principal)

    @app.get("/live")
    def live() -> dict[str, object]:
        return {"ok": True, "state": "live"}

    @app.get("/ready")
    def ready() -> Any:
        report = check_local_health(journal_path=journal_path, database_path=database_path)
        return JSONResponse(status_code=200 if report.ok else 503, content=report.as_dict())

    @app.get("/health")
    def health() -> Any:
        report = check_local_health(journal_path=journal_path, database_path=database_path)
        return JSONResponse(status_code=200 if report.ok else 503, content=report.as_dict())

    @app.get("/timeline")
    def timeline(
        trace_id: str | None = None,
        run_id: str | None = None,
        service_principal: Any = principal_dependency,
    ) -> dict[str, object]:
        try:
            require_capability(service_principal, ServiceCapability.EVENTS_READ)
        except ServiceAuthError as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc
        try:
            return query_timeline(
                database_path,
                journal_path=journal_path,
                trace_id=trace_id,
                run_id=run_id,
            ).as_dict()
        except ProjectionError as exc:
            raise HTTPException(status_code=503, detail=_safe_detail(exc)) from exc

    @app.get("/events")
    def events(service_principal: Any = principal_dependency) -> dict[str, object]:
        try:
            require_capability(service_principal, ServiceCapability.EVENTS_READ)
        except ServiceAuthError as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc
        snapshot = _verified_snapshot_or_503(journal_path)
        return {
            "ok": True,
            "events": [
                {
                    "event_id": event.event_id,
                    "ingestion_provenance": (
                        "service_authenticated"
                        if isinstance(event.payload.get("ingested_by"), Mapping)
                        else "legacy_no_ingested_by"
                    ),
                }
                for event in snapshot.events
            ],
            "verification": snapshot.verification.as_dict(),
        }

    @app.post("/export-case")
    def export_case(
        output_dir: str,
        trace_id: str | None = None,
        run_id: str | None = None,
        service_principal: Any = principal_dependency,
    ) -> dict[str, object]:
        try:
            require_capability(service_principal, ServiceCapability.CASES_EXPORT)
        except ServiceAuthError as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc
        try:
            return export_case_bundle(
                database_path,
                _service_export_dir(service_export_root, output_dir),
                journal_path=journal_path,
                trace_id=trace_id,
                run_id=run_id,
            ).as_dict()
        except (ProjectionError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=_safe_detail(exc)) from exc

    @app.post("/ingest")
    def ingest(
        body: dict[str, Any],
        x_request_id: str | None = Header(default=None, alias="X-Request-ID"),
        service_principal: Any = principal_dependency,
    ) -> Any:
        try:
            require_capability(service_principal, ServiceCapability.EVENTS_WRITE)
            require_capability(service_principal, ServiceCapability.PROJECTIONS_REBUILD)
            journal = LocalJournal(journal_path)
            _reject_client_ingested_by(body)
            _reject_unprivileged_trusted_classification(body, _typed_principal(service_principal))
            ingested_by = _ingested_by(
                _typed_principal(service_principal),
                request_id=x_request_id,
                service_instance_id=service_instance_id,
            )
            normalizer = _normalizer_from_request(
                body,
                service_principal=_typed_principal(service_principal),
                initial_sequence=0,
            )
            records = _evidence_records_from_request(body, ingested_by=ingested_by)
            result = import_evidence_batch_atomically(
                records,
                normalizer=normalizer,
                journal=journal,
            )
            if result.imported_count or result.duplicate_count:
                try:
                    rebuild_projection(journal_path, database_path)
                except ProjectionError as exc:
                    return JSONResponse(
                        status_code=503,
                        content=_ingest_response_body(
                            result,
                            projection_state="stale",
                            projection_error=_safe_detail(exc),
                        ),
                    )
        except ServiceAuthError as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc
        except JournalError as exc:
            raise HTTPException(status_code=503, detail=_integrity_detail_from_error(exc)) from exc
        except (ActionLineageValidationError, ValidationError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=_safe_detail(exc)) from exc
        return JSONResponse(
            status_code=_ingest_status_code(result),
            content=_ingest_response_body(result, projection_state="rebuilt"),
        )

    @app.post("/contracts/validate")
    def validate_contract_endpoint(
        body: dict[str, Any],
        service_principal: Any = principal_dependency,
    ) -> dict[str, object]:
        try:
            require_capability(service_principal, ServiceCapability.EVENTS_READ)
            contract = contract_from_dict(_object_body_field(body, "contract"))
            snapshot = _verified_snapshot_or_503(journal_path)
            detection_results = _built_in_detection_results(snapshot.events)
            return validate_contract(
                snapshot.events,
                contract,
                detection_results=detection_results,
                journal_verification=snapshot.verification,
            ).as_dict()
        except ServiceAuthError as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc
        except (ActionLineageValidationError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=_safe_detail(exc)) from exc

    @app.post("/detections/evaluate")
    def detections_evaluate(
        body: dict[str, Any] | None = None,
        service_principal: Any = principal_dependency,
    ) -> dict[str, object]:
        try:
            require_capability(service_principal, ServiceCapability.DETECTIONS_RUN)
            requested_rule_ids = _requested_rule_ids(body or {})
        except ServiceAuthError as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=_safe_detail(exc)) from exc

        snapshot = _verified_snapshot_or_503(journal_path)
        matches: list[dict[str, object]] = []
        rules_evaluated: list[str] = []
        for rule in built_in_sequence_rules():
            if requested_rule_ids and rule.rule_id not in requested_rule_ids:
                continue
            rules_evaluated.append(rule.rule_id or rule.name)
            matches.extend(
                match.as_dict() for match in evaluate_sequence_rule(snapshot.events, rule)
            )
        return {
            "ok": True,
            "rules_evaluated": rules_evaluated,
            "match_count": len(matches),
            "matches": matches,
        }

    return app


def _verified_snapshot_or_503(journal_path: Path) -> VerifiedJournalSnapshot:
    try:
        snapshot = LocalJournal(journal_path).verified_snapshot()
    except JournalError as exc:
        from fastapi import HTTPException

        raise HTTPException(status_code=503, detail=_integrity_detail_from_error(exc)) from exc
    if snapshot.ok:
        return snapshot
    from fastapi import HTTPException

    raise HTTPException(
        status_code=503,
        detail={
            "error": "journal_integrity_error",
            "verification": snapshot.verification.as_dict(),
        },
    )


def _normalizer_from_request(
    body: dict[str, Any],
    *,
    service_principal: ServicePrincipal,
    initial_sequence: int,
) -> EvidenceNormalizer:
    correlation = Correlation.model_validate(_object_body_field(body, "correlation"))
    source_data = body.get("source")
    source = (
        Source.model_validate(source_data)
        if isinstance(source_data, dict)
        else Source(component="service_api", instance_id="local_service", version="1.0.0")
    )
    principal_data = body.get("principal")
    principal = (
        Principal.model_validate(principal_data)
        if isinstance(principal_data, dict)
        else Principal(
            principal_id=service_principal.principal_id,
            principal_type=PrincipalType.SERVICE,
        )
    )
    classification_data = body.get("classification")
    classification = (
        Classification.model_validate(classification_data)
        if isinstance(classification_data, dict)
        else Classification(sensitivity=Sensitivity.INTERNAL, trust=TrustLevel.UNKNOWN)
    )
    return EvidenceNormalizer(
        correlation=correlation,
        source=source,
        principal=principal,
        classification=classification,
        clock=SystemClock(),
        id_generator=PrefixedUuidGenerator(),
        initial_sequence=initial_sequence,
    )


def _evidence_records_from_request(
    body: dict[str, Any],
    *,
    ingested_by: dict[str, object],
) -> tuple[EvidenceRecord, ...]:
    records = body.get("records")
    if not isinstance(records, list):
        raise ValueError("request body must include records array")
    prepared: list[EvidenceRecord] = []
    for record in records:
        if not isinstance(record, dict):
            raise ValueError("records must contain objects")
        payload = record.get("payload")
        if not isinstance(payload, dict):
            raise ValueError("record payload must be an object")
        prepared.append(
            EvidenceRecord.model_validate(
                {
                    **record,
                    "payload": {
                        **payload,
                        "ingested_by": ingested_by,
                    },
                }
            )
        )
    return tuple(prepared)


def _object_body_field(body: dict[str, Any], field: str) -> dict[str, Any]:
    value = body.get(field)
    if not isinstance(value, dict):
        raise ValueError(f"request body must include {field} object")
    return value


def _built_in_detection_results(events: tuple[EventEnvelope, ...]) -> tuple[DetectionMatch, ...]:
    matches: list[DetectionMatch] = []
    for rule in built_in_sequence_rules():
        matches.extend(evaluate_sequence_rule(events, rule))
    return tuple(matches)


def _requested_rule_ids(body: dict[str, Any]) -> frozenset[str]:
    rule_ids = body.get("rule_ids")
    if rule_ids is None:
        return frozenset()
    if not isinstance(rule_ids, list) or not all(isinstance(rule_id, str) for rule_id in rule_ids):
        raise ValueError("rule_ids must be an array of strings")
    return frozenset(rule_ids)


def _typed_principal(value: Any) -> ServicePrincipal:
    if not isinstance(value, ServicePrincipal):
        raise ServiceAuthError("invalid service principal")
    return value


def _reject_client_ingested_by(body: dict[str, Any]) -> None:
    if "ingested_by" in body:
        raise ValueError("ingested_by is server-controlled and must not be supplied")
    records = body.get("records")
    if not isinstance(records, list):
        return
    for record in records:
        if isinstance(record, dict):
            if "ingested_by" in record:
                raise ValueError("ingested_by is server-controlled and must not be supplied")
            payload = record.get("payload")
            if isinstance(payload, dict) and "ingested_by" in payload:
                raise ValueError("ingested_by is server-controlled and must not be supplied")


def _reject_unprivileged_trusted_classification(
    body: dict[str, Any],
    service_principal: ServicePrincipal,
) -> None:
    if service_principal.has_capability(ServiceCapability.ADMIN_CONFIGURE):
        return

    if _classification_is_trusted(body.get("classification")):
        raise ServiceAuthError("admin role required to assert trusted evidence")
    records = body.get("records")
    if not isinstance(records, list):
        return
    for record in records:
        if isinstance(record, dict) and _classification_is_trusted(record.get("classification")):
            raise ServiceAuthError("admin role required to assert trusted evidence")


def _classification_is_trusted(value: object) -> bool:
    return isinstance(value, dict) and value.get("trust") == TrustLevel.TRUSTED.value


def _ingested_by(
    service_principal: ServicePrincipal,
    *,
    request_id: str | None,
    service_instance_id: str,
) -> dict[str, object]:
    return {
        "schema_version": "actionlineage.dev/ingestion-provenance-v1",
        "authenticated_principal": service_principal.principal_id,
        "authenticated_roles": sorted(role.value for role in service_principal.roles),
        "authentication_method": "bearer",
        "credential_identifier": f"principal:{service_principal.principal_id}",
        "request_id": request_id or f"req_{uuid4().hex}",
        "received_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "service_instance_id": service_instance_id,
        "legacy": False,
    }


def _integrity_detail_from_error(exc: JournalError) -> dict[str, object]:
    return {
        "error": "journal_integrity_error",
        "message": "internal journal could not be safely consumed",
        "error_type": type(exc).__name__,
    }


def _safe_detail(exc: Exception) -> str:
    if isinstance(exc, ValidationError):
        return "service request validation failed"
    return str(exc)


def _ingest_status_code(result: BatchImportResult) -> int:
    if result.imported_count and not result.ok:
        return 207
    if result.conflict_count:
        return 409
    if result.failed_count:
        return 400
    return 200


def _ingest_response_body(
    result: BatchImportResult,
    *,
    projection_state: str,
    projection_error: str | None = None,
) -> dict[str, object]:
    body = result.as_dict()
    if projection_state == "stale":
        body["ok"] = False
    body["journal_committed"] = result.imported_count > 0
    projection: dict[str, object] = {"state": projection_state}
    if projection_error is not None:
        projection["error"] = "projection_rebuild_failed"
        projection["detail"] = projection_error
    body["projection"] = projection
    return body


def _service_export_dir(export_root: Path, requested_output_dir: str) -> Path:
    if not requested_output_dir.strip():
        raise ValueError("output_dir must be a relative directory under export_root")

    requested = Path(requested_output_dir)
    if requested.is_absolute() or any(part in {"", ".", ".."} for part in requested.parts):
        raise ValueError("output_dir must be a relative directory under export_root")

    root = Path(export_root).resolve(strict=False)
    candidate = (root / requested).resolve(strict=False)
    if candidate == root or not candidate.is_relative_to(root):
        raise ValueError("output_dir must stay under export_root")
    return candidate
