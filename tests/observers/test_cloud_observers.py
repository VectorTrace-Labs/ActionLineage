from __future__ import annotations

from actionlineage.domain import ResourceType, TrustLevel, VerificationStatus
from actionlineage.observers import (
    AwsCloudTrailObserver,
    AzureActivityObserver,
    GcpAuditLogObserver,
    KubernetesAuditObserver,
    ObserverOutcome,
)


def test_aws_cloudtrail_observer_reports_s3_write_fixture() -> None:
    observation = AwsCloudTrailObserver().observe_s3_object_write(
        {
            "eventSource": "s3.amazonaws.com",
            "eventName": "PutObject",
            "eventID": "aws-event-1",
            "awsRegion": "us-east-1",
            "requestParameters": {"bucketName": "demo-bucket", "key": "reports/out.json"},
        },
        bucket="demo-bucket",
        key="reports/out.json",
    )

    assert observation.outcome == ObserverOutcome.OBSERVED
    assert observation.resource_type == ResourceType.CLOUD_RESOURCE
    assert observation.resource_identifier == "aws:s3://demo-bucket/reports/out.json"
    assert observation.trust == TrustLevel.EXTERNAL
    assert observation.verification_status == VerificationStatus.OBSERVED


def test_gcp_audit_log_observer_reports_storage_write_fixture() -> None:
    observation = GcpAuditLogObserver().observe_storage_object_write(
        {
            "insertId": "gcp-event-1",
            "protoPayload": {
                "serviceName": "storage.googleapis.com",
                "methodName": "storage.objects.create",
                "resourceName": "projects/_/buckets/demo-bucket/objects/reports/out.json",
            },
        },
        bucket="demo-bucket",
        object_name="reports/out.json",
    )

    assert observation.outcome == ObserverOutcome.OBSERVED
    assert observation.resource_identifier == "gcp:gs://demo-bucket/reports/out.json"
    assert observation.as_payload()["observed_state"]["provider"] == "gcp"


def test_azure_activity_observer_reports_blob_write_fixture() -> None:
    observation = AzureActivityObserver().observe_blob_write(
        {
            "eventDataId": "azure-event-1",
            "operationName": {
                "value": "Microsoft.Storage/storageAccounts/blobServices/containers/blobs/write"
            },
            "resourceId": (
                "/subscriptions/sub/resourceGroups/rg/providers/Microsoft.Storage/"
                "storageAccounts/acct/blobServices/default/containers/demo/blobs/out.json"
            ),
            "status": "Succeeded",
        },
        account="acct",
        container="demo",
        blob="out.json",
    )

    assert observation.outcome == ObserverOutcome.OBSERVED
    assert observation.resource_identifier == "azure:blob://acct/demo/out.json"
    assert observation.as_payload()["observed_state"]["provider"] == "azure"


def test_cloud_fixture_absence_is_unverified_not_absence_evidence() -> None:
    observation = AwsCloudTrailObserver().observe_s3_object_write(
        None,
        bucket="demo-bucket",
        key="missing.json",
    )
    limitations = " ".join(observation.as_payload()["limitations"])

    assert observation.outcome == ObserverOutcome.UNVERIFIED
    assert observation.verification_status == VerificationStatus.UNVERIFIED
    assert "not evidence of absence" in limitations


def test_cloud_fixture_mismatch_is_conflicting() -> None:
    observation = AwsCloudTrailObserver().observe_s3_object_write(
        {
            "eventSource": "s3.amazonaws.com",
            "eventName": "PutObject",
            "requestParameters": {"bucketName": "other", "key": "reports/out.json"},
        },
        bucket="demo-bucket",
        key="reports/out.json",
    )

    assert observation.outcome == ObserverOutcome.CONFLICTING
    assert observation.verification_status == VerificationStatus.CONFLICTING


def test_kubernetes_audit_observer_reports_resource_change_fixture() -> None:
    observation = KubernetesAuditObserver().observe_resource_change(
        {
            "auditID": "k8s-audit-1",
            "verb": "create",
            "stage": "ResponseComplete",
            "objectRef": {
                "apiGroup": "batch",
                "resource": "jobs",
                "namespace": "demo",
                "name": "nightly-export",
            },
            "responseStatus": {"code": 201},
        },
        api_group="batch",
        resource="jobs",
        namespace="demo",
        name="nightly-export",
        verb="create",
    )

    assert observation.outcome == ObserverOutcome.OBSERVED
    assert observation.resource_type == ResourceType.CLOUD_RESOURCE
    assert observation.resource_identifier == "kubernetes:demo/jobs/nightly-export"
    assert observation.trust == TrustLevel.EXTERNAL
    assert observation.as_payload()["observed_state"]["provider"] == "kubernetes"


def test_kubernetes_audit_fixture_absence_is_unverified_not_absence_evidence() -> None:
    observation = KubernetesAuditObserver().observe_resource_change(
        None,
        resource="deployments",
        namespace="demo",
        name="web",
        verb="patch",
    )
    limitations = " ".join(observation.as_payload()["limitations"])

    assert observation.outcome == ObserverOutcome.UNVERIFIED
    assert observation.verification_status == VerificationStatus.UNVERIFIED
    assert "not evidence of absence" in limitations


def test_kubernetes_audit_fixture_mismatch_is_conflicting() -> None:
    observation = KubernetesAuditObserver().observe_resource_change(
        {
            "auditID": "k8s-audit-2",
            "verb": "delete",
            "stage": "ResponseComplete",
            "objectRef": {"resource": "pods", "namespace": "demo", "name": "other"},
            "responseStatus": {"code": 200},
        },
        resource="pods",
        namespace="demo",
        name="target",
        verb="delete",
    )

    assert observation.outcome == ObserverOutcome.CONFLICTING
    assert observation.verification_status == VerificationStatus.CONFLICTING
