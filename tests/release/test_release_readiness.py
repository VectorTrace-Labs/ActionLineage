from __future__ import annotations

import tomllib
from pathlib import Path

from typer.testing import CliRunner

import actionlineage
from actionlineage.cli import app

PROJECT_ROOT = Path(__file__).resolve().parents[2]
PYPROJECT = PROJECT_ROOT / "pyproject.toml"


def test_package_metadata_is_public_alpha_ready() -> None:
    pyproject = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))
    project = pyproject["project"]

    assert project["version"] == "0.1.0a3"
    assert project["requires-python"] == ">=3.12"
    assert actionlineage.__version__ == "0.1.0a3"
    assert "Development Status :: 3 - Alpha" in project["classifiers"]
    assert "Development Status :: 5 - Production/Stable" not in project["classifiers"]
    assert "Programming Language :: Python :: 3.12" in project["classifiers"]
    assert "Programming Language :: Python :: 3.13" in project["classifiers"]
    assert "Typing :: Typed" in project["classifiers"]
    assert pyproject["tool"]["ruff"]["target-version"] == "py312"
    assert pyproject["tool"]["mypy"]["python_version"] == "3.12"


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
        "docs/PACKAGE_MANAGERS.md",
        "docs/REVIEW_PROCESS.md",
        ".github/copilot-instructions.md",
        "docs/QUALITY_SCORECARD.md",
        "docs/PERFECTION_PLAN.md",
        "docs/MATURITY.md",
        "docs/DECISIONS_REQUIRED.md",
        "docs/PUBLISHING.md",
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
    assert result.stdout.strip() == "0.1.0a3"


def test_readme_quickstart_uses_demo_aligned_contract() -> None:
    readme = (PROJECT_ROOT / "README.md").read_text(encoding="utf-8")

    assert "Five-Minute PyPI Evaluation" in readme
    assert "Python 3.12 or newer" in readme
    assert "Because `0.1.0a3` is a prerelease" in readme
    assert "uvx --prerelease allow --from actionlineage==0.1.0a3 actionlineage version" in readme
    assert (
        "uvx --prerelease allow --from actionlineage==0.1.0a3 actionlineage demo run --output-dir"
    ) in readme
    assert "PyPI path needs internet access to install the package" in readme
    assert "uv sync --locked --all-extras" in readme
    assert "contracts/examples/outbound-http.json" in readme
    assert (
        "uv run actionlineage contract validate contracts/examples/restricted-exfiltration.json"
    ) not in readme
    assert "public alpha" in readme
    assert "Preview" in readme
    assert "Agent Validation Lab" in readme
    assert "development-only evaluation surface" in readme
    assert "PYTHONPATH=evals uv run --group eval python -m actionlineage_evals" in readme


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
        "gh workflow run release.yml -f publish_target=none",
        "gh workflow run release.yml -f publish_target=testpypi",
        "gh workflow run release.yml -f publish_target=pypi",
        "gh attestation verify",
        "repository-url: https://test.pypi.org/legacy/",
        "GHCR publishes preview container images",
        "packages: write",
        "deploy/docker/Dockerfile",
        "See `docs/PACKAGE_MANAGERS.md`.",
    ):
        assert command in checklist


