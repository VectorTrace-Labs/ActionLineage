from __future__ import annotations

import shutil
import subprocess
import tomllib
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def test_docker_compose_runs_optional_service_factory() -> None:
    dockerfile = (PROJECT_ROOT / "deploy/docker/Dockerfile").read_text(encoding="utf-8")
    compose = (PROJECT_ROOT / "deploy/docker/compose.yaml").read_text(encoding="utf-8")

    assert "FROM python:3.12-slim@sha256:" in dockerfile
    assert "uv sync" in dockerfile
    assert "--locked" in dockerfile
    assert "--no-dev" in dockerfile
    assert "--extra service" in dockerfile
    assert "--no-install-project" in dockerfile
    assert "--python /usr/local/bin/python" in dockerfile
    assert "--no-managed-python" in dockerfile
    assert "--no-python-downloads" in dockerfile
    assert "uv build" in dockerfile
    assert "--out-dir /tmp/actionlineage-dist" in dockerfile
    assert "uv pip install" in dockerfile
    assert "--reinstall" in dockerfile
    assert "/tmp/actionlineage-dist/*.whl" in dockerfile
    assert "actionlineage.service.runtime:create_service_app_from_env" in compose
    assert "--factory" in compose
    assert "ACTIONLINEAGE_SERVICE_TOKEN: local-token" in compose
    assert "actionlineage-data:/data" in compose


def test_dockerignore_excludes_local_state_and_generated_artifacts() -> None:
    dockerignore = (PROJECT_ROOT / ".dockerignore").read_text(encoding="utf-8")

    for ignored in (".git", ".venv", "node_modules", "build", "dist", "cdk.out"):
        assert ignored in dockerignore.splitlines()


def test_operations_docs_label_deployment_examples_preview() -> None:
    operations = (PROJECT_ROOT / "docs/OPERATIONS.md").read_text(encoding="utf-8")

    assert "Deployment examples are preview support surfaces" in operations
    assert "do not make the service production-supported" in operations


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
    assert "/app/contracts/examples/outbound-http.json" in workflow


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
    assert "path: /ready" in manifest
    assert "path: /live" in manifest
    assert "ghcr.io/vectortrace-labs/actionlineage:0.1.0a6" in manifest
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
    assert f'tag: "{pyproject["project"]["version"]}"' in values_text
    assert 'digest: ""' in values_text
    assert "journalPath: /data/actionlineage.journal" in values_text
    assert "databasePath: /data/projection.sqlite" in values_text
    assert "readOnlyRootFilesystem: true" in values_text
    assert "{{ .Values.image.repository }}@{{ .Values.image.digest }}" in deployment_text
    assert "actionlineage.service.runtime:create_service_app_from_env" in deployment_text
    assert "path: /ready" in deployment_text
    assert "path: /live" in deployment_text
    assert "secretKeyRef:" in deployment_text
    assert "persistentVolumeClaim:" in deployment_text


def test_helm_template_supports_tag_and_digest_images() -> None:
    if shutil.which("helm") is None:
        return
    chart_dir = PROJECT_ROOT / "deploy/helm/actionlineage"
    tag_render = subprocess.run(
        ["helm", "template", "actionlineage", str(chart_dir)],
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    digest_render = subprocess.run(
        [
            "helm",
            "template",
            "actionlineage",
            str(chart_dir),
            "--set",
            "image.digest=sha256:abc123",
        ],
        check=True,
        capture_output=True,
        text=True,
    ).stdout

    assert 'image: "ghcr.io/vectortrace-labs/actionlineage:0.1.0a6"' in tag_render
    assert 'image: "ghcr.io/vectortrace-labs/actionlineage@sha256:abc123"' in digest_render
