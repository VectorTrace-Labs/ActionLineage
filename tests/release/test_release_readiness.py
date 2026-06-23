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
    assert "Intended Audience :: Developers" in project["classifiers"]
    assert "Intended Audience :: Information Technology" in project["classifiers"]
    assert "Operating System :: OS Independent" in project["classifiers"]
    assert "Programming Language :: Python :: 3.12" in project["classifiers"]
    assert "Programming Language :: Python :: 3.13" in project["classifiers"]
    assert "Topic :: Software Development :: Libraries :: Python Modules" in project["classifiers"]
    assert "Typing :: Typed" in project["classifiers"]
    assert project["license"] == "Apache-2.0"
    assert project["urls"] == {
        "Homepage": "https://github.com/VectorTrace-Labs/ActionLineage",
        "Repository": "https://github.com/VectorTrace-Labs/ActionLineage",
        "Documentation": "https://github.com/VectorTrace-Labs/ActionLineage#readme",
        "Issues": "https://github.com/VectorTrace-Labs/ActionLineage/issues",
        "Changelog": "https://github.com/VectorTrace-Labs/ActionLineage/blob/main/CHANGELOG.md",
        "Security policy": "https://github.com/VectorTrace-Labs/ActionLineage/security/policy",
    }
    assert pyproject["tool"]["ruff"]["target-version"] == "py312"
    assert pyproject["tool"]["mypy"]["python_version"] == "3.12"


def test_optional_extras_are_split_by_release_surface() -> None:
    optional = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))["project"][
        "optional-dependencies"
    ]

    assert {"adapters", "cloud", "console", "dev", "service"} <= set(optional)
    assert "fastapi>=0.115,<1" in optional["service"]
    assert "httpx2>=2,<3" not in optional["service"]
    assert "PyJWT[crypto]>=2.10,<3" in optional["service"]
    assert "uvicorn>=0.34,<1" in optional["service"]
    assert "mcp>=1.27,<2" in optional["adapters"]
    assert "httpx2>=2,<3" in optional["dev"]
    assert optional["console"] == []
    assert optional["cloud"] == []


def test_dependency_policy_documents_dev_only_test_client_dependency() -> None:
    policy = (PROJECT_ROOT / "docs/DEPENDENCY_POLICY.md").read_text(encoding="utf-8")

    assert "Development-only test-client dependency" in policy
    assert "`httpx2` is included only in the `dev` optional extra" in policy
    assert "Starlette/FastAPI" in policy
    assert "service-mode tests" in policy
    assert "BSD-3-Clause" in policy
    assert "does not enter the alpha" in policy
    assert "runtime trusted computing base" in policy
    assert "httpcore2" in policy
    assert "truststore" in policy


