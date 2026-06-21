from __future__ import annotations

import tomllib
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def test_docker_compose_runs_optional_service_factory() -> None:
    dockerfile = (PROJECT_ROOT / "deploy/docker/Dockerfile").read_text(encoding="utf-8")
    compose = (PROJECT_ROOT / "deploy/docker/compose.yaml").read_text(encoding="utf-8")

    assert 'pip install --no-cache-dir ".[service]"' in dockerfile
    assert "actionlineage.service.runtime:create_service_app_from_env" in compose
    assert "--factory" in compose
    assert "ACTIONLINEAGE_SERVICE_TOKEN: local-token" in compose
    assert "actionlineage-data:/data" in compose


def test_ci_builds_and_smoke_tests_docker_image() -> None:
    workflow = (PROJECT_ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")

    assert "container:" in workflow
    assert "docker build -f deploy/docker/Dockerfile -t actionlineage:ci ." in workflow
    assert "docker run --rm actionlineage:ci version" in workflow
    assert "docker run --rm actionlineage:ci doctor" in workflow
    assert "actionlineage:ci demo run --output-dir /artifacts/demo" in workflow
    assert "actionlineage:ci journal verify /artifacts/demo/evidence.jsonl" in workflow
    assert "actionlineage:ci projection timeline /artifacts/demo/projection.sqlite" in workflow
    assert "actionlineage:ci contract validate" in workflow


def test_kubernetes_manifest_preserves_local_first_service_posture() -> None:
    manifest = (PROJECT_ROOT / "deploy/kubernetes/actionlineage-service.yaml").read_text(
        encoding="utf-8"
    )

    assert "kind: PersistentVolumeClaim" in manifest
    assert "ACTIONLINEAGE_JOURNAL_PATH" in manifest
    assert "value: /data/actionlineage.journal" in manifest
    assert "ACTIONLINEAGE_DATABASE_PATH" in manifest
    assert "value: /data/projection.sqlite" in manifest
    assert "secretKeyRef:" in manifest
    assert "readOnlyRootFilesystem: true" in manifest
    assert "allowPrivilegeEscalation: false" in manifest
    assert "runAsNonRoot: true" in manifest
    assert "path: /health" in manifest
    assert "actionlineage.service.runtime:create_service_app_from_env" in manifest


def test_helm_chart_contains_service_storage_and_security_templates() -> None:
    chart_dir = PROJECT_ROOT / "deploy/helm/actionlineage"
    chart = chart_dir / "Chart.yaml"
    values = chart_dir / "values.yaml"
    deployment = chart_dir / "templates/deployment.yaml"
    service = chart_dir / "templates/service.yaml"
    secret = chart_dir / "templates/secret.yaml"
    pvc = chart_dir / "templates/pvc.yaml"

    assert chart.exists()
    assert values.exists()
    assert deployment.exists()
    assert service.exists()
    assert secret.exists()
    assert pvc.exists()

    pyproject = tomllib.loads((PROJECT_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    assert f'appVersion: "{pyproject["project"]["version"]}"' in chart.read_text(encoding="utf-8")

    values_text = values.read_text(encoding="utf-8")
    deployment_text = deployment.read_text(encoding="utf-8")
    assert "repository: ghcr.io/vectortrace-labs/actionlineage" in values_text
    assert "journalPath: /data/actionlineage.journal" in values_text
    assert "databasePath: /data/projection.sqlite" in values_text
    assert "readOnlyRootFilesystem: true" in values_text
    assert "actionlineage.service.runtime:create_service_app_from_env" in deployment_text
    assert "secretKeyRef:" in deployment_text
    assert "persistentVolumeClaim:" in deployment_text
