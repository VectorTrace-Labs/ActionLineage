from __future__ import annotations

import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier

import pytest
from fastapi.testclient import TestClient

import actionlineage.service.api as service_api_module
from actionlineage.contracts import ContractEventRequirement, LineageContract, contract_to_dict
from actionlineage.demo import run_demo
from actionlineage.journal import LocalJournal
from actionlineage.service import (
    HealthIssue,
    JwtAuthenticator,
    OidcJwtAuthenticator,
    ServiceAuthError,
    ServiceCapability,
    ServicePrincipal,
    ServiceRole,
    ServiceRuntimeConfigError,
    ServiceTenant,
    StaticTokenAuthenticator,
    TenantRegistry,
    TenantRoleBinding,
    check_local_health,
    create_app,
    create_service_app_from_env,
    require_capability,
    require_role,
    require_tenant_role,
)

JWT_HS256_KEY = "test-key-material-for-hs256-000000"
JWT_OTHER_HS256_KEY = "other-key-material-for-hs256-0000"


def test_static_token_authenticator_and_rbac() -> None:
    principal = ServicePrincipal(
        principal_id="analyst",
        roles=frozenset({ServiceRole.READ, ServiceRole.EXPORT}),
    )
    authenticator = StaticTokenAuthenticator(tokens={"token": principal})

    assert authenticator.authenticate("token") == principal
    require_role(principal, ServiceRole.READ)
    require_role(principal, ServiceRole.EXPORT)
    with pytest.raises(ServiceAuthError):
        authenticator.authenticate("bad")
    with pytest.raises(ServiceAuthError):
        require_role(principal, ServiceRole.ADMIN)


def test_role_bundles_do_not_use_ordinal_privilege_inheritance() -> None:
    reader = ServicePrincipal(principal_id="reader", roles=frozenset({ServiceRole.READ}))
    writer = ServicePrincipal(principal_id="writer", roles=frozenset({ServiceRole.WRITE}))
    exporter = ServicePrincipal(principal_id="exporter", roles=frozenset({ServiceRole.EXPORT}))
    detector = ServicePrincipal(
        principal_id="detector",
        roles=frozenset(),
        capabilities=frozenset({ServiceCapability.DETECTIONS_RUN}),
    )
    tenant_manager = ServicePrincipal(
        principal_id="tenant-manager",
        roles=frozenset(),
        capabilities=frozenset({ServiceCapability.TENANTS_MANAGE}),
    )

    require_capability(reader, ServiceCapability.EVENTS_READ)
    require_capability(writer, ServiceCapability.EVENTS_WRITE)
    require_capability(exporter, ServiceCapability.CASES_EXPORT)
    require_capability(detector, ServiceCapability.DETECTIONS_RUN)
    require_capability(tenant_manager, ServiceCapability.TENANTS_MANAGE)

    with pytest.raises(ServiceAuthError):
        require_capability(reader, ServiceCapability.EVENTS_WRITE)
    with pytest.raises(ServiceAuthError):
        require_capability(reader, ServiceCapability.PROJECTIONS_REBUILD)
    with pytest.raises(ServiceAuthError):
        require_capability(writer, ServiceCapability.CASES_EXPORT)
    with pytest.raises(ServiceAuthError):
        require_capability(exporter, ServiceCapability.EVENTS_WRITE)
    with pytest.raises(ServiceAuthError):
        require_capability(detector, ServiceCapability.EVENTS_READ)
    with pytest.raises(ServiceAuthError):
        require_capability(tenant_manager, ServiceCapability.ADMIN_CONFIGURE)


def test_tenant_registry_enforces_tenant_scoped_roles() -> None:
    principal = ServicePrincipal(
        principal_id="analyst",
        roles=frozenset({ServiceRole.READ, ServiceRole.WRITE}),
    )
    registry = TenantRegistry(
        tenants=(
            ServiceTenant(tenant_id="tenant-a", display_name="Tenant A"),
            ServiceTenant(tenant_id="tenant-b", display_name="Tenant B"),
        ),
        bindings=(
            TenantRoleBinding(
                tenant_id="tenant-a",
                principal_id="analyst",
                roles=frozenset({ServiceRole.READ}),
            ),
        ),
    )

    read_decision = registry.decide(
        principal,
        tenant_id="tenant-a",
        required_role=ServiceRole.READ,
    )
    write_decision = registry.decide(
        principal,
        tenant_id="tenant-a",
        required_role=ServiceRole.WRITE,
    )
    other_tenant_decision = registry.decide(
        principal,
        tenant_id="tenant-b",
        required_role=ServiceRole.READ,
    )

    assert read_decision.allowed is True
    assert write_decision.allowed is False
    assert write_decision.reason == "tenant_binding_missing"
    assert other_tenant_decision.allowed is False
    assert other_tenant_decision.reason == "tenant_binding_missing"
    assert registry.as_dict()["bindings"][0]["roles"] == ["read"]


