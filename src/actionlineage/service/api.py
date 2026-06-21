"""Optional FastAPI service factory."""

from __future__ import annotations

from pathlib import Path
from typing import Any

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
from actionlineage.evidence import EvidenceNormalizer, EvidenceRecord, import_evidence_batch
from actionlineage.journal import LocalJournal
from actionlineage.projection import (
    ProjectionError,
    export_case_bundle,
    query_timeline,
    rebuild_projection,
)
from actionlineage.service.auth import (
    ServiceAuthError,
    ServicePrincipal,
    ServiceRole,
    StaticTokenAuthenticator,
    require_role,
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
) -> Any:
    """Create the optional FastAPI service application."""

    try:
        from fastapi import Depends, FastAPI, Header, HTTPException
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

    @app.get("/health")
    def health() -> dict[str, object]:
        return check_local_health(journal_path=journal_path, database_path=database_path).as_dict()

    @app.get("/timeline")
    def timeline(
        trace_id: str | None = None,
        run_id: str | None = None,
        service_principal: Any = principal_dependency,
    ) -> dict[str, object]:
        try:
            require_role(service_principal, ServiceRole.READ)
        except ServiceAuthError as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc
        return query_timeline(database_path, trace_id=trace_id, run_id=run_id).as_dict()

    @app.get("/events")
    def events(service_principal: Any = principal_dependency) -> dict[str, object]:
        try:
            require_role(service_principal, ServiceRole.READ)
        except ServiceAuthError as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc
        return {"events": [event.event_id for event in LocalJournal(journal_path).iter_events()]}

    @app.post("/export-case")
    def export_case(
        output_dir: str,
        trace_id: str | None = None,
        run_id: str | None = None,
        service_principal: Any = principal_dependency,
    ) -> dict[str, object]:
        try:
            require_role(service_principal, ServiceRole.EXPORT)
        except ServiceAuthError as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc
        try:
            return export_case_bundle(
                database_path,
                _service_export_dir(service_export_root, output_dir),
                trace_id=trace_id,
                run_id=run_id,
            ).as_dict()
        except (ProjectionError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=_safe_detail(exc)) from exc

    @app.post("/ingest")
    def ingest(
        body: dict[str, Any],
        service_principal: Any = principal_dependency,
    ) -> dict[str, object]:
        try:
            require_role(service_principal, ServiceRole.WRITE)
            journal = LocalJournal(journal_path)
            normalizer = _normalizer_from_request(
                body,
                service_principal=_typed_principal(service_principal),
                initial_sequence=journal.verify().records_verified,
            )
            records = _evidence_records_from_request(body)
            result = import_evidence_batch(
                records,
                normalizer=normalizer,
                journal=journal,
                existing_events=journal,
            )
            if result.imported_count:
                rebuild_projection(journal_path, database_path)
        except ServiceAuthError as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc
        except (ActionLineageValidationError, ValidationError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=_safe_detail(exc)) from exc
        return result.as_dict()

    @app.post("/contracts/validate")
    def validate_contract_endpoint(
        body: dict[str, Any],
        service_principal: Any = principal_dependency,
    ) -> dict[str, object]:
        try:
            require_role(service_principal, ServiceRole.READ)
            contract = contract_from_dict(_object_body_field(body, "contract"))
            events_tuple = tuple(LocalJournal(journal_path).iter_events())
            detection_results = _built_in_detection_results(events_tuple)
            return validate_contract(
                events_tuple,
                contract,
                detection_results=detection_results,
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
            require_role(service_principal, ServiceRole.READ)
            requested_rule_ids = _requested_rule_ids(body or {})
        except ServiceAuthError as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=_safe_detail(exc)) from exc

        events_tuple = tuple(LocalJournal(journal_path).iter_events())
        matches: list[dict[str, object]] = []
        rules_evaluated: list[str] = []
        for rule in built_in_sequence_rules():
            if requested_rule_ids and rule.rule_id not in requested_rule_ids:
                continue
            rules_evaluated.append(rule.rule_id or rule.name)
            matches.extend(match.as_dict() for match in evaluate_sequence_rule(events_tuple, rule))
        return {
            "ok": True,
            "rules_evaluated": rules_evaluated,
            "match_count": len(matches),
            "matches": matches,
        }

    return app


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
        else Classification(sensitivity=Sensitivity.INTERNAL, trust=TrustLevel.TRUSTED)
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


def _evidence_records_from_request(body: dict[str, Any]) -> tuple[EvidenceRecord, ...]:
    records = body.get("records")
    if not isinstance(records, list):
        raise ValueError("request body must include records array")
    return tuple(EvidenceRecord.model_validate(record) for record in records)


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


def _safe_detail(exc: Exception) -> str:
    if isinstance(exc, ValidationError):
        return "service request validation failed"
    return str(exc)


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
