from __future__ import annotations

import tomllib
from pathlib import Path

from typer.testing import CliRunner

import actionlineage
from actionlineage.cli import app

PROJECT_ROOT = Path(__file__).resolve().parents[2]
PYPROJECT = PROJECT_ROOT / "pyproject.toml"


def test_package_metadata_is_public_alpha_ready() -> None:
    project = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))["project"]

    assert project["version"] == "0.1.0a1"
    assert actionlineage.__version__ == "0.1.0a1"
    assert "Development Status :: 3 - Alpha" in project["classifiers"]
    assert "Development Status :: 5 - Production/Stable" not in project["classifiers"]
    assert "Typing :: Typed" in project["classifiers"]


def test_optional_extras_are_split_by_release_surface() -> None:
    optional = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))["project"][
        "optional-dependencies"
    ]

    assert {"adapters", "cloud", "console", "dev", "service"} <= set(optional)
    assert "fastapi>=0.115,<1" in optional["service"]
    assert "PyJWT[crypto]>=2.10,<3" in optional["service"]
    assert "uvicorn>=0.34,<1" in optional["service"]
    assert "mcp>=1.27,<2" in optional["adapters"]
    assert optional["console"] == []
    assert optional["cloud"] == []


def test_release_docs_are_present() -> None:
    required_docs = {
        "docs/API_REFERENCE.md",
        "docs/CLI_REFERENCE.md",
        "docs/SCHEMA_REFERENCE.md",
        "docs/TUTORIAL.md",
        "docs/MIGRATION.md",
        "docs/FAQ.md",
        "docs/RELEASE_CHECKLIST.md",
        "docs/QUALITY_SCORECARD.md",
        "docs/PERFECTION_PLAN.md",
        "docs/MATURITY.md",
        "docs/DECISIONS_REQUIRED.md",
        "SECURITY.md",
        "docs/PRIVACY.md",
    }

    missing = [path for path in required_docs if not (PROJECT_ROOT / path).exists()]

    assert missing == []


def test_specialized_issue_templates_are_present() -> None:
    template_dir = PROJECT_ROOT / ".github/ISSUE_TEMPLATE"
    expected = {
        "adapter_request.yml",
        "compatibility_report.yml",
        "contract_gap.yml",
        "detection_rule.yml",
        "security_report.yml",
    }

    assert expected <= {path.name for path in template_dir.glob("*.yml")}


def test_cli_version_matches_package_metadata() -> None:
    result = CliRunner().invoke(app, ["version"])

    assert result.exit_code == 0
    assert result.stdout.strip() == "0.1.0a1"


def test_readme_quickstart_uses_demo_aligned_contract() -> None:
    readme = (PROJECT_ROOT / "README.md").read_text(encoding="utf-8")

    assert "contracts/examples/outbound-http.json" in readme
    assert (
        "uv run actionlineage contract validate contracts/examples/restricted-exfiltration.json"
    ) not in readme
    assert "public alpha" in readme
    assert "Preview" in readme


def test_release_checklist_covers_required_gates() -> None:
    checklist = (PROJECT_ROOT / "docs/RELEASE_CHECKLIST.md").read_text(encoding="utf-8")

    for command in (
        "uv run ruff check .",
        "uv run ruff format --check .",
        "uv run mypy src",
        "uv run pytest",
        "scripts/check_claims_language.py",
        "scripts/secret_scan.py",
        "scripts/generate_sbom.py",
        "uv run pip-audit",
        "uv build",
        "uv build --out-dir /tmp/actionlineage-dist",
        "scripts/generate_release_provenance.py",
        "--dist-dir /tmp/actionlineage-dist",
        "docker build -f deploy/docker/Dockerfile -t actionlineage:ci .",
        "docker run --rm actionlineage:ci version",
        "actionlineage:ci demo run",
        "actionlineage demo run",
        "actionlineage projection export-console",
        "uv run --all-extras pytest",
    ):
        assert command in checklist


def test_ci_runs_local_release_proof_gates() -> None:
    workflow = (PROJECT_ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")

    assert (
        "uv run python scripts/generate_sbom.py --output /tmp/actionlineage-sbom.json" in workflow
    )
    assert "uv run pip-audit" in workflow
    assert "uv build --out-dir /tmp/actionlineage-dist" in workflow
    assert "scripts/generate_release_provenance.py" in workflow
    assert "--dist-dir /tmp/actionlineage-dist" in workflow
    assert "--output /tmp/actionlineage-release-provenance.json" in workflow