def test_require_tenant_role_rejects_unknown_tenant() -> None:
    principal = ServicePrincipal(
        principal_id="admin",
        roles=frozenset({ServiceRole.ADMIN}),
    )
    registry = TenantRegistry(
        tenants=(ServiceTenant(tenant_id="tenant-a", display_name="Tenant A"),),
        bindings=(
            TenantRoleBinding(
                tenant_id="tenant-a",
                principal_id="admin",
                roles=frozenset({ServiceRole.ADMIN}),
            ),
        ),
    )

    allowed = require_tenant_role(
        registry,
        principal,
        tenant_id="tenant-a",
        role=ServiceRole.EXPORT,
    )

    assert allowed.allowed is True
    with pytest.raises(ServiceAuthError, match="tenant-missing:read"):
        require_tenant_role(
            registry,
            principal,
            tenant_id="tenant-missing",
            role=ServiceRole.READ,
        )


def test_jwt_authenticator_maps_claims_to_principal() -> None:
    import jwt

    token = jwt.encode(
        {
            "sub": "jwt-analyst",
            "roles": ["read", "export"],
            "iss": "https://issuer.example.invalid",
            "aud": "actionlineage-service",
        },
        JWT_HS256_KEY,
        algorithm="HS256",
    )
    authenticator = JwtAuthenticator(
        verification_key=JWT_HS256_KEY,
        algorithms=("HS256",),
        issuer="https://issuer.example.invalid",
        audience="actionlineage-service",
    )

    principal = authenticator.authenticate(token)

    assert principal.principal_id == "jwt-analyst"
    assert principal.has_role(ServiceRole.READ)
    assert principal.has_role(ServiceRole.EXPORT)


def test_jwt_authenticator_rejects_malformed_roles_and_capabilities() -> None:
    import jwt

    authenticator = JwtAuthenticator(
        verification_key=JWT_HS256_KEY,
        algorithms=("HS256",),
    )
    bad_role_token = jwt.encode(
        {"sub": "jwt-analyst", "roles": ["read", 7]},
        JWT_HS256_KEY,
        algorithm="HS256",
    )
    bad_capability_token = jwt.encode(
        {
            "sub": "jwt-analyst",
            "roles": ["read"],
            "capabilities": ["detections:run", "events:delete"],
        },
        JWT_HS256_KEY,
        algorithm="HS256",
    )

    with pytest.raises(ServiceAuthError, match="invalid service JWT"):
        authenticator.authenticate(bad_role_token)
    with pytest.raises(ServiceAuthError, match="invalid service JWT"):
        authenticator.authenticate(bad_capability_token)


def test_jwt_authenticator_rejects_invalid_signature_without_leaking_claims() -> None:
    import jwt

    token = jwt.encode(
        {"sub": "sensitive-user", "roles": ["admin"]},
        JWT_OTHER_HS256_KEY,
        algorithm="HS256",
    )
    authenticator = JwtAuthenticator(
        verification_key=JWT_HS256_KEY,
        algorithms=("HS256",),
    )

    with pytest.raises(ServiceAuthError) as exc_info:
        authenticator.authenticate(token)

    assert str(exc_info.value) == "invalid service JWT"
    assert "sensitive-user" not in str(exc_info.value)
    assert "admin" not in str(exc_info.value)


def test_oidc_jwt_authenticator_uses_injected_jwk_client() -> None:
    import jwt

    token = jwt.encode(
        {
            "sub": "oidc-analyst",
            "roles": "read export",
            "iss": "https://issuer.example.invalid",
            "aud": "actionlineage-service",
        },
        JWT_HS256_KEY,
        algorithm="HS256",
        headers={"kid": "demo-key"},
    )
    authenticator = OidcJwtAuthenticator(
        jwks_url="https://issuer.example.invalid/.well-known/jwks.json",
        algorithms=("HS256",),
        issuer="https://issuer.example.invalid",
        audience="actionlineage-service",
        jwk_client_factory=FakeJwkClient,
    )

    principal = authenticator.authenticate(token)

    assert principal.principal_id == "oidc-analyst"
    assert principal.roles == frozenset({ServiceRole.READ, ServiceRole.EXPORT})


