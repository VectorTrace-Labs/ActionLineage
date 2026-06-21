from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from actionlineage.contracts import ContractEventRequirement, LineageContract, contract_to_dict
from actionlineage.demo import run_demo
from actionlineage.service import (
    JwtAuthenticator,
    OidcJwtAuthenticator,
    ServiceAuthError,
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


def test_local_health_reports_ok_and_projection_missing(tmp_path) -> None:
    demo = run_demo(tmp_path / "demo")
    ok = check_local_health(journal_path=demo.journal_path, database_path=demo.database_path)
    degraded = check_local_health(
        journal_path=demo.journal_path,
        database_path=tmp_path / "missing.sqlite",
    )

    assert ok.ok
    assert not degraded.ok
    assert degraded.issues[0].code == "projection_missing"


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


def test_service_contract_and_detection_endpoints(tmp_path: Path) -> None:
    demo = run_demo(tmp_path / "demo")
    client = _client(
        demo.journal_path,
        demo.database_path,
        token="reader",
        roles=frozenset({ServiceRole.READ}),
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


def test_service_detection_endpoint_rejects_malformed_rule_ids(tmp_path: Path) -> None:
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
    export_root=None,
) -> TestClient:
    authenticator = StaticTokenAuthenticator(
        tokens={
            token: ServicePrincipal(
                principal_id=token,
                roles=roles,
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


class FakeSigningKey:
    key = JWT_HS256_KEY


class FakeJwkClient:
    def __init__(self, url: str) -> None:
        self.url = url

    def get_signing_key_from_jwt(self, token: str) -> FakeSigningKey:
        assert token
        return FakeSigningKey()
