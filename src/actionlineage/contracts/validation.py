"""Contract validator for required evidence and control dependencies."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from actionlineage.detection import DetectionMatch
from actionlineage.domain import EventEnvelope, event_to_dict
from actionlineage.domain.events import event_type_value
from actionlineage.errors import ActionLineageValidationError

CONTRACT_SCHEMA_VERSION = "actionlineage.dev/contract/v1"


@dataclass(frozen=True, slots=True)
class ContractEventRequirement:
    """Required event type and fields."""

    event_type: str
    required_fields: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class ContractRelationshipRequirement:
    """Required parent-child or explicit payload reference relationship."""

    child_event_type: str
    parent_event_type: str
    reference_field: str | None = None


@dataclass(frozen=True, slots=True)
class ContractEvidenceLinkRequirement:
    """Required evidence-link semantics."""

    event_type: str = "side_effect.verified"
    subject_event_type: str | None = None
    evidence_event_type: str | None = None
    relationship: str | None = None
    verification_status: str | None = None
    corroboration_types: tuple[str, ...] = ()
    observer_identity: str | None = None


@dataclass(frozen=True, slots=True)
class ContractLatencyRequirement:
    """Maximum occurrence-time latency between two event types."""

    start_event_type: str
    end_event_type: str
    max_seconds: float
    group_by: tuple[str, ...] = ("correlation.run_id",)


@dataclass(frozen=True, slots=True)
class ContractDescriptorRequirement:
    """Required tool descriptor identity for an event type."""

    event_type: str
    descriptor_hash_field: str = "payload.tool_identity.descriptor_hash"
    tool_name_field: str = "payload.tool_identity.name"
    hash_prefix: str = "sha256:"


@dataclass(frozen=True, slots=True)
class ContractDetectionRequirement:
    """Required detection coverage and evidence-quality dependencies."""

    rule_id: str
    required: bool = True
    required_event_types: tuple[str, ...] = ()
    required_verification_statuses: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class LineageContract:
    """Executable subset of a Lineage Contract."""

    name: str
    events: tuple[ContractEventRequirement, ...]
    relationships: tuple[ContractRelationshipRequirement, ...] = ()
    evidence_links: tuple[ContractEvidenceLinkRequirement, ...] = ()
    latency_requirements: tuple[ContractLatencyRequirement, ...] = ()
    descriptor_requirements: tuple[ContractDescriptorRequirement, ...] = ()
    detection_requirements: tuple[ContractDetectionRequirement, ...] = ()
    allowed_verification_statuses: frozenset[str] = frozenset()
    required_verification_status: str | None = None
    hash_chain_required: bool = True


@dataclass(frozen=True, slots=True)
class ContractViolation:
    """One machine-readable contract failure."""

    code: str
    message: str
    event_id: str | None = None
    event_type: str | None = None
    field: str | None = None
    severity: str = "error"
    remediation: str | None = None

    def as_dict(self) -> dict[str, object]:
        return {
            "code": self.code,
            "message": self.message,
            "event_id": self.event_id,
            "event_type": self.event_type,
            "field": self.field,
            "severity": self.severity,
            "remediation": self.remediation,
        }


@dataclass(frozen=True, slots=True)
class ContractResult:
    """Contract validation result."""

    contract_name: str
    ok: bool
    violations: tuple[ContractViolation, ...]

    def as_dict(self) -> dict[str, object]:
        return {
            "contract_name": self.contract_name,
            "ok": self.ok,
            "violations": [violation.as_dict() for violation in self.violations],
        }


def validate_contract(
    events: tuple[EventEnvelope, ...],
    contract: LineageContract,
    *,
    detection_results: tuple[DetectionMatch, ...] = (),
) -> ContractResult:
    """Validate required telemetry fields and control dependencies."""

    event_objects = tuple(event_to_dict(event) for event in events)
    violations: list[ContractViolation] = []
    events_by_id = {event.event_id: event for event in events}

    if contract.hash_chain_required:
        for event in events:
            if event.integrity.event_hash is None:
                violations.append(
                    ContractViolation(
                        code="event_hash_missing",
                        message="contract requires journal integrity hashes",
                        event_id=event.event_id,
                        event_type=event_type_value(event.event_type),
                        remediation="append events through the local journal before validation",
                    )
                )

    for requirement in contract.events:
        matches = _events_of_type(events, requirement.event_type)
        if not matches:
            violations.append(
                ContractViolation(
                    code="required_event_missing",
                    message=f"required event type is missing: {requirement.event_type}",
                    event_type=requirement.event_type,
                    remediation="emit the required lifecycle event before evaluating this contract",
                )
            )
            continue

        for field in requirement.required_fields:
            if not any(_has_nonempty_field(event_to_dict(event), field) for event in matches):
                violations.append(
                    ContractViolation(
                        code="required_field_missing",
                        message=f"required field is missing: {field}",
                        event_type=requirement.event_type,
                        field=field,
                        remediation="populate this field at the redaction boundary",
                    )
                )

    for relationship in contract.relationships:
        if not _relationship_exists(events, events_by_id, relationship):
            violations.append(
                ContractViolation(
                    code="relationship_missing",
                    message=(
                        f"missing relationship {relationship.parent_event_type} -> "
                        f"{relationship.child_event_type}"
                    ),
                    event_type=relationship.child_event_type,
                    field=relationship.reference_field,
                    remediation="record a causal parent or explicit reference field",
                )
            )

    for evidence_requirement in contract.evidence_links:
        violations.extend(
            _validate_evidence_link_requirement(events, events_by_id, evidence_requirement)
        )

    for latency_requirement in contract.latency_requirements:
        violations.extend(_validate_latency_requirement(events, latency_requirement))

    for descriptor_requirement in contract.descriptor_requirements:
        violations.extend(_validate_descriptor_requirement(events, descriptor_requirement))

    for detection_requirement in contract.detection_requirements:
        violations.extend(
            _validate_detection_requirement(
                event_objects=event_objects,
                detection_results=detection_results,
                requirement=detection_requirement,
            )
        )

    statuses = _verification_statuses(event_objects)
    if (
        contract.required_verification_status is not None
        and contract.required_verification_status not in statuses
    ):
        violations.append(
            ContractViolation(
                code="verification_status_missing",
                message=(
                    "required verification status is missing: "
                    f"{contract.required_verification_status}"
                ),
                field="payload.evidence_link.verification_status",
                remediation="emit explicit verification evidence before satisfying this contract",
            )
        )

    if contract.allowed_verification_statuses:
        unexpected = statuses - contract.allowed_verification_statuses
        for status in sorted(unexpected):
            violations.append(
                ContractViolation(
                    code="verification_status_not_allowed",
                    message=f"verification status is not allowed: {status}",
                    field="payload.evidence_link.verification_status",
                    remediation="update the contract or emit a supported verification outcome",
                )
            )

    return ContractResult(
        contract_name=contract.name,
        ok=not violations,
        violations=tuple(violations),
    )


def load_contract(path: Path) -> LineageContract:
    """Load a JSON Lineage Contract file."""

    path = Path(path)
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ActionLineageValidationError(
            f"contract file is not valid JSON; first invalid field: line {exc.lineno}"
        ) from None
    if not isinstance(raw, dict):
        raise ActionLineageValidationError("contract file must contain a JSON object")
    return contract_from_dict(raw)


def write_contract_template(path: Path, *, name: str = "actionlineage-contract") -> LineageContract:
    """Write a starter JSON Lineage Contract and return its model."""

    contract = LineageContract(
        name=name,
        events=(
            ContractEventRequirement(
                event_type="tool.execution.requested",
                required_fields=("payload.tool_identity.name",),
            ),
            ContractEventRequirement(
                event_type="tool.execution.acknowledged",
                required_fields=("payload.acknowledgement.status",),
            ),
            ContractEventRequirement(
                event_type="side_effect.verified",
                required_fields=(
                    "payload.evidence_link.subject_event_id",
                    "payload.evidence_link.evidence_event_id",
                    "payload.evidence_link.verification_status",
                ),
            ),
        ),
        relationships=(
            ContractRelationshipRequirement(
                child_event_type="tool.execution.acknowledged",
                parent_event_type="tool.execution.dispatched",
            ),
        ),
        evidence_links=(
            ContractEvidenceLinkRequirement(
                event_type="side_effect.verified",
                verification_status="verified",
            ),
        ),
        descriptor_requirements=(
            ContractDescriptorRequirement(event_type="tool.execution.requested"),
        ),
        allowed_verification_statuses=frozenset(
            {"verified", "unverified", "timed_out", "conflicting", "observed"}
        ),
    )
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(contract_to_dict(contract), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return contract


def contract_from_dict(data: dict[str, Any]) -> LineageContract:
    """Build a contract model from the public JSON representation."""

    spec = _object(data.get("spec"), "spec") if "spec" in data else data
    metadata = _object(data.get("metadata"), "metadata") if "metadata" in data else {}
    requirements = (
        _object(spec.get("requirements"), "spec.requirements") if "requirements" in spec else spec
    )
    name = _string_or_none(metadata.get("name")) or _string_or_none(spec.get("name"))
    if name is None:
        name = _string_or_none(data.get("name"))
    if name is None:
        raise ActionLineageValidationError("contract metadata.name is required")

    verification = _object(requirements.get("verification"), "requirements.verification")
    integrity = _object(requirements.get("integrity"), "requirements.integrity")

    return LineageContract(
        name=name,
        events=tuple(
            ContractEventRequirement(
                event_type=_required_string(item, "type"),
                required_fields=tuple(_strings(item.get("requiredFields", ()))),
            )
            for item in _objects(requirements.get("events", ()), "requirements.events")
        ),
        relationships=tuple(
            ContractRelationshipRequirement(
                child_event_type=_required_string(item, "child"),
                parent_event_type=_required_string(item, "parent"),
                reference_field=_string_or_none(item.get("referenceField")),
            )
            for item in _objects(
                requirements.get("relationships", ()), "requirements.relationships"
            )
        ),
        evidence_links=tuple(
            ContractEvidenceLinkRequirement(
                event_type=_string_or_none(item.get("eventType")) or "side_effect.verified",
                subject_event_type=_string_or_none(item.get("subjectEventType")),
                evidence_event_type=_string_or_none(item.get("evidenceEventType")),
                relationship=_string_or_none(item.get("relationship")),
                verification_status=_string_or_none(item.get("verificationStatus")),
                corroboration_types=tuple(_strings(item.get("corroborationTypes", ()))),
                observer_identity=_string_or_none(item.get("observerIdentity")),
            )
            for item in _objects(
                requirements.get("evidenceLinks", ()), "requirements.evidenceLinks"
            )
        ),
        latency_requirements=tuple(
            ContractLatencyRequirement(
                start_event_type=_required_string(item, "startEventType"),
                end_event_type=_required_string(item, "endEventType"),
                max_seconds=float(_required_number(item, "maxSeconds")),
                group_by=tuple(_strings(item.get("groupBy", ("correlation.run_id",)))),
            )
            for item in _objects(requirements.get("latency", ()), "requirements.latency")
        ),
        descriptor_requirements=tuple(
            ContractDescriptorRequirement(
                event_type=_required_string(item, "eventType"),
                descriptor_hash_field=_string_or_none(item.get("descriptorHashField"))
                or "payload.tool_identity.descriptor_hash",
                tool_name_field=_string_or_none(item.get("toolNameField"))
                or "payload.tool_identity.name",
                hash_prefix=_string_or_none(item.get("hashPrefix")) or "sha256:",
            )
            for item in _objects(requirements.get("descriptors", ()), "requirements.descriptors")
        ),
        detection_requirements=tuple(
            ContractDetectionRequirement(
                rule_id=_required_string(item, "ruleId"),
                required=bool(item.get("required", True)),
                required_event_types=tuple(_strings(item.get("requiredEventTypes", ()))),
                required_verification_statuses=tuple(
                    _strings(item.get("requiredVerificationStatuses", ()))
                ),
            )
            for item in _objects(requirements.get("detections", ()), "requirements.detections")
        ),
        allowed_verification_statuses=frozenset(_strings(verification.get("allowedStatuses", ()))),
        required_verification_status=_string_or_none(verification.get("requiredStatus")),
        hash_chain_required=bool(integrity.get("hashChainRequired", True)),
    )


def contract_to_dict(contract: LineageContract) -> dict[str, object]:
    """Return the public JSON representation for a contract."""

    return {
        "apiVersion": CONTRACT_SCHEMA_VERSION,
        "kind": "LineageContract",
        "metadata": {"name": contract.name},
        "spec": {
            "requirements": {
                "events": [
                    {
                        "type": requirement.event_type,
                        "requiredFields": list(requirement.required_fields),
                    }
                    for requirement in contract.events
                ],
                "relationships": [
                    {
                        "child": requirement.child_event_type,
                        "parent": requirement.parent_event_type,
                        "referenceField": requirement.reference_field,
                    }
                    for requirement in contract.relationships
                ],
                "evidenceLinks": [
                    {
                        "eventType": requirement.event_type,
                        "subjectEventType": requirement.subject_event_type,
                        "evidenceEventType": requirement.evidence_event_type,
                        "relationship": requirement.relationship,
                        "verificationStatus": requirement.verification_status,
                        "corroborationTypes": list(requirement.corroboration_types),
                        "observerIdentity": requirement.observer_identity,
                    }
                    for requirement in contract.evidence_links
                ],
                "latency": [
                    {
                        "startEventType": requirement.start_event_type,
                        "endEventType": requirement.end_event_type,
                        "maxSeconds": requirement.max_seconds,
                        "groupBy": list(requirement.group_by),
                    }
                    for requirement in contract.latency_requirements
                ],
                "descriptors": [
                    {
                        "eventType": requirement.event_type,
                        "descriptorHashField": requirement.descriptor_hash_field,
                        "toolNameField": requirement.tool_name_field,
                        "hashPrefix": requirement.hash_prefix,
                    }
                    for requirement in contract.descriptor_requirements
                ],
                "detections": [
                    {
                        "ruleId": requirement.rule_id,
                        "required": requirement.required,
                        "requiredEventTypes": list(requirement.required_event_types),
                        "requiredVerificationStatuses": list(
                            requirement.required_verification_statuses
                        ),
                    }
                    for requirement in contract.detection_requirements
                ],
                "verification": {
                    "allowedStatuses": sorted(contract.allowed_verification_statuses),
                    "requiredStatus": contract.required_verification_status,
                },
                "integrity": {"hashChainRequired": contract.hash_chain_required},
            }
        },
    }


def explain_contract(contract: LineageContract) -> dict[str, object]:
    """Return a concise machine-readable contract summary."""

    return {
        "name": contract.name,
        "event_requirements": len(contract.events),
        "relationship_requirements": len(contract.relationships),
        "evidence_link_requirements": len(contract.evidence_links),
        "latency_requirements": len(contract.latency_requirements),
        "descriptor_requirements": len(contract.descriptor_requirements),
        "detection_requirements": len(contract.detection_requirements),
        "hash_chain_required": contract.hash_chain_required,
        "required_verification_status": contract.required_verification_status,
        "allowed_verification_statuses": sorted(contract.allowed_verification_statuses),
    }


def contract_result_annotations(result: ContractResult) -> tuple[str, ...]:
    """Return lightweight CI annotation lines for a validation result."""

    if result.ok:
        return (f"contract {result.contract_name}: ok",)
    return tuple(
        (
            f"{violation.severity.upper()} {result.contract_name} {violation.code}"
            f" event_id={violation.event_id or '-'} field={violation.field or '-'}"
            f" message={violation.message}"
        )
        for violation in result.violations
    )


def _validate_evidence_link_requirement(
    events: tuple[EventEnvelope, ...],
    events_by_id: dict[str, EventEnvelope],
    requirement: ContractEvidenceLinkRequirement,
) -> tuple[ContractViolation, ...]:
    matches = _events_of_type(events, requirement.event_type)
    if not matches:
        return (
            ContractViolation(
                code="evidence_link_event_missing",
                message=f"no event found for evidence-link requirement: {requirement.event_type}",
                event_type=requirement.event_type,
                remediation="emit an event carrying a payload.evidence_link object",
            ),
        )

    violations: list[ContractViolation] = []
    for event in matches:
        event_object = event_to_dict(event)
        evidence_link = _get_path(event_object, "payload.evidence_link")
        if not isinstance(evidence_link, dict):
            violations.append(
                ContractViolation(
                    code="evidence_link_missing",
                    message="event does not include payload.evidence_link",
                    event_id=event.event_id,
                    event_type=event_type_value(event.event_type),
                    field="payload.evidence_link",
                    remediation="attach an explicit evidence link to verification events",
                )
            )
            continue

        subject_id = _string_or_none(evidence_link.get("subject_event_id"))
        evidence_id = _string_or_none(evidence_link.get("evidence_event_id"))
        if subject_id is None or evidence_id is None:
            violations.append(
                ContractViolation(
                    code="evidence_link_field_missing",
                    message="evidence link must identify subject_event_id and evidence_event_id",
                    event_id=event.event_id,
                    event_type=event_type_value(event.event_type),
                    field="payload.evidence_link",
                    remediation="record both sides of the corroboration relationship",
                )
            )
            continue

        subject = events_by_id.get(subject_id)
        evidence = events_by_id.get(evidence_id)
        if subject is None or evidence is None:
            missing_id = subject_id if subject is None else evidence_id
            violations.append(
                ContractViolation(
                    code="evidence_link_reference_missing",
                    message=f"evidence link references missing event: {missing_id}",
                    event_id=event.event_id,
                    event_type=event_type_value(event.event_type),
                    field="payload.evidence_link",
                    remediation="persist referenced subject and evidence events in the journal",
                )
            )
            continue

        violations.extend(
            _validate_evidence_link_types(
                event=event,
                requirement=requirement,
                evidence_link=evidence_link,
                subject=subject,
                evidence=evidence,
            )
        )
    return tuple(violations)


def _validate_evidence_link_types(
    *,
    event: EventEnvelope,
    requirement: ContractEvidenceLinkRequirement,
    evidence_link: dict[Any, Any],
    subject: EventEnvelope,
    evidence: EventEnvelope,
) -> tuple[ContractViolation, ...]:
    violations: list[ContractViolation] = []
    checks = (
        (
            requirement.subject_event_type,
            event_type_value(subject.event_type),
            "subjectEventType",
        ),
        (
            requirement.evidence_event_type,
            event_type_value(evidence.event_type),
            "evidenceEventType",
        ),
        (
            requirement.relationship,
            _string_or_none(evidence_link.get("relationship")),
            "relationship",
        ),
        (
            requirement.verification_status,
            _string_or_none(evidence_link.get("verification_status")),
            "verificationStatus",
        ),
        (
            requirement.observer_identity,
            _string_or_none(evidence_link.get("observer_identity")),
            "observerIdentity",
        ),
    )
    for expected, actual, field_name in checks:
        if expected is not None and actual != expected:
            violations.append(
                ContractViolation(
                    code="evidence_link_requirement_mismatch",
                    message=f"evidence link {field_name} expected {expected}, got {actual}",
                    event_id=event.event_id,
                    event_type=event_type_value(event.event_type),
                    field=f"payload.evidence_link.{field_name}",
                    remediation="emit corroboration metadata that matches the contract",
                )
            )

    corroboration_type = _string_or_none(evidence_link.get("corroboration_type"))
    if (
        requirement.corroboration_types
        and corroboration_type not in requirement.corroboration_types
    ):
        violations.append(
            ContractViolation(
                code="evidence_link_requirement_mismatch",
                message=(
                    "evidence link corroboration type expected one of "
                    f"{sorted(requirement.corroboration_types)}, got {corroboration_type}"
                ),
                event_id=event.event_id,
                event_type=event_type_value(event.event_type),
                field="payload.evidence_link.corroboration_type",
                remediation="use an approved corroboration source for this contract",
            )
        )
    return tuple(violations)


def _validate_latency_requirement(
    events: tuple[EventEnvelope, ...],
    requirement: ContractLatencyRequirement,
) -> tuple[ContractViolation, ...]:
    start_events = _events_of_type(events, requirement.start_event_type)
    end_events = _events_of_type(events, requirement.end_event_type)
    if not start_events or not end_events:
        return (
            ContractViolation(
                code="latency_event_missing",
                message=(
                    f"latency requirement needs {requirement.start_event_type} and "
                    f"{requirement.end_event_type}"
                ),
                event_type=requirement.end_event_type,
                remediation="emit both lifecycle states before validating latency",
            ),
        )

    starts_by_group = _group_by(start_events, requirement.group_by)
    violations: list[ContractViolation] = []
    for end_event in end_events:
        end_group = _group_key(end_event, requirement.group_by)
        candidate_starts = starts_by_group.get(end_group, ())
        if not candidate_starts:
            violations.append(
                ContractViolation(
                    code="latency_start_missing",
                    message=f"no start event for latency group {end_group}",
                    event_id=end_event.event_id,
                    event_type=event_type_value(end_event.event_type),
                    remediation="preserve correlation fields across lifecycle events",
                )
            )
            continue
        start_event = min(
            candidate_starts, key=lambda event: abs(end_event.occurred_at - event.occurred_at)
        )
        observed_seconds = abs((end_event.occurred_at - start_event.occurred_at).total_seconds())
        if observed_seconds > requirement.max_seconds:
            violations.append(
                ContractViolation(
                    code="latency_breach",
                    message=(
                        f"latency {observed_seconds:.3f}s exceeds max "
                        f"{requirement.max_seconds:.3f}s"
                    ),
                    event_id=end_event.event_id,
                    event_type=event_type_value(end_event.event_type),
                    field="occurred_at",
                    remediation="lower telemetry delay or relax the documented contract threshold",
                )
            )
    return tuple(violations)


def _validate_descriptor_requirement(
    events: tuple[EventEnvelope, ...],
    requirement: ContractDescriptorRequirement,
) -> tuple[ContractViolation, ...]:
    matches = _events_of_type(events, requirement.event_type)
    if not matches:
        return (
            ContractViolation(
                code="descriptor_event_missing",
                message=f"no event found for descriptor requirement: {requirement.event_type}",
                event_type=requirement.event_type,
                remediation="emit the event that should carry tool descriptor identity",
            ),
        )
    violations: list[ContractViolation] = []
    for event in matches:
        event_object = event_to_dict(event)
        tool_name = _string_or_none(_get_path(event_object, requirement.tool_name_field))
        descriptor_hash = _string_or_none(
            _get_path(event_object, requirement.descriptor_hash_field)
        )
        if tool_name is None or descriptor_hash is None:
            violations.append(
                ContractViolation(
                    code="descriptor_identity_missing",
                    message="tool name and descriptor hash are required",
                    event_id=event.event_id,
                    event_type=event_type_value(event.event_type),
                    field=requirement.descriptor_hash_field,
                    remediation=(
                        "record a canonical descriptor hash at tool discovery or request time"
                    ),
                )
            )
            continue
        if not descriptor_hash.startswith(requirement.hash_prefix):
            violations.append(
                ContractViolation(
                    code="descriptor_hash_invalid",
                    message=f"descriptor hash must start with {requirement.hash_prefix}",
                    event_id=event.event_id,
                    event_type=event_type_value(event.event_type),
                    field=requirement.descriptor_hash_field,
                    remediation="hash canonical descriptors with the configured algorithm prefix",
                )
            )
    return tuple(violations)


def _validate_detection_requirement(
    *,
    event_objects: tuple[dict[str, Any], ...],
    detection_results: tuple[DetectionMatch, ...],
    requirement: ContractDetectionRequirement,
) -> tuple[ContractViolation, ...]:
    matches = tuple(match for match in detection_results if match.rule_id == requirement.rule_id)
    if requirement.required and not matches:
        return (
            ContractViolation(
                code="required_detection_missing",
                message=f"required detection result is missing: {requirement.rule_id}",
                remediation="run the required detection rule against this evidence set in CI",
            ),
        )
    if not matches:
        return ()

    present_event_types = {
        event_type
        for event_type in (
            _string_or_none(event_object.get("event_type")) for event_object in event_objects
        )
        if event_type is not None
    }
    missing_event_types = set(requirement.required_event_types) - present_event_types
    statuses = _verification_statuses(event_objects)
    missing_statuses = set(requirement.required_verification_statuses) - statuses
    violations: list[ContractViolation] = []
    if missing_event_types:
        violations.append(
            ContractViolation(
                code="detection_control_dependency_missing",
                message=(
                    f"detection {requirement.rule_id} depends on missing events: "
                    f"{sorted(missing_event_types)}"
                ),
                remediation=(
                    "ensure the detection is only considered covered with required telemetry"
                ),
            )
        )
    if missing_statuses:
        violations.append(
            ContractViolation(
                code="detection_control_dependency_missing",
                message=(
                    f"detection {requirement.rule_id} depends on missing statuses: "
                    f"{sorted(missing_statuses)}"
                ),
                field="payload.evidence_link.verification_status",
                remediation="ensure detection coverage includes required verification states",
            )
        )
    return tuple(violations)


def _events_of_type(
    events: tuple[EventEnvelope, ...],
    event_type: str,
) -> tuple[EventEnvelope, ...]:
    return tuple(event for event in events if event_type_value(event.event_type) == event_type)


def _relationship_exists(
    events: tuple[EventEnvelope, ...],
    events_by_id: dict[str, EventEnvelope],
    relationship: ContractRelationshipRequirement,
) -> bool:
    for child in _events_of_type(events, relationship.child_event_type):
        parent_id = child.causality.parent_event_id
        if relationship.reference_field is not None:
            parent_id = _string_or_none(
                _get_path(event_to_dict(child), relationship.reference_field)
            )
        if parent_id is None:
            continue
        parent = events_by_id.get(parent_id)
        if parent is None:
            continue
        if event_type_value(parent.event_type) == relationship.parent_event_type:
            return True
    return False


def _verification_statuses(event_objects: tuple[dict[str, Any], ...]) -> frozenset[str]:
    statuses: set[str] = set()
    for event_object in event_objects:
        payload = event_object.get("payload")
        if not isinstance(payload, dict):
            continue
        evidence_link = payload.get("evidence_link")
        if isinstance(evidence_link, dict):
            status = _string_or_none(evidence_link.get("verification_status"))
            if status is not None:
                statuses.add(status)
        status = _string_or_none(payload.get("verification_status"))
        if status is not None:
            statuses.add(status)
    return frozenset(statuses)


def _group_by(
    events: tuple[EventEnvelope, ...],
    paths: tuple[str, ...],
) -> dict[tuple[str, ...], tuple[EventEnvelope, ...]]:
    grouped: dict[tuple[str, ...], list[EventEnvelope]] = {}
    for event in events:
        grouped.setdefault(_group_key(event, paths), []).append(event)
    return {key: tuple(value) for key, value in grouped.items()}


def _group_key(event: EventEnvelope, paths: tuple[str, ...]) -> tuple[str, ...]:
    event_object = event_to_dict(event)
    return tuple(str(_get_path(event_object, path) or "") for path in paths)


def _has_nonempty_field(event_object: dict[str, Any], path: str) -> bool:
    value = _get_path(event_object, path)
    if value is None:
        return False
    if value == "":
        return False
    return not (value == [] or value == {})


def _get_path(value: object, path: str) -> object:
    current = value
    for part in path.split("."):
        if isinstance(current, dict):
            current = current.get(part)
            continue
        if isinstance(current, list) and part.isdecimal():
            index = int(part)
            if index >= len(current):
                return None
            current = current[index]
            continue
        else:
            return None
    return current


def _string_or_none(value: object) -> str | None:
    if isinstance(value, str) and value:
        return value
    return None


def _object(value: object, field: str) -> dict[str, Any]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ActionLineageValidationError(f"{field} must be an object")
    return value


def _objects(value: object, field: str) -> tuple[dict[str, Any], ...]:
    if value is None:
        return ()
    if not isinstance(value, list | tuple):
        raise ActionLineageValidationError(f"{field} must be a list")
    objects: list[dict[str, Any]] = []
    for index, item in enumerate(value):
        if not isinstance(item, dict):
            raise ActionLineageValidationError(f"{field}.{index} must be an object")
        objects.append(item)
    return tuple(objects)


def _strings(value: object) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        return (value,)
    if not isinstance(value, list | tuple | set | frozenset):
        raise ActionLineageValidationError("expected a list of strings")
    strings: list[str] = []
    for item in value:
        string = _string_or_none(item)
        if string is None:
            raise ActionLineageValidationError("expected a list of nonempty strings")
        strings.append(string)
    return tuple(strings)


def _required_string(data: dict[str, Any], field: str) -> str:
    value = _string_or_none(data.get(field))
    if value is None:
        raise ActionLineageValidationError(f"{field} is required")
    return value


def _required_number(data: dict[str, Any], field: str) -> float | int:
    value = data.get(field)
    if isinstance(value, int | float):
        return value
    raise ActionLineageValidationError(f"{field} must be a number")