def test_local_health_reports_ok_and_projection_missing(tmp_path: Path) -> None:
    demo = run_demo(tmp_path / "demo")
    ok = check_local_health(journal_path=demo.journal_path, database_path=demo.database_path)
    degraded = check_local_health(
        journal_path=demo.journal_path,
        database_path=tmp_path / "missing.sqlite",
    )

    assert ok.ok
    assert not degraded.ok
    assert degraded.issues[0].code == "projection_missing"


def test_health_issue_as_dict_returns_defensive_details_copy() -> None:
    issue = HealthIssue(
        code="demo",
        message="demo issue",
        details={"nested": {"status": "original"}},
    )
    data = issue.as_dict()
    details = data["details"]
    assert isinstance(details, dict)
    nested = details["nested"]
    assert isinstance(nested, dict)

    nested["status"] = "tampered"

    repeated_details = issue.as_dict()["details"]
    assert isinstance(repeated_details, dict)
    repeated_nested = repeated_details["nested"]
    assert isinstance(repeated_nested, dict)
    assert repeated_nested["status"] == "original"


def test_service_health_split_and_corrupt_journal_readiness(tmp_path: Path) -> None:
    demo = run_demo(tmp_path / "demo")
    _tamper_record_three(demo.journal_path)
    client = _client(
        demo.journal_path,
        demo.database_path,
        token="reader",
        roles=frozenset({ServiceRole.READ}),
    )

    live = client.get("/live")
    ready = client.get("/ready")
    health = client.get("/health")

    assert live.status_code == 200
    assert live.json()["state"] == "live"
    assert ready.status_code == 503
    assert health.status_code == 503
    assert ready.json()["issues"][0]["code"] == "journal_invalid"
    assert ready.json()["issues"][0]["details"]["verification"]["issues"][0]["code"] == (
        "event_hash_mismatch"
    )


def test_service_readiness_rejects_unrebuilt_projection(tmp_path: Path) -> None:
    journal_path = tmp_path / "events.jsonl"
    database_path = tmp_path / "projection.sqlite"
    _write_private_bytes(journal_path, b"")
    _write_private_bytes(database_path, b"")
    client = _client(
        journal_path,
        database_path,
        token="reader",
        roles=frozenset({ServiceRole.READ}),
    )

    ready = client.get("/ready")

    assert ready.status_code == 503
    assert ready.json()["issues"][0]["code"] == "projection_rebuild_required"


def test_service_readiness_rejects_malformed_journal(tmp_path: Path) -> None:
    journal_path = tmp_path / "events.jsonl"
    database_path = tmp_path / "projection.sqlite"
    _write_private_bytes(journal_path, b'{"not":"an actionlineage event"}\n')
    _write_private_bytes(database_path, b"")
    client = _client(
        journal_path,
        database_path,
        token="reader",
        roles=frozenset({ServiceRole.READ}),
    )

    ready = client.get("/ready")

    assert ready.status_code == 503
    assert ready.json()["issues"][0]["code"] == "journal_invalid"
    assert ready.json()["issues"][0]["details"]["verification"]["issues"][0]["code"] == (
        "parse_error"
    )


def test_service_readiness_reports_locked_journal_without_failing_liveness(
    tmp_path: Path,
) -> None:
    if os.name != "posix":
        pytest.skip("kernel advisory lock contention is covered on POSIX platforms")
    demo = run_demo(tmp_path / "demo")
    lock_path = demo.journal_path.with_suffix(f"{demo.journal_path.suffix}.lock")
    holder = _start_lock_holder(lock_path)
    try:
        client = _client(
            demo.journal_path,
            demo.database_path,
            token="reader",
            roles=frozenset({ServiceRole.READ}),
        )

        live = client.get("/live")
        ready = client.get("/ready")
    finally:
        holder.terminate()
        try:
            holder.wait(timeout=5)
        except subprocess.TimeoutExpired:
            holder.kill()
            holder.wait(timeout=5)

    assert live.status_code == 200
    assert ready.status_code == 503
    assert ready.json()["issues"][0]["code"] == "journal_unavailable"


def test_create_app_factory_is_available_with_optional_dependencies(tmp_path: Path) -> None:
    demo = run_demo(tmp_path / "demo")
    authenticator = StaticTokenAuthenticator(
        tokens={
            "reader": ServicePrincipal(
                principal_id="reader",
                roles=frozenset({ServiceRole.READ}),
            )
        }
    )

    app = create_app(
        journal_path=demo.journal_path,
        database_path=demo.database_path,
        authenticator=authenticator,
    )

    assert app.title == "ActionLineage Evidence Service"


