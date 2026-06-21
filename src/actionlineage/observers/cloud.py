"""Fixture-first cloud observer adapters."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from actionlineage.domain import ResourceType, TrustLevel
from actionlineage.domain.events import JsonObject, JsonValue
from actionlineage.observers.local import ObservationOutcome, ObserverOutcome


@dataclass(frozen=True, slots=True)
class AwsCloudTrailObserver:
    """Observe AWS S3 side effects from CloudTrail-style fixture records."""

    observer_identity: str = "aws_cloudtrail_fixture"

    def observe_s3_object_write(
        self,
        record: dict[str, Any] | None,
        *,
        bucket: str,
        key: str,
    ) -> ObservationOutcome:
        identifier = f"aws:s3://{bucket}/{key}"
        if record is None:
            return _unverified(
                observer_identity=self.observer_identity,
                identifier=identifier,
                observed_state={"provider": "aws", "record_found": False},
            )

        request = _object(record.get("requestParameters"))
        event_name = str(record.get("eventName", ""))
        observed_bucket = _string(request.get("bucketName"))
        observed_key = _string(request.get("key"))
        observed = (
            record.get("eventSource") == "s3.amazonaws.com"
            and event_name in {"CompleteMultipartUpload", "CopyObject", "PutObject"}
            and observed_bucket == bucket
            and observed_key == key
        )
        state = _json_object(
            {
                "provider": "aws",
                "event_name": event_name,
                "event_source": record.get("eventSource"),
                "bucket": observed_bucket,
                "key": observed_key,
                "event_id": record.get("eventID"),
                "aws_region": record.get("awsRegion"),
            }
        )
        if observed:
            return _observed(self.observer_identity, identifier, state, provider="aws")
        return _conflicting(self.observer_identity, identifier, state, provider="aws")


@dataclass(frozen=True, slots=True)
class GcpAuditLogObserver:
    """Observe GCP Storage side effects from Audit Log-style fixture records."""

    observer_identity: str = "gcp_audit_log_fixture"

    def observe_storage_object_write(
        self,
        record: dict[str, Any] | None,
        *,
        bucket: str,
        object_name: str,
    ) -> ObservationOutcome:
        identifier = f"gcp:gs://{bucket}/{object_name}"
        if record is None:
            return _unverified(
                observer_identity=self.observer_identity,
                identifier=identifier,
                observed_state={"provider": "gcp", "record_found": False},
            )

        proto_payload = _object(record.get("protoPayload"))
        resource_name = _string(proto_payload.get("resourceName")) or _string(
            record.get("resourceName")
        )
        method_name = _string(proto_payload.get("methodName"))
        expected_suffix = f"/buckets/{bucket}/objects/{object_name}"
        observed = (
            proto_payload.get("serviceName") == "storage.googleapis.com"
            and method_name in {"storage.objects.create", "storage.objects.update"}
            and resource_name.endswith(expected_suffix)
        )
        state = _json_object(
            {
                "provider": "gcp",
                "method_name": method_name,
                "service_name": proto_payload.get("serviceName"),
                "resource_name": resource_name,
                "insert_id": record.get("insertId"),
            }
        )
        if observed:
            return _observed(self.observer_identity, identifier, state, provider="gcp")
        return _conflicting(self.observer_identity, identifier, state, provider="gcp")


@dataclass(frozen=True, slots=True)
class AzureActivityObserver:
    """Observe Azure Blob side effects from Activity Log-style fixture records."""

    observer_identity: str = "azure_activity_fixture"

    def observe_blob_write(
        self,
        record: dict[str, Any] | None,
        *,
        account: str,
        container: str,
        blob: str,
    ) -> ObservationOutcome:
        identifier = f"azure:blob://{account}/{container}/{blob}"
        if record is None:
            return _unverified(
                observer_identity=self.observer_identity,
                identifier=identifier,
                observed_state={"provider": "azure", "record_found": False},
            )

        operation_name = _operation_name(record.get("operationName"))
        resource_id = _string(record.get("resourceId"))
        expected_parts = (account.lower(), container.lower(), blob.lower())
        observed = operation_name.endswith("/write") and all(
            part in resource_id.lower() for part in expected_parts
        )
        state = _json_object(
            {
                "provider": "azure",
                "operation_name": operation_name,
                "resource_id": resource_id,
                "event_id": record.get("eventDataId"),
                "status": record.get("status"),
            }
        )
        if observed:
            return _observed(self.observer_identity, identifier, state, provider="azure")
        return _conflicting(self.observer_identity, identifier, state, provider="azure")


@dataclass(frozen=True, slots=True)
class KubernetesAuditObserver:
    """Observe Kubernetes resource side effects from audit-log fixture records."""

    observer_identity: str = "kubernetes_audit_fixture"

    def observe_resource_change(
        self,
        record: dict[str, Any] | None,
        *,
        resource: str,
        name: str,
        namespace: str | None = None,
        verb: str | None = None,
        api_group: str = "",
    ) -> ObservationOutcome:
        namespace_part = namespace or "cluster"
        identifier = f"kubernetes:{namespace_part}/{resource}/{name}"
        if record is None:
            return _unverified(
                observer_identity=self.observer_identity,
                identifier=identifier,
                observed_state={"provider": "kubernetes", "record_found": False},
            )

        object_ref = _object(record.get("objectRef"))
        response_status = _object(record.get("responseStatus"))
        observed_verb = _string(record.get("verb"))
        observed_resource = _string(object_ref.get("resource"))
        observed_name = _string(object_ref.get("name"))
        observed_namespace = _string(object_ref.get("namespace")) or None
        observed_api_group = _string(object_ref.get("apiGroup"))
        response_code = _int(response_status.get("code"))
        expected_verb = verb or observed_verb
        observed = (
            record.get("stage") == "ResponseComplete"
            and response_code is not None
            and 200 <= response_code < 400
            and observed_verb == expected_verb
            and observed_resource == resource
            and observed_name == name
            and observed_namespace == namespace
            and observed_api_group == api_group
        )
        state = _json_object(
            {
                "provider": "kubernetes",
                "audit_id": record.get("auditID"),
                "verb": observed_verb,
                "stage": record.get("stage"),
                "response_code": response_code,
                "resource": observed_resource,
                "name": observed_name,
                "namespace": observed_namespace,
                "api_group": observed_api_group,
            }
        )
        if observed:
            return _observed(self.observer_identity, identifier, state, provider="kubernetes")
        return _conflicting(self.observer_identity, identifier, state, provider="kubernetes")


def _observed(
    observer_identity: str,
    identifier: str,
    observed_state: JsonObject,
    *,
    provider: str,
) -> ObservationOutcome:
    return ObservationOutcome(
        observer_identity=observer_identity,
        resource_type=ResourceType.CLOUD_RESOURCE,
        resource_identifier=identifier,
        outcome=ObserverOutcome.OBSERVED,
        observed_state=observed_state,
        limitations=(f"{provider} fixture audit-log observation only",),
        trust=TrustLevel.EXTERNAL,
    )


def _conflicting(
    observer_identity: str,
    identifier: str,
    observed_state: JsonObject,
    *,
    provider: str,
) -> ObservationOutcome:
    return ObservationOutcome(
        observer_identity=observer_identity,
        resource_type=ResourceType.CLOUD_RESOURCE,
        resource_identifier=identifier,
        outcome=ObserverOutcome.CONFLICTING,
        observed_state=observed_state,
        limitations=(f"{provider} fixture did not match the expected cloud resource",),
        trust=TrustLevel.EXTERNAL,
    )


def _unverified(
    *,
    observer_identity: str,
    identifier: str,
    observed_state: JsonObject,
) -> ObservationOutcome:
    return ObservationOutcome(
        observer_identity=observer_identity,
        resource_type=ResourceType.CLOUD_RESOURCE,
        resource_identifier=identifier,
        outcome=ObserverOutcome.UNVERIFIED,
        observed_state=observed_state,
        limitations=("no cloud audit fixture was recorded; this is not evidence of absence",),
        trust=TrustLevel.EXTERNAL,
    )


def _object(value: object) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _string(value: object) -> str:
    return value if isinstance(value, str) else ""


def _int(value: object) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def _operation_name(value: object) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        return _string(value.get("value"))
    return ""


def _json_object(value: dict[str, object]) -> JsonObject:
    return {
        key: _json_value(raw_value) for key, raw_value in value.items() if raw_value is not None
    }


def _json_value(value: object) -> JsonValue:
    if value is None or isinstance(value, str | int | float | bool):
        return value
    if isinstance(value, list):
        return [_json_value(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _json_value(child) for key, child in value.items()}
    return str(value)