def test_ci_runs_local_release_proof_gates() -> None:
    workflow = (PROJECT_ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")

    assert "python-version: ['3.12', '3.13']" in workflow
    assert "python-version: ${{ matrix.python-version }}" in workflow
    assert "uv sync --locked --all-extras" in workflow
    assert (
        "uv run python scripts/generate_sbom.py --output /tmp/actionlineage-sbom.json" in workflow
    )
    assert "uv run pip-audit" in workflow
    assert "uv build --out-dir /tmp/actionlineage-dist" in workflow
    assert "scripts/generate_release_provenance.py" in workflow
    assert "--dist-dir /tmp/actionlineage-dist" in workflow
    assert "--output /tmp/actionlineage-release-provenance.json" in workflow


def test_release_workflow_builds_attests_and_uses_trusted_publishing() -> None:
    workflow = (PROJECT_ROOT / ".github/workflows/release.yml").read_text(encoding="utf-8")

    assert "name: release" in workflow
    assert "publish_target:" in workflow
    assert 'python-version: ["3.12", "3.13"]' in workflow
    assert "python-version: ${{ matrix.python-version }}" in workflow
    assert "name: Verify release candidate" in workflow
    assert "name: Build release artifacts" in workflow
    assert "name: Smoke test release artifact bundle" in workflow
    assert "name: Attest release artifacts" not in workflow
    assert "needs: verify" in workflow
    assert workflow.count("needs: build") == 1
    assert workflow.count("needs: artifact-smoke") == 2
    assert "attestations: write" in workflow
    assert "artifact-metadata: write" in workflow
    assert "id-token: write" in workflow
    assert "actions/attest@" in workflow
    assert "dist/*" in workflow
    assert "build/release/*" in workflow
    assert "pypa/gh-action-pypi-publish@" in workflow
    assert 'gh run download "${GITHUB_RUN_ID}" --repo "${GITHUB_REPOSITORY}"' in workflow
    assert "actions: read" in workflow
    assert "sha256sum -c build/release/SHA256SUMS.txt" in workflow
    assert """name '*.whl'""" in workflow
    assert """name '*.tar.gz'""" in workflow
    assert "repository-url: https://test.pypi.org/legacy/" in workflow
    assert "packages-dir: release-artifacts/dist" in workflow
    assert "startsWith(github.ref, 'refs/tags/v')" in workflow
    assert "environment:" in workflow
    assert "name: testpypi" in workflow
    assert "name: pypi" in workflow
    assert "password:" not in workflow
    assert "PYPI_TOKEN" not in workflow


def test_artifact_upload_action_is_node24_pin_and_download_action_is_not_used() -> None:
    release = (PROJECT_ROOT / ".github/workflows/release.yml").read_text(encoding="utf-8")
    agent_validation = (PROJECT_ROOT / ".github/workflows/agent-validation.yml").read_text(
        encoding="utf-8"
    )
    combined = release + "\n" + agent_validation

    upload_artifact_v7_0_1 = "043fb46d1a93c77aae656e7c1c64a875d1fc6a0a"

    assert upload_artifact_v7_0_1 in release
    assert upload_artifact_v7_0_1 in agent_validation
    assert combined.count(f"actions/upload-artifact@{upload_artifact_v7_0_1}") == 4
    assert "actions/download-artifact@" not in combined
    assert 'python-version: ["3.12", "3.13"]' in agent_validation
    assert (
        "actionlineage-agent-validation-no-model-py${{ matrix.python-version }}" in agent_validation
    )
    assert (
        "actionlineage-agent-validation-docker-py${{ matrix.python-version }}" in agent_validation
    )


def test_release_workflow_publishes_versioned_ghcr_image_without_registry_secret() -> None:
    workflow = (PROJECT_ROOT / ".github/workflows/release.yml").read_text(encoding="utf-8")

    assert "name: Publish GHCR image" in workflow
    assert "needs: verify" in workflow
    assert "if: startsWith(github.ref, 'refs/tags/v')" in workflow
    assert "packages: write" in workflow
    assert "ghcr.io/${owner}/actionlineage" in workflow
    assert "docker login ghcr.io" in workflow
    assert "secrets.GITHUB_TOKEN" in workflow
    assert "deploy/docker/Dockerfile" in workflow
    assert "${GITHUB_REF_NAME#v}" in workflow
    assert "docker run --rm" in workflow
    assert "docker push" in workflow
    assert ":latest" not in workflow
    assert "DOCKERHUB" not in workflow


def test_publishing_docs_record_package_publication_and_remaining_gates() -> None:
    publishing = (PROJECT_ROOT / "docs/PUBLISHING.md").read_text(encoding="utf-8")
    package_managers = (PROJECT_ROOT / "docs/PACKAGE_MANAGERS.md").read_text(encoding="utf-8")
    maturity = (PROJECT_ROOT / "docs/MATURITY.md").read_text(encoding="utf-8")
    decisions = (PROJECT_ROOT / "docs/DECISIONS_REQUIRED.md").read_text(encoding="utf-8")

    assert "Trusted Publisher records" in publishing
    assert "Do not add PyPI API tokens" in publishing
    assert "GHCR Container Images" in publishing
    assert "https://pypi.org/project/actionlineage/" in publishing
    assert "https://test.pypi.org/project/actionlineage/" in publishing
    assert "27973522992" in publishing
    assert "27973832210" in publishing
    assert "Organization ownership transfer remains an external follow-up" in publishing
    assert "ghcr.io/vectortrace-labs/actionlineage" in package_managers
    assert "PyPI/TestPyPI | Alpha-supported" in package_managers
    assert (
        "uvx --prerelease allow --from actionlineage==0.1.0a3 actionlineage version"
    ) in package_managers
    assert "Python 3.12-compatible alpha release" in package_managers
    assert "do not publish or document a `latest` tag" in package_managers
    assert "Homebrew tap" in package_managers
    assert "Do not commit an unvalidated formula" in package_managers
    assert "PyPI and TestPyPI package publication" in maturity
    assert "package ownership transfer to the organization account" in maturity
    assert "GHCR container-image publication" in maturity
    assert "PyPI/TestPyPI organization ownership transfer" in decisions
    assert "GHCR package visibility" in decisions
    assert "Homebrew tap" in decisions


def test_review_process_keeps_ai_review_advisory() -> None:
    review_process = (PROJECT_ROOT / "docs/REVIEW_PROCESS.md").read_text(encoding="utf-8")
    copilot_instructions = (PROJECT_ROOT / ".github/copilot-instructions.md").read_text(
        encoding="utf-8"
    )
    readme = (PROJECT_ROOT / "README.md").read_text(encoding="utf-8")

    assert "AI review is advisory" in review_process
    assert "intended to request Copilot review" in review_process
    assert ".github/copilot-instructions.md" in review_process
    assert "does not" in review_process
    assert "count as an approving review" in review_process
    assert "replace maintainer judgment" in review_process
    assert "override failing required checks" in review_process
    assert "Required human approvals are not enabled" in review_process
    assert "required checks pass" in review_process
    assert "docs/REVIEW_PROCESS.md" in readme
    assert "Treat Copilot review as advisory" in copilot_instructions
    assert "domain core remains independent" in copilot_instructions
    assert "not treated as proof" in copilot_instructions
    assert "proof-of-absence wording" in copilot_instructions
    assert "uv run pytest" in copilot_instructions