def test_release_docs_are_present() -> None:
    required_docs = {
        "docs/API_REFERENCE.md",
        "docs/CLI_REFERENCE.md",
        "docs/SCHEMA_REFERENCE.md",
        "docs/TUTORIAL.md",
        "docs/MIGRATION.md",
        "docs/FAQ.md",
        "docs/RELEASE_CHECKLIST.md",
        "docs/RELEASE_CANDIDATE_AUDIT.md",
        "docs/DRAFT_RELEASE_NOTES_0.1.0a3.md",
        "docs/OWNER_PUBLICATION_CHECKLIST.md",
        "docs/PACKAGE_MANAGERS.md",
        "docs/REVIEW_PROCESS.md",
        "docs/EXTERNAL_REVIEW_GUIDE.md",
        "docs/SECURITY_REVIEW_CHECKLIST.md",
        "docs/AGENT_PLATFORM_REVIEW_CHECKLIST.md",
        "docs/EVALUATION_REPRODUCTION.md",
        "docs/TROUBLESHOOTING.md",
        "docs/ADOPTION_CASE_STUDY_TEMPLATE.md",
        "docs/KNOWN_LIMITATIONS.md",
        ".github/copilot-instructions.md",
        "docs/QUALITY_SCORECARD.md",
        "docs/AGENT_VALIDATION_EVIDENCE.md",
        "docs/evidence/agent-validation-baseline.json",
        "docs/evidence/agent-validation-baseline.md",
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
        "evaluation-feedback.yml",
        "integration-proposal.yml",
        "security_report.yml",
        "security-design-review.yml",
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
    assert "make demo-map" in readme
    assert "demo-evidence-map.svg" in readme
    assert "canonical evidence remains `evidence.jsonl`" in readme
    assert "External review guide" in readme
    assert "Review outreach drafts" in readme
    assert "docs/REVIEW_OUTREACH_DRAFTS.md" in readme
    assert "Evaluation reproduction" in readme
    assert "Troubleshooting" in readme
    assert "docs/TROUBLESHOOTING.md" in readme
    assert "Known limitations" in readme
    assert "Release-candidate audit" in readme
    assert "Owner publication checklist" in readme


def test_external_review_docs_prepare_review_without_claiming_validation() -> None:
    docs = {
        "external": (PROJECT_ROOT / "docs/EXTERNAL_REVIEW_GUIDE.md").read_text(encoding="utf-8"),
        "security": (PROJECT_ROOT / "docs/SECURITY_REVIEW_CHECKLIST.md").read_text(
            encoding="utf-8"
        ),
        "platform": (PROJECT_ROOT / "docs/AGENT_PLATFORM_REVIEW_CHECKLIST.md").read_text(
            encoding="utf-8"
        ),
        "reproduction": (PROJECT_ROOT / "docs/EVALUATION_REPRODUCTION.md").read_text(
            encoding="utf-8"
        ),
        "hardening": (PROJECT_ROOT / "docs/SECURITY_HARDENING.md").read_text(encoding="utf-8"),
        "troubleshooting": (PROJECT_ROOT / "docs/TROUBLESHOOTING.md").read_text(encoding="utf-8"),
        "outreach": (PROJECT_ROOT / "docs/REVIEW_OUTREACH_DRAFTS.md").read_text(encoding="utf-8"),
        "case_study": (PROJECT_ROOT / "docs/ADOPTION_CASE_STUDY_TEMPLATE.md").read_text(
            encoding="utf-8"
        ),
        "limitations": (PROJECT_ROOT / "docs/KNOWN_LIMITATIONS.md").read_text(encoding="utf-8"),
    }
    combined = "\n".join(docs.values())
    normalized = combined.lower()

    assert "Five-Minute Install Path" in docs["external"]
    assert "acknowledgement is not proof" in docs["external"]
    assert "What Data Is Safe To Share" in docs["external"]
    assert "Security Review Checklist" in docs["security"]
    assert "Required Invariants" in docs["security"]
    assert "Agent Platform Review Checklist" in docs["platform"]
    assert "Lifecycle Semantics" in docs["platform"]
    assert "Published Package Smoke" in docs["reproduction"]
    assert "docs/TROUBLESHOOTING.md" in docs["reproduction"]
    assert "No-Model Agent Validation Baseline" in docs["reproduction"]
    assert "Local Release Proof" in docs["reproduction"]
    assert "release-consistency-offline.json" in docs["reproduction"]
    assert "review index summarizes the report counts" in docs["reproduction"]
    assert "release-consistency-*.json" in docs["external"]
    assert "Outreach Drafts" in docs["external"]
    assert "Release And Evaluation Announcement Draft" in docs["outreach"]
    assert "Technical Article Outline" in docs["outreach"]
    assert "Acknowledgement is not verification" in docs["outreach"]
    assert "Tool return values are component acknowledgements" in docs["outreach"]
    assert "docs/OWNER_PUBLICATION_CHECKLIST.md" in docs["outreach"]
    assert "current no-model Agent Validation baseline" in docs["outreach"]
    assert "offline release-consistency report" in docs["hardening"]
    assert "This is a template" in docs["case_study"]
    assert "Known Limitations" in docs["limitations"]
    assert (
        "No external audit, external adoption, production history, or independent"
        in docs["limitations"]
    )

    for required in (
        "uvx --prerelease allow --from actionlineage==0.1.0a3 actionlineage version",
        "actionlineage demo run",
        "actionlineage journal verify",
        "contracts/examples/outbound-http.json",
        "PYTHONPATH=evals uv run --group eval python -m actionlineage_evals",
        "docs/evidence/agent-validation-baseline.json",
        "scripts/check_claims_language.py",
        "scripts/secret_scan.py",
        "scripts/check_release_consistency.py",
        "scripts/write_release_candidate_manifest.py",
        "build/release-candidate/REVIEW_INDEX.md",
        "docs/REVIEW_OUTREACH_DRAFTS.md",
        "actionlineage doctor",
        'pipx run --pip-args="--pre"',
        "python -m pip install --pre actionlineage==0.1.0a3",
    ):
        assert required in combined

    unsupported_claims = (
        "has been externally audited",
        "has external adoption",
        "is production ready",
        "independent validation exists",
        "community validated",
    )
    for claim in unsupported_claims:
        assert claim not in normalized


def test_troubleshooting_doc_covers_first_time_user_failures() -> None:
    troubleshooting = (PROJECT_ROOT / "docs/TROUBLESHOOTING.md").read_text(encoding="utf-8")
    normalized = troubleshooting.lower()

    for required in (
        "Troubleshooting First-Time Evaluation",
        "actionlineage doctor",
        "uvx --prerelease allow --from actionlineage==0.1.0a3",
        'pipx run --pip-args="--pre"',
        "python -m pip install --pre actionlineage==0.1.0a3",
        "Python 3.12",
        "uv sync --locked --extra adapters",
        "uv sync --locked --extra service",
        "contracts/examples/outbound-http.json",
        "actionlineage projection export-console",
        "Offline Versus Online",
        "Release Proof And Review Index Issues",
        "release-consistency-offline.json",
        "scripts/write_release_review_index.py",
        "HASH_MISMATCH",
        "malformed_release_consistency_report",
        "Do not share live secrets",
        "evaluation feedback template",
        "SECURITY.md",
    ):
        assert required in troubleshooting

    for unsupported_claim in (
        "production ready",
        "externally validated",
        "externally audited",
    ):
        assert unsupported_claim not in normalized


def test_external_review_issue_templates_collect_safe_repro_context() -> None:
    template_dir = PROJECT_ROOT / ".github/ISSUE_TEMPLATE"
    templates = {
        path.name: path.read_text(encoding="utf-8")
        for path in (
            template_dir / "evaluation-feedback.yml",
            template_dir / "integration-proposal.yml",
            template_dir / "security-design-review.yml",
        )
    }
    combined = "\n".join(templates.values())

    assert "Evaluation path" in templates["evaluation-feedback.yml"]
    assert "Commands run" in templates["evaluation-feedback.yml"]
    assert "Evidence semantics concern" in templates["evaluation-feedback.yml"]
    assert "Safe bundle or fixture" in templates["evaluation-feedback.yml"]
    assert "Evidence lifecycle mapping" in templates["integration-proposal.yml"]
    assert "Tool identity and descriptor hash" in templates["integration-proposal.yml"]
    assert "Verification and observer model" in templates["integration-proposal.yml"]
    assert "Boundary or invariant at risk" in templates["security-design-review.yml"]
    assert (
        "For sensitive vulnerabilities, follow SECURITY.md"
        in templates["security-design-review.yml"]
    )

    for required in (
        "synthetic",
        "minimized",
        "Do not",
        "credentials",
        "authorization headers",
    ):
        assert required in combined


def test_release_candidate_audit_prepares_without_publishing() -> None:
    audit = (PROJECT_ROOT / "docs/RELEASE_CANDIDATE_AUDIT.md").read_text(encoding="utf-8")
    draft_notes = (PROJECT_ROOT / "docs/DRAFT_RELEASE_NOTES_0.1.0a3.md").read_text(encoding="utf-8")
    owner_checklist = (PROJECT_ROOT / "docs/OWNER_PUBLICATION_CHECKLIST.md").read_text(
        encoding="utf-8"
    )
    combined = "\n".join((audit, draft_notes, owner_checklist))
    normalized = combined.lower()

    assert "build/release-candidate/manifest.json" in audit
    assert "scripts/write_release_candidate_manifest.py" in audit
    assert "Release-candidate manifest generation" in audit
    assert "build/release-candidate/REVIEW_INDEX.md" in audit
    assert "Release proof review index" in audit
    assert "3ff4185b199fc74474f65dfa86d72441728a010d" in audit
    assert "Do not republish immutable PyPI/TestPyPI files" in audit
    assert "135 files already formatted" in audit
    assert "298 passed" in audit
    assert "86.03 percent total coverage" in audit
    assert "308 passed" in audit
    assert "no warning summary" in audit
    assert "23 package entries" in audit
    assert "23 direct dependencies checked, 0 issues" in audit
    assert "actionlineage-license-report.json" in audit
    assert "Release workflow artifact proof" in audit
    assert "build/release/release-consistency-offline.json" in audit
    assert "release-consistency reports are summarized when present" in audit
    assert "build/release/manifest.json" in audit
    assert "build/release/REVIEW_INDEX.md" in audit
    assert "bounded read-only `curl`" in audit
    assert "`fail_count=5`, `unknown_count=7`" in audit
    assert "Lower-priority URL HEAD checks" in audit
    assert "contract validate, case export, and static console export" in audit
    assert "47/47 declared capabilities covered" in audit
    assert "236 files scanned, 0 leaks" in audit
    assert "docs/evidence/agent-validation-baseline.md" in audit
    assert "docs/evidence/agent-validation-baseline.json" in audit
    assert "GitHub Release object for `v0.1.0a3`: absent" in audit
    assert "corrected long description" in audit
    assert "e3460120c7d85cfe8fa46f3bf5e8dc66f7e3ecb899979967d662b0072f800cae" in audit
    assert "488ff0ebf8bee34426ec9787d8aaacf829f2f5efc146073a0ba4eaa2b73bcbb6" in audit
    assert "3c69f5f1bec06abd9c260cc748a010cebfa22a1cea9a6b7ed8e7c0555cfb072a" in audit
    assert "8aaaaaa19f63c34ba9a164daff8c63d43315e35450b9cea912a40b0514698e7e" in audit
    assert "6c8003b10261b38e501ca1c0cfe645828a0ae59436c258ac147e69ff6db93d50" in audit

    for status in (
        "PASS",
        "BLOCKED_ON_OWNER",
        "BLOCKED_ON_EXTERNAL_VALIDATION",
        "NOT_IN_RELEASE_SCOPE",
    ):
        assert status in audit

    assert "not a request to republish immutable package-index artifacts" in draft_notes
    assert "ambiguous HTTP correlation as unverified evidence" in draft_notes
    assert "No external audit, external adoption, production use, independent review" in draft_notes
    assert "Codex must not perform these actions without explicit approval" in owner_checklist
    assert "build/release-candidate/REVIEW_INDEX.md" in owner_checklist
    assert "not as an attestation or external validation" in owner_checklist
    assert (
        "Do not republish or attempt to overwrite existing PyPI/TestPyPI files" in owner_checklist
    )

    unsupported_claims = (
        "release has been published by this audit",
        "production ready",
        "externally audited",
        "independent review completed",
        "community validated",
    )
    for claim in unsupported_claims:
        assert claim not in normalized


def test_release_checklist_covers_required_gates() -> None:
    checklist = (PROJECT_ROOT / "docs/RELEASE_CHECKLIST.md").read_text(encoding="utf-8")

    for command in (
        "uv run ruff check .",
        "uv run ruff format --check .",
        "uv run mypy src",
        "uv run pytest",
        "--cov=actionlineage",
        "--cov-branch",
        "--cov-fail-under=85",
        "scripts/generate_demo_evidence_map.py",
        "--demo-dir /tmp/actionlineage-demo",
        "scripts/check_claims_language.py",
        "scripts/check_markdown_links.py",
        "scripts/secret_scan.py",
        "scripts/generate_sbom.py",
        "scripts/check_release_consistency.py",
        "--output build/release-candidate/release-consistency-offline.json",
        "scripts/check_dependency_licenses.py",
        "--license-report build/actionlineage-license-report.json",
        "uv run pip-audit",
        "uv build --out-dir dist",
        "scripts/smoke_public_quickstart.py",
        "--package-spec dist/actionlineage-0.1.0a3-py3-none-any.whl",
        "--package-spec dist/actionlineage-0.1.0a3.tar.gz",
        "scripts/write_ci_quality_summary.py",
        "--coverage-floor 85",
        "actionlineage_evals public-report",
        "--json-output docs/evidence/agent-validation-baseline.json",
        "--markdown-output docs/evidence/agent-validation-baseline.md",
        "uv build --out-dir build/release-candidate/dist",
        "scripts/generate_release_provenance.py",
        "--dist-dir build/release-candidate/dist",
        "scripts/write_release_candidate_manifest.py",
        "--artifact-root build/release-candidate",
        "--dist-dir build/release-candidate/dist",
        '--gate "ruff_check|PASS|uv run ruff check ."',
        "scripts/write_release_review_index.py",
        "--manifest build/release-candidate/manifest.json",
        "--output build/release-candidate/REVIEW_INDEX.md",
        "docker build -f deploy/docker/Dockerfile -t actionlineage:ci .",
        "docker run --rm actionlineage:ci version",
        "actionlineage:ci demo run",
        "actionlineage demo run",
        "actionlineage projection export-console",
        "uv run --all-extras pytest",
        "First-time-user troubleshooting covers",
        "gh workflow run release.yml -f publish_target=none",
        "gh workflow run release.yml -f publish_target=testpypi",
        "gh workflow run release.yml -f publish_target=pypi",
        "gh attestation verify",
        "repository-url: https://test.pypi.org/legacy/",
        "Post-publication verification",
        "scripts/smoke_public_quickstart.py",
        "actionlineage-post-publication-*",
        "GHCR preview container images remain version-tagged",
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
    assert "name: Test with branch coverage" in workflow
    assert "--cov=actionlineage" in workflow
    assert "--cov-branch" in workflow
    assert "--cov-report=xml:/tmp/actionlineage-coverage.xml" in workflow
    assert "--cov-fail-under=85" in workflow
    assert (
        "uv run python scripts/generate_sbom.py --output /tmp/actionlineage-sbom.json" in workflow
    )
    assert "name: Dependency license check" in workflow
    assert "scripts/check_dependency_licenses.py" in workflow
    assert "--output /tmp/actionlineage-license-report.json" in workflow
    assert "uv run pip-audit" in workflow
    assert "uv build --out-dir /tmp/actionlineage-dist" in workflow
    assert "uv run actionlineage demo run --output-dir /tmp/actionlineage-demo" in workflow
    assert "scripts/generate_demo_evidence_map.py" in workflow
    assert "--demo-dir /tmp/actionlineage-demo" in workflow
    assert "--check" in workflow
    assert "uv run python scripts/check_markdown_links.py ." in workflow
    assert "scripts/generate_release_provenance.py" in workflow
    assert "--dist-dir /tmp/actionlineage-dist" in workflow
    assert "--output /tmp/actionlineage-release-provenance.json" in workflow
    assert "name: Built wheel first-time-user smoke" in workflow
    assert "name: Built sdist first-time-user smoke" in workflow
    assert "scripts/smoke_public_quickstart.py" in workflow
    assert '--package-spec "$wheel"' in workflow
    assert '--package-spec "$sdist"' in workflow
    assert "name: CI quality summary" in workflow
    assert "scripts/write_ci_quality_summary.py" in workflow
    assert "--coverage-floor 85" in workflow
    assert "--license-report /tmp/actionlineage-license-report.json" in workflow
    assert 'cat /tmp/actionlineage-ci-summary.md >> "$GITHUB_STEP_SUMMARY"' in workflow


def test_release_workflow_builds_attests_and_uses_trusted_publishing() -> None:
    workflow = (PROJECT_ROOT / ".github/workflows/release.yml").read_text(encoding="utf-8")

    assert "name: release" in workflow
    assert "publish_target:" in workflow
    assert 'python-version: ["3.12", "3.13"]' in workflow
    assert "python-version: ${{ matrix.python-version }}" in workflow
    assert "name: Verify release candidate" in workflow
    assert "name: Build release artifacts" in workflow
    assert "name: Dependency license check" in workflow
    assert "name: Generate dependency license report" in workflow
    assert "build/release/actionlineage-license-report.json" in workflow
    assert "name: Generate offline release consistency report" in workflow
    assert "--output build/release/release-consistency-offline.json" in workflow
    assert "name: Generate release candidate manifest" in workflow
    assert "scripts/write_release_candidate_manifest.py" in workflow
    assert "--artifact-root build/release" in workflow
    assert "--dist-dir dist" in workflow
    assert '--audited-implementation-commit "$GITHUB_SHA"' in workflow
    assert "build/release/manifest.json" in workflow
    assert "name: Generate release proof review index" in workflow
    assert "scripts/write_release_review_index.py" in workflow
    assert "build/release/REVIEW_INDEX.md" in workflow
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
    assert "test -f build/release/release-consistency-offline.json" in workflow
    assert "test -f build/release/manifest.json" in workflow
    assert "test -f build/release/REVIEW_INDEX.md" in workflow
    assert "actionlineage.dev/release-candidate-manifest-v0" in workflow
    assert "ActionLineage Release Proof Review Index" in workflow
    assert """name '*.whl'""" in workflow
    assert """name '*.tar.gz'""" in workflow
    assert "repository-url: https://test.pypi.org/legacy/" in workflow
    assert "packages-dir: release-artifacts/dist" in workflow
    assert "name: Post-publication verification" in workflow
    assert "needs: [publish-testpypi, publish-pypi]" in workflow
    assert "needs['publish-testpypi'].result == 'success'" in workflow
    assert "needs['publish-pypi'].result == 'success'" in workflow
    assert "timeout-minutes: 20" in workflow
    assert "https://test.pypi.org/pypi/actionlineage/json" in workflow
    assert "https://pypi.org/pypi/actionlineage/json" in workflow
    assert "python -m venv .venv-post-publication" in workflow
    assert (
        'python -m pip install --pre ${PIP_INDEX_ARGS} "actionlineage==${ACTIONLINEAGE_VERSION}"'
        in workflow
    )
    assert "installed-metadata.json" in workflow
    assert "public-smoke.json" in workflow
    assert '--expected-version "${ACTIONLINEAGE_VERSION}"' in workflow
    assert (
        "actionlineage-post-publication-${{ inputs.publish_target }}-py${{ matrix.python-version }}"
    ) in workflow
    assert "retention-days: 14" in workflow
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
    assert combined.count(f"actions/upload-artifact@{upload_artifact_v7_0_1}") == 5
    assert "actions/download-artifact@" not in combined
    assert 'python-version: ["3.12", "3.13"]' in agent_validation
    assert (
        "actionlineage-agent-validation-no-model-py${{ matrix.python-version }}" in agent_validation
    )
    assert (
        "actionlineage-agent-validation-docker-py${{ matrix.python-version }}" in agent_validation
    )


def test_agent_validation_workflow_schedules_no_model_and_secret_gates_live_models() -> None:
    workflow = (PROJECT_ROOT / ".github/workflows/agent-validation.yml").read_text(encoding="utf-8")
    docs = (PROJECT_ROOT / "docs" / "AGENT_VALIDATION_ARCHITECTURE.md").read_text(encoding="utf-8")
    evidence = (PROJECT_ROOT / "docs" / "AGENT_VALIDATION_EVIDENCE.md").read_text(encoding="utf-8")

    assert "schedule:" in workflow
    assert "if: github.event_name != 'schedule' || github.ref == 'refs/heads/main'" in workflow
    assert "--artifact-root build/evals/no-model" in workflow
    assert "actionlineage_evals public-report" in workflow
    assert "--json-output build/evals/reports/agent-validation-baseline.json" in workflow
    assert "--markdown-output build/evals/reports/agent-validation-baseline.md" in workflow
    assert "id: live-secret" in workflow
    assert "GH_MODELS_TOKEN: ${{ secrets.GH_MODELS_TOKEN }}" in workflow
    assert "Skipped: GH_MODELS_TOKEN is not configured; no model requests were made." in workflow
    assert "if: steps.live-secret.outputs.configured == 'true'" in workflow
    assert "GITHUB_TOKEN: ${{ github.token }}" not in workflow
    assert "failure_fingerprint" in docs
    assert "Scheduled no-model lane" in docs
    assert "explicit `GH_MODELS_TOKEN`" in docs
    assert "Scheduled no-model lane" in evidence
    assert "Scheduled live-model lane" in evidence


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
    assert "post-publication verification job runs only after the selected publishing" in publishing
    assert "index-propagation.json" in publishing
    assert "installed-metadata.json" in publishing
    assert "public-smoke.json" in publishing
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
    assert "corrected long description wording" in decisions
    assert "GHCR package visibility" in decisions
    assert "Homebrew tap" in decisions


def test_public_claim_audit_tracks_package_description_drift() -> None:
    audit = (PROJECT_ROOT / "docs/PUBLIC_CLAIM_AUDIT.md").read_text(encoding="utf-8")
    hardening_plan = (PROJECT_ROOT / "docs/PUBLIC_ALPHA_HARDENING_PLAN.md").read_text(
        encoding="utf-8"
    )
    scorecard = (PROJECT_ROOT / "docs/QUALITY_SCORECARD.md").read_text(encoding="utf-8")

    assert "CLAIM-007" in audit
    assert "stale GitHub Release or pending-publication claims" in audit
    assert "scripts/check_release_consistency.py" in audit
    assert "PALPHA-013" in hardening_plan
    assert "PALPHA-014" in hardening_plan
    assert "PALPHA-015" in hardening_plan
    assert "PALPHA-016" in hardening_plan
    assert "FIXED_IN_POST_PUBLICATION_VERIFY_SLICE" in hardening_plan
    assert "FIXED_IN_OUTREACH_DRAFTS_SLICE" in hardening_plan
    assert "MITIGATED_WITH_CURL_FALLBACK" in hardening_plan
    assert "3ff4185b199fc74474f65dfa86d72441728a010d" in hardening_plan
    assert "Public package long descriptions can lag" in hardening_plan
    assert "Local release-proof reproduction docs mixed" in hardening_plan
    assert "bounded read-only `curl` fallback" in audit
    assert "bounded read-only `curl` fallback" in scorecard
    assert "Local Python certificate stores can block online release checks" in scorecard


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