def test_service_runtime_factory_reads_environment(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    journal_path = tmp_path / "runtime.journal"
    database_path = tmp_path / "runtime.sqlite"
    monkeypatch.setenv("ACTIONLINEAGE_SERVICE_TOKEN", "runtime-token")
    monkeypatch.setenv("ACTIONLINEAGE_JOURNAL_PATH", str(journal_path))
    monkeypatch.setenv("ACTIONLINEAGE_DATABASE_PATH", str(database_path))
    monkeypatch.setenv("ACTIONLINEAGE_SERVICE_PRINCIPAL", "runtime-admin")
    monkeypatch.setenv("ACTIONLINEAGE_SERVICE_ROLES", "read,write,export")

    app = create_service_app_from_env()

    assert app.title == "ActionLineage Evidence Service"


def test_service_runtime_factory_requires_explicit_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("ACTIONLINEAGE_SERVICE_TOKEN", raising=False)

    with pytest.raises(ServiceRuntimeConfigError, match="ACTIONLINEAGE_SERVICE_TOKEN"):
        create_service_app_from_env()


def test_service_runtime_factory_rejects_unknown_roles(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ACTIONLINEAGE_SERVICE_TOKEN", "runtime-token")
    monkeypatch.setenv("ACTIONLINEAGE_SERVICE_ROLES", "read,root")

    with pytest.raises(ServiceRuntimeConfigError, match="unsupported service role"):
        create_service_app_from_env()


def test_service_ingest_endpoint_writes_and_rebuilds_projection(tmp_path: Path) -> None:
    demo = run_demo(tmp_path / "demo")
    client = _client(
        demo.journal_path,
        demo.database_path,
        token="writer",
        roles=frozenset({ServiceRole.WRITE, ServiceRole.READ}),
    )

    response = client.post(
        "/ingest",
        headers={"Authorization": "Bearer writer"},
        json={
            "correlation": {"trace_id": "trace_service", "run_id": "run_service"},
            "records": [
                {
                    "idempotency_key": "service-record-1",
                    "event_type": "agent.intent.recorded",
                    "payload": {"intent": {"summary": "service ingest"}},
                    "source_kind": "external_json",
                    "sort_key": "001",
                }
            ],
        },
    )

    assert response.status_code == 200
    assert response.json()["imported_count"] == 1

    timeline = client.get(
        "/timeline",
        params={"trace_id": "trace_service"},
        headers={"Authorization": "Bearer writer"},
    )
    assert timeline.status_code == 200
    assert timeline.json()["event_count"] == 1


def test_service_ingest_replay_reports_duplicate_without_new_append(tmp_path: Path) -> None:
    demo = run_demo(tmp_path / "demo")
    client = _client(
        demo.journal_path,
        demo.database_path,
        token="writer",
        roles=frozenset({ServiceRole.WRITE, ServiceRole.READ}),
    )
    body = {
        "correlation": {"trace_id": "trace_service", "run_id": "run_service"},
        "records": [
            {
                "idempotency_key": "service-record-replay",
                "event_type": "agent.intent.recorded",
                "payload": {"intent": {"summary": "service ingest"}},
                "source_kind": "external_json",
                "sort_key": "001",
            }
        ],
    }
    initial_count = LocalJournal(demo.journal_path).verified_snapshot().record_count

    first = client.post("/ingest", headers={"Authorization": "Bearer writer"}, json=body)
    second = client.post(
        "/ingest",
        headers={"Authorization": "Bearer writer", "X-Request-ID": "different-response"},
        json=body,
    )
    snapshot = LocalJournal(demo.journal_path).verified_snapshot()

    assert first.status_code == 200
    assert first.json()["imported_count"] == 1
    assert second.status_code == 200
    assert second.json()["imported_count"] == 0
    assert second.json()["duplicate_count"] == 1
    assert second.json()["outcomes"][0]["status"] == "duplicate"
    assert snapshot.record_count == initial_count + 1


def test_service_ingest_rejects_same_idempotency_key_for_different_record(
    tmp_path: Path,
) -> None:
    demo = run_demo(tmp_path / "demo")
    client = _client(
        demo.journal_path,
        demo.database_path,
        token="writer",
        roles=frozenset({ServiceRole.WRITE, ServiceRole.READ}),
    )
    original = {
        "correlation": {"trace_id": "trace_service", "run_id": "run_service"},
        "records": [
            {
                "idempotency_key": "service-record-conflict",
                "event_type": "agent.intent.recorded",
                "payload": {"intent": {"summary": "service ingest"}},
                "source_kind": "external_json",
                "sort_key": "001",
            }
        ],
    }
    changed = {
        **original,
        "records": [
            {
                **original["records"][0],
                "payload": {"intent": {"summary": "changed ingest"}},
            }
        ],
    }

    first = client.post("/ingest", headers={"Authorization": "Bearer writer"}, json=original)
    second = client.post("/ingest", headers={"Authorization": "Bearer writer"}, json=changed)

    assert first.status_code == 200
    assert second.status_code == 409
    assert second.json()["conflict_count"] == 1
    assert second.json()["outcomes"][0]["status"] == "conflict"


def test_service_ingest_partial_batch_uses_multi_status(tmp_path: Path) -> None:
    demo = run_demo(tmp_path / "demo")
    client = _client(
        demo.journal_path,
        demo.database_path,
        token="writer",
        roles=frozenset({ServiceRole.WRITE, ServiceRole.READ}),
    )
    initial_count = LocalJournal(demo.journal_path).verified_snapshot().record_count

    response = client.post(
        "/ingest",
        headers={"Authorization": "Bearer writer"},
        json={
            "correlation": {"trace_id": "trace_service", "run_id": "run_service"},
            "records": [
                {
                    "idempotency_key": "service-record-partial-ok",
                    "event_type": "agent.intent.recorded",
                    "payload": {"intent": {"summary": "service ingest"}},
                    "source_kind": "external_json",
                    "sort_key": "001",
                },
                {
                    "idempotency_key": "service-record-partial-invalid",
                    "event_type": "agent.intent.recorded",
                    "payload": {"oversized": [0] * 4097},
                    "source_kind": "external_json",
                    "sort_key": "002",
                },
            ],
        },
    )
    snapshot = LocalJournal(demo.journal_path).verified_snapshot()

    assert response.status_code == 207
    assert response.json()["ok"] is False
    assert response.json()["imported_count"] == 1
    assert response.json()["failed_count"] == 1
    assert response.json()["journal_committed"] is True
    assert snapshot.record_count == initial_count + 1


def test_service_ingest_reports_projection_stale_after_committed_append(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    demo = run_demo(tmp_path / "demo")
    client = _client(
        demo.journal_path,
        demo.database_path,
        token="writer",
        roles=frozenset({ServiceRole.WRITE, ServiceRole.READ}),
    )
    initial_count = LocalJournal(demo.journal_path).verified_snapshot().record_count

    def fail_rebuild(*_args: object, **_kwargs: object) -> None:
        raise service_api_module.ProjectionError("simulated projection rebuild failure")

    monkeypatch.setattr(service_api_module, "rebuild_projection", fail_rebuild)
    response = client.post(
        "/ingest",
        headers={"Authorization": "Bearer writer"},
        json={
            "correlation": {"trace_id": "trace_service", "run_id": "run_service"},
            "records": [
                {
                    "idempotency_key": "service-record-projection-stale",
                    "event_type": "agent.intent.recorded",
                    "payload": {"intent": {"summary": "service ingest"}},
                    "source_kind": "external_json",
                    "sort_key": "001",
                }
            ],
        },
    )
    snapshot = LocalJournal(demo.journal_path).verified_snapshot()

    assert response.status_code == 503
    assert response.json()["ok"] is False
    assert response.json()["imported_count"] == 1
    assert response.json()["journal_committed"] is True
    assert response.json()["projection"]["state"] == "stale"
    assert response.json()["projection"]["error"] == "projection_rebuild_failed"
    assert snapshot.record_count == initial_count + 1


def test_service_concurrent_duplicate_ingest_reports_duplicate_not_failure(
    tmp_path: Path,
) -> None:
    demo = run_demo(tmp_path / "demo")
    initial_count = LocalJournal(demo.journal_path).verified_snapshot().record_count
    authenticator = StaticTokenAuthenticator(
        tokens={
            "writer": ServicePrincipal(
                principal_id="writer",
                roles=frozenset({ServiceRole.WRITE, ServiceRole.READ}),
            )
        }
    )
    app = create_app(
        journal_path=demo.journal_path,
        database_path=demo.database_path,
        authenticator=authenticator,
    )
    barrier = Barrier(2)
    body = {
        "correlation": {"trace_id": "trace_service", "run_id": "run_service"},
        "records": [
            {
                "idempotency_key": "service-record-concurrent",
                "event_type": "agent.intent.recorded",
                "payload": {"intent": {"summary": "service ingest"}},
                "source_kind": "external_json",
                "sort_key": "001",
            }
        ],
    }

    def post_once() -> dict[str, object]:
        barrier.wait(timeout=5)
        with TestClient(app) as client:
            response = client.post("/ingest", headers={"Authorization": "Bearer writer"}, json=body)
        assert response.status_code == 200
        return response.json()

    with ThreadPoolExecutor(max_workers=2) as executor:
        responses = list(executor.map(lambda _: post_once(), range(2)))
    snapshot = LocalJournal(demo.journal_path).verified_snapshot()

    assert sorted(response["imported_count"] for response in responses) == [0, 1]
    assert sorted(response["duplicate_count"] for response in responses) == [0, 1]
    assert {response["failed_count"] for response in responses} == {0}
    assert snapshot.record_count == initial_count + 1


def test_service_ingest_preserves_authenticated_provenance_for_asserted_principal(
    tmp_path: Path,
) -> None:
    demo = run_demo(tmp_path / "demo")
    client = _client(
        demo.journal_path,
        demo.database_path,
        token="writer-a",
        roles=frozenset({ServiceRole.WRITE, ServiceRole.READ}),
    )

    response = client.post(
        "/ingest",
        headers={"Authorization": "Bearer writer-a", "X-Request-ID": "req-test-1"},
        json={
            "correlation": {"trace_id": "trace_service", "run_id": "run_service"},
            "principal": {"principal_id": "principal-b", "principal_type": "human"},
            "source": {"component": "client-asserted", "instance_id": "source-b", "version": "1"},
            "records": [
                {
                    "idempotency_key": "service-record-provenance",
                    "event_type": "agent.intent.recorded",
                    "payload": {"intent": {"summary": "service ingest"}},
                    "source_kind": "external_json",
                    "sort_key": "001",
                }
            ],
        },
    )

    assert response.status_code == 200
    event = LocalJournal(demo.journal_path).verified_snapshot().events[-1]
    ingested_by = event.payload["ingested_by"]
    assert event.principal.principal_id == "principal-b"
    assert event.source.component == "client-asserted"
    assert ingested_by["authenticated_principal"] == "writer-a"
    assert ingested_by["request_id"] == "req-test-1"
    assert "writer-a" in ingested_by["credential_identifier"]


def test_service_ingest_rejects_client_supplied_ingested_by(tmp_path: Path) -> None:
    demo = run_demo(tmp_path / "demo")
    client = _client(
        demo.journal_path,
        demo.database_path,
        token="writer",
        roles=frozenset({ServiceRole.WRITE}),
    )

    response = client.post(
        "/ingest",
        headers={"Authorization": "Bearer writer"},
        json={
            "correlation": {"trace_id": "trace_service", "run_id": "run_service"},
            "records": [
                {
                    "idempotency_key": "service-record-override",
                    "event_type": "agent.intent.recorded",
                    "payload": {
                        "intent": {"summary": "service ingest"},
                        "ingested_by": {"authenticated_principal": "attacker"},
                    },
                    "source_kind": "external_json",
                }
            ],
        },
    )

    assert response.status_code == 400
    assert "ingested_by is server-controlled" in response.json()["detail"]


def test_service_ingest_rejects_unprivileged_trusted_evidence(tmp_path: Path) -> None:
    demo = run_demo(tmp_path / "demo")
    writer = _client(
        demo.journal_path,
        demo.database_path,
        token="writer",
        roles=frozenset({ServiceRole.WRITE}),
    )
    admin = _client(
        demo.journal_path,
        demo.database_path,
        token="admin",
        roles=frozenset({ServiceRole.ADMIN}),
    )
    body = {
        "correlation": {"trace_id": "trace_service", "run_id": "run_service"},
        "classification": {"sensitivity": "internal", "trust": "trusted"},
        "records": [
            {
                "idempotency_key": "service-record-trusted",
                "event_type": "agent.intent.recorded",
                "payload": {"intent": {"summary": "trusted ingest"}},
                "source_kind": "external_json",
            }
        ],
    }

    denied = writer.post("/ingest", headers={"Authorization": "Bearer writer"}, json=body)
    allowed = admin.post("/ingest", headers={"Authorization": "Bearer admin"}, json=body)

    assert denied.status_code == 403
    assert "admin role required" in denied.json()["detail"]
    assert allowed.status_code == 200
    assert LocalJournal(demo.journal_path).verified_snapshot().events[-1].classification.trust == (
        "trusted"
    )


def test_service_ingest_does_not_persist_or_echo_bearer_token(tmp_path: Path) -> None:
    demo = run_demo(tmp_path / "demo")
    raw_token = "writer-secret-token-value"
    client = _client(
        demo.journal_path,
        demo.database_path,
        token=raw_token,
        principal_id="writer-no-secret",
        roles=frozenset({ServiceRole.WRITE, ServiceRole.READ}),
    )

    ingest = client.post(
        "/ingest",
        headers={"Authorization": f"Bearer {raw_token}"},
        json={
            "correlation": {"trace_id": "trace_service", "run_id": "run_service"},
            "records": [
                {
                    "idempotency_key": "service-record-no-secret",
                    "event_type": "agent.intent.recorded",
                    "payload": {"intent": {"summary": "service ingest"}},
                    "source_kind": "external_json",
                }
            ],
        },
    )
    events = client.get("/events", headers={"Authorization": f"Bearer {raw_token}"})
    contract = LineageContract(
        name="service-contract",
        events=(ContractEventRequirement(event_type="agent.intent.recorded"),),
    )
    validation = client.post(
        "/contracts/validate",
        headers={"Authorization": f"Bearer {raw_token}"},
        json={"contract": contract_to_dict(contract)},
    )

    assert ingest.status_code == 200
    assert events.status_code == 200
    assert validation.status_code == 200
    assert raw_token not in demo.journal_path.read_text(encoding="utf-8")
    assert raw_token not in str(events.json())
    assert raw_token not in str(validation.json())


def test_service_ingested_by_is_covered_by_canonical_hash(tmp_path: Path) -> None:
    demo = run_demo(tmp_path / "demo")
    client = _client(
        demo.journal_path,
        demo.database_path,
        token="writer",
        roles=frozenset({ServiceRole.WRITE}),
    )
    response = client.post(
        "/ingest",
        headers={"Authorization": "Bearer writer"},
        json={
            "correlation": {"trace_id": "trace_service", "run_id": "run_service"},
            "records": [
                {
                    "idempotency_key": "service-record-hash",
                    "event_type": "agent.intent.recorded",
                    "payload": {"intent": {"summary": "service ingest"}},
                    "source_kind": "external_json",
                }
            ],
        },
    )
    assert response.status_code == 200

    text = demo.journal_path.read_text(encoding="utf-8")
    demo.journal_path.write_text(
        text.replace('"authenticated_principal":"writer"', '"authenticated_principal":"other"'),
        encoding="utf-8",
    )

    verification = LocalJournal(demo.journal_path).verify()
    assert not verification.ok
    assert verification.issues[0].code == "event_hash_mismatch"


def test_service_contract_and_detection_endpoints(tmp_path: Path) -> None:
    demo = run_demo(tmp_path / "demo")
    client = _client(
        demo.journal_path,
        demo.database_path,
        token="reader",
        roles=frozenset({ServiceRole.READ}),
        capabilities=frozenset({ServiceCapability.DETECTIONS_RUN}),
    )
    contract = LineageContract(
        name="service-contract",
        events=(ContractEventRequirement(event_type="agent.intent.recorded"),),
    )

    contract_response = client.post(
        "/contracts/validate",
        headers={"Authorization": "Bearer reader"},
        json={"contract": contract_to_dict(contract)},
    )
    detection_response = client.post(
        "/detections/evaluate",
        headers={"Authorization": "Bearer reader"},
        json={"rule_ids": ["AL-DET-003"]},
    )

    assert contract_response.status_code == 200
    assert contract_response.json()["ok"] is True
    assert detection_response.status_code == 200
    assert detection_response.json()["rules_evaluated"] == ["AL-DET-003"]
    assert detection_response.json()["match_count"] == 1


def test_service_read_only_principal_cannot_run_detections(tmp_path: Path) -> None:
    demo = run_demo(tmp_path / "demo")
    client = _client(
        demo.journal_path,
        demo.database_path,
        token="reader",
        roles=frozenset({ServiceRole.READ}),
    )

    response = client.post(
        "/detections/evaluate",
        headers={"Authorization": "Bearer reader"},
        json={"rule_ids": ["AL-DET-003"]},
    )

    assert response.status_code == 403
    assert "detections:run" in response.json()["detail"]


def test_service_journal_dependent_endpoints_fail_closed_on_corruption(tmp_path: Path) -> None:
    demo = run_demo(tmp_path / "demo")
    _tamper_record_three(demo.journal_path)
    client = _client(
        demo.journal_path,
        demo.database_path,
        token="reader",
        roles=frozenset({ServiceRole.READ}),
        capabilities=frozenset({ServiceCapability.DETECTIONS_RUN}),
    )
    contract = LineageContract(
        name="service-contract",
        events=(ContractEventRequirement(event_type="agent.intent.recorded"),),
    )

    events = client.get("/events", headers={"Authorization": "Bearer reader"})
    contract_response = client.post(
        "/contracts/validate",
        headers={"Authorization": "Bearer reader"},
        json={"contract": contract_to_dict(contract)},
    )
    detection_response = client.post(
        "/detections/evaluate",
        headers={"Authorization": "Bearer reader"},
        json={"rule_ids": ["AL-DET-003"]},
    )

    for response in (events, contract_response, detection_response):
        assert response.status_code == 503
        assert response.json()["detail"]["error"] == "journal_integrity_error"
        assert response.json()["detail"]["verification"]["issues"][0]["code"] == (
            "event_hash_mismatch"
        )


def test_service_detection_endpoint_rejects_malformed_rule_ids(tmp_path: Path) -> None:
    demo = run_demo(tmp_path / "demo")
    client = _client(
        demo.journal_path,
        demo.database_path,
        token="reader",
        roles=frozenset({ServiceRole.READ}),
        capabilities=frozenset({ServiceCapability.DETECTIONS_RUN}),
    )

    response = client.post(
        "/detections/evaluate",
        headers={"Authorization": "Bearer reader"},
        json={"rule_ids": "AL-DET-003"},
    )

    assert response.status_code == 400
    assert "rule_ids" in response.json()["detail"]


def test_service_export_case_is_confined_to_export_root(tmp_path: Path) -> None:
    demo = run_demo(tmp_path / "demo")
    export_root = tmp_path / "exports"
    client = _client(
        demo.journal_path,
        demo.database_path,
        token="exporter",
        roles=frozenset({ServiceRole.EXPORT}),
        export_root=export_root,
    )

    valid = client.post(
        "/export-case",
        headers={"Authorization": "Bearer exporter"},
        params={"output_dir": "case-1", "trace_id": demo.trace_id},
    )
    repeated = client.post(
        "/export-case",
        headers={"Authorization": "Bearer exporter"},
        params={"output_dir": "case-1", "trace_id": demo.trace_id},
    )
    traversal = client.post(
        "/export-case",
        headers={"Authorization": "Bearer exporter"},
        params={"output_dir": "../outside", "trace_id": demo.trace_id},
    )
    absolute = client.post(
        "/export-case",
        headers={"Authorization": "Bearer exporter"},
        params={"output_dir": str(tmp_path / "outside"), "trace_id": demo.trace_id},
    )

    assert valid.status_code == 200
    assert (export_root / "case-1" / "case.json").exists()
    assert repeated.status_code == 400
    assert "already exists" in repeated.json()["detail"]
    assert traversal.status_code == 400
    assert absolute.status_code == 400
    assert not (tmp_path / "outside").exists()


def _client(
    journal_path,
    database_path,
    *,
    token: str,
    roles: frozenset[ServiceRole],
    capabilities: frozenset[ServiceCapability] = frozenset(),
    principal_id: str | None = None,
    export_root=None,
) -> TestClient:
    authenticator = StaticTokenAuthenticator(
        tokens={
            token: ServicePrincipal(
                principal_id=principal_id or token,
                roles=roles,
                capabilities=capabilities,
            )
        }
    )
    return TestClient(
        create_app(
            journal_path=journal_path,
            database_path=database_path,
            authenticator=authenticator,
            export_root=export_root,
        )
    )


def _tamper_record_three(journal_path: Path) -> None:
    lines = journal_path.read_bytes().splitlines()
    lines[2] = lines[2].replace(b'"requested_state":"requested"', b'"requested_state":"tampered"')
    journal_path.write_bytes(b"\n".join(lines) + b"\n")


def _write_private_bytes(path: Path, payload: bytes) -> None:
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        os.write(fd, payload)
        os.fsync(fd)
    finally:
        os.close(fd)


def _start_lock_holder(lock_path: Path) -> subprocess.Popen[str]:
    code = """
from pathlib import Path
import sys
import time
import actionlineage.journal.local as local_journal_module

lock_path = Path(sys.argv[1])
with local_journal_module._journal_lock(
    lock_path,
    mode="exclusive",
    operation="readiness-test",
    timeout_seconds=1,
    poll_seconds=0.01,
):
    print("locked", flush=True)
    time.sleep(30)
"""
    process = subprocess.Popen(
        [sys.executable, "-c", code, str(lock_path)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    assert process.stdout is not None
    if process.stdout.readline().strip() != "locked":
        stderr = process.stderr.read() if process.stderr is not None else ""
        process.terminate()
        pytest.fail(f"failed to start lock holder: {stderr}")
    return process


class FakeSigningKey:
    key = JWT_HS256_KEY


class FakeJwkClient:
    def __init__(self, url: str) -> None:
        self.url = url

    def get_signing_key_from_jwt(self, token: str) -> FakeSigningKey:
        assert token
        return FakeSigningKey()
