from __future__ import annotations

import tomllib
from fnmatch import fnmatch
from pathlib import Path

from typer.testing import CliRunner

import actionlineage
from actionlineage.cli import app

PROJECT_ROOT = Path(__file__).resolve().parents[2]
PYPROJECT = PROJECT_ROOT / "pyproject.toml"
LOCAL_ONLY_DOCS = (
    "docs/DECISIONS_REQUIRED.md",
    "docs/PERFECTION_PLAN.md",
    "docs/OWNER_PUBLICATION_CHECKLIST.md",
    "docs/RELEASE_CANDIDATE_AUDIT.md",
    "docs/DRAFT_RELEASE_NOTES_0.1.0a3.md",
    "docs/DRAFT_RELEASE_NOTES_0.1.0a5.md",
    "docs/DRAFT_RELEASE_NOTES_0.1.0a6.md",
    "docs/PUBLIC_ALPHA_HARDENING_PLAN.md",
    "docs/PUBLIC_CLAIM_AUDIT.md",
    "docs/REVIEW_OUTREACH_DRAFTS.md",
    "docs/RESOURCES.md",
)


def test_package_metadata_is_public_alpha_ready() -> None:
    pyproject = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))
    project = pyproject["project"]

    assert project["version"] == "0.1.0a6"
    assert project["requires-python"] == ">=3.12,<3.15"
    assert actionlineage.__version__ == "0.1.0a6"
    assert "Development Status :: 3 - Alpha" in project["classifiers"]
    assert "Development Status :: 5 - Production/Stable" not in project["classifiers"]
    assert "Intended Audience :: Developers" in project["classifiers"]
    assert "Intended Audience :: Information Technology" in project["classifiers"]
    assert "Operating System :: OS Independent" in project["classifiers"]
    assert "Programming Language :: Python :: 3.12" in project["classifiers"]
    assert "Programming Language :: Python :: 3.13" in project["classifiers"]
    assert "Programming Language :: Python :: 3.14" in project["classifiers"]
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
        "docs/MATURITY.md",
        "docs/PUBLISHING.md",
        "SECURITY.md",
        "docs/PRIVACY.md",
    }

    missing = [path for path in required_docs if not (PROJECT_ROOT / path).exists()]

    assert missing == []


def test_append_checkpoint_scope_decision_is_tracked() -> None:
    adr = (PROJECT_ROOT / "docs/ADR/0011-append-checkpoint-and-index-scope.md").read_text(
        encoding="utf-8"
    )
    architecture = (PROJECT_ROOT / "ARCHITECTURE.md").read_text(encoding="utf-8")
    journal_integrity = (PROJECT_ROOT / "docs/JOURNAL_INTEGRITY.md").read_text(encoding="utf-8")
    scorecard = (PROJECT_ROOT / "docs/QUALITY_SCORECARD.md").read_text(encoding="utf-8")
    followups = (PROJECT_ROOT / "docs/SECURITY_ASSESSMENT_FOLLOWUPS.md").read_text(encoding="utf-8")

    assert "- Status: Accepted" in adr
    assert "Do not add a trusted append index" in adr
    assert "rebuildable cache" in adr
    assert "canonical evidence or trusted evidence" in architecture
    assert "A stale or mismatched" in journal_integrity
    assert "index must be ignored or rebuilt" in journal_integrity
    assert "future append indexes are rebuildable caches" in scorecard
    assert "Append checkpoint/index scope" in followups


def test_observer_attestation_policy_boundary_is_tracked() -> None:
    adr = (PROJECT_ROOT / "docs/ADR/0012-observer-attestation-policy.md").read_text(
        encoding="utf-8"
    )
    observers = (PROJECT_ROOT / "docs/OBSERVERS.md").read_text(encoding="utf-8")
    data_model = (PROJECT_ROOT / "docs/DATA_MODEL.md").read_text(encoding="utf-8")
    scorecard = (PROJECT_ROOT / "docs/QUALITY_SCORECARD.md").read_text(encoding="utf-8")
    maturity = (PROJECT_ROOT / "docs/MATURITY.md").read_text(encoding="utf-8")
    followups = (PROJECT_ROOT / "docs/SECURITY_ASSESSMENT_FOLLOWUPS.md").read_text(encoding="utf-8")

    assert "- Status: Proposed" in adr
    assert "do not change the public `v1alpha1` event schema" in adr
    assert "reviewed independence declaration" in adr
    assert "Independence boundaries" in adr
    assert "trust labels and limitations" in observers
    assert "do not by themselves prove" in observers
    assert "Attestation Policy Boundary" in observers
    assert "`verify_observation()` defaults to `unknown` corroboration" in observers
    assert "Missing, stale, expired, shared, incomplete" in observers
    assert "A trust label alone is not enough" in data_model
    assert "helper defaults to `unknown` corroboration" in data_model
    assert "Observer independence requires a reviewed attestation policy" in scorecard
    assert "Observer attestation declarations and `verify_observation()` gating" in maturity
    assert "Observer attestation gate" in followups
    assert "helper-generated `independent_observer` evidence links now require" in followups


def test_canonicalization_v1_boundary_is_tracked() -> None:
    adr = (PROJECT_ROOT / "docs/ADR/0013-canonicalization-v1-conformance.md").read_text(
        encoding="utf-8"
    )
    data_model = (PROJECT_ROOT / "docs/DATA_MODEL.md").read_text(encoding="utf-8")
    journal_integrity = (PROJECT_ROOT / "docs/JOURNAL_INTEGRITY.md").read_text(encoding="utf-8")
    compatibility = (PROJECT_ROOT / "docs/COMPATIBILITY.md").read_text(encoding="utf-8")
    scorecard = (PROJECT_ROOT / "docs/QUALITY_SCORECARD.md").read_text(encoding="utf-8")
    maturity = (PROJECT_ROOT / "docs/MATURITY.md").read_text(encoding="utf-8")
    followups = (PROJECT_ROOT / "docs/SECURITY_ASSESSMENT_FOLLOWUPS.md").read_text(encoding="utf-8")

    assert "- Status: Accepted" in adr
    assert "Do not replace `actionlineage.dev/json-deterministic-v0`" in adr
    assert "json-canonicalization-v1" in adr
    assert "conformance vectors" in adr
    assert "tests/fixtures/canonicalization/json-canonicalization-v1-vectors.json" in adr
    assert "expected bytes and" in adr
    assert "SHA-256 digests" in adr
    assert "migration ADR" in adr
    assert "runtime migration policy" in adr
    assert "active public-alpha journal" in data_model
    assert "serialization boundary" in data_model
    assert "v1 is still rejected for persisted evidence hashes" in data_model
    assert "does not claim RFC 8785/JCS conformance" in journal_integrity
    assert "current verifier rejects v1 labels" in journal_integrity
    assert "Adopting `actionlineage.dev/json-canonicalization-v1`" in compatibility
    assert "Portable canonicalization v1 is not yet a persisted hash format" in scorecard
    assert "tests/domain/test_canonicalization.py" in scorecard
    assert "Canonicalization v1 conformance vectors and migration guardrails" in maturity
    assert "Portable canonicalization v1 as an active persisted hash format" in maturity
    assert "ADR-0013 now accepts the" in followups
    assert "Runtime policy rejects v1 for persisted event hashes" in followups


def test_causality_evolution_boundary_is_tracked() -> None:
    adr = (PROJECT_ROOT / "docs/ADR/0014-causality-model-evolution.md").read_text(encoding="utf-8")
    data_model = (PROJECT_ROOT / "docs/DATA_MODEL.md").read_text(encoding="utf-8")
    scorecard = (PROJECT_ROOT / "docs/QUALITY_SCORECARD.md").read_text(encoding="utf-8")
    maturity = (PROJECT_ROOT / "docs/MATURITY.md").read_text(encoding="utf-8")
    followups = (PROJECT_ROOT / "docs/SECURITY_ASSESSMENT_FOLLOWUPS.md").read_text(encoding="utf-8")

    assert "- Status: Proposed" in adr
    assert "Do not change `actionlineage.dev/v1alpha1` causality" in adr
    assert "versioned schema change or migration ADR" in adr
    assert "Local journal position" in adr
    assert "Producer or source sequence" in adr
    assert "typed multi-parent causal edges" in data_model
    assert "ADR-0014" in scorecard
    assert "Causality model evolution ADR" in maturity
    assert "ADR-0014 now defines" in followups


def test_external_checkpoint_trust_root_boundary_is_tracked() -> None:
    adr = (PROJECT_ROOT / "docs/ADR/0015-external-checkpoint-trust-roots.md").read_text(
        encoding="utf-8"
    )
    journal_integrity = (PROJECT_ROOT / "docs/JOURNAL_INTEGRITY.md").read_text(encoding="utf-8")
    scorecard = (PROJECT_ROOT / "docs/QUALITY_SCORECARD.md").read_text(encoding="utf-8")
    maturity = (PROJECT_ROOT / "docs/MATURITY.md").read_text(encoding="utf-8")
    followups = (PROJECT_ROOT / "docs/SECURITY_ASSESSMENT_FOLLOWUPS.md").read_text(encoding="utf-8")

    assert "- Status: Proposed" in adr
    assert "Do not add a new external checkpoint implementation" in adr
    assert "provider-neutral checkpoint declaration" in adr
    assert "Outage behavior must be explicit" in adr
    assert "ADR-0015" in journal_integrity
    assert "External checkpoint trust roots remain planned" in scorecard
    assert "External checkpoint trust-root ADR" in maturity
    assert "ADR-0015 now defines" in followups


def test_structured_log_redaction_boundary_is_tracked() -> None:
    redaction_source = (PROJECT_ROOT / "src/actionlineage/domain/redaction.py").read_text(
        encoding="utf-8"
    )
    security_hardening = (PROJECT_ROOT / "docs/SECURITY_HARDENING.md").read_text(encoding="utf-8")
    coding_standards = (PROJECT_ROOT / "docs/CODING_STANDARDS.md").read_text(encoding="utf-8")
    scorecard = (PROJECT_ROOT / "docs/QUALITY_SCORECARD.md").read_text(encoding="utf-8")
    followups = (PROJECT_ROOT / "docs/SECURITY_ASSESSMENT_FOLLOWUPS.md").read_text(encoding="utf-8")

    assert "redact_structured_log_fields" in redaction_source
    assert "STRUCTURED_LOG_CAPTURE_MARKER" in redaction_source
    assert "STRUCTURED_LOG_DIGEST_UNAVAILABLE" in redaction_source
    assert "Structured log capture summary" in security_hardening
    assert "Pass user, event, observer, exporter, or exception-derived fields" in coding_standards
    assert "Structured log fields have a reusable redaction" in scorecard
    assert "Structured log digest boundary" in followups
    assert (
        "Broader\n  digest-correlation review across future structured log surfaces remains open"
        not in (followups)
    )


def test_local_release_planning_docs_are_ignored_and_not_linked_publicly() -> None:
    gitignore = (PROJECT_ROOT / ".gitignore").read_text(encoding="utf-8")
    ignore_patterns = tuple(
        line.strip() for line in gitignore.splitlines() if line.strip() and not line.startswith("#")
    )
    readme = (PROJECT_ROOT / "README.md").read_text(encoding="utf-8")
    scorecard = (PROJECT_ROOT / "docs/QUALITY_SCORECARD.md").read_text(encoding="utf-8")
    external_review = (PROJECT_ROOT / "docs/EXTERNAL_REVIEW_GUIDE.md").read_text(encoding="utf-8")
    public_reference_text = "\n".join((readme, scorecard, external_review))

    for path in LOCAL_ONLY_DOCS:
        assert any(fnmatch(path, pattern) for pattern in ignore_patterns)
        assert path not in public_reference_text

    assert "Release workflow prepares owner-review artifacts without publishing" in scorecard
    assert "Review outreach drafts" not in readme
    assert "Decisions required" not in readme


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
    assert result.stdout.strip() == "0.1.0a6"


def test_readme_quickstart_uses_demo_aligned_contract() -> None:
    readme = (PROJECT_ROOT / "README.md").read_text(encoding="utf-8")

    assert "Five-Minute PyPI Evaluation" in readme
    assert "Python 3.12, 3.13, or 3.14" in readme
    assert "Because `0.1.0a6` is a prerelease" in readme
    assert "uvx --prerelease allow --from actionlineage==0.1.0a6 actionlineage version" in readme
    assert (
        "uvx --prerelease allow --from actionlineage==0.1.0a6 actionlineage demo run --output-dir"
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
    assert "Good first issue candidates" in readme
    assert "docs/GOOD_FIRST_ISSUES.md" in readme
    assert "Evaluation reproduction" in readme
    assert "Troubleshooting" in readme
    assert "docs/TROUBLESHOOTING.md" in readme
    assert "Known limitations" in readme
    for local_only_doc in LOCAL_ONLY_DOCS:
        assert local_only_doc not in readme


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
        "good_first": (PROJECT_ROOT / "docs/GOOD_FIRST_ISSUES.md").read_text(encoding="utf-8"),
        "troubleshooting": (PROJECT_ROOT / "docs/TROUBLESHOOTING.md").read_text(encoding="utf-8"),
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
    assert "Version tag matches audited commit" in docs["external"]
    assert "post-tag hardening proof" in docs["external"]
    assert "docs/GOOD_FIRST_ISSUES.md" in docs["external"]
    assert "Good First Issue Candidates" in docs["good_first"]
    assert "Candidate 1: Extend Ambiguous HTTP Correlation Coverage" in docs["good_first"]
    assert "Candidate 2: Add Reference-Style Fragment Link Coverage" in docs["good_first"]
    assert "Candidate 3: Add A Future Event Compatibility Fixture" in docs["good_first"]
    assert "Candidate 4: Add One Failed-Prerequisite Troubleshooting Example" in docs["good_first"]
    assert "Candidate 5: Add Static-Console Invalid Context Coverage" in docs["good_first"]
    assert "Acceptance criteria" in docs["good_first"]
    assert "Suggested verification" in docs["good_first"]
    assert "Out of scope" in docs["good_first"]
    assert "They are not automatically opened" in docs["good_first"]
    assert "offline release-consistency report" in docs["hardening"]
    assert "This is a template" in docs["case_study"]
    assert "Known Limitations" in docs["limitations"]
    assert (
        "No external audit, external adoption, production history, or independent"
        in docs["limitations"]
    )

    for required in (
        "uvx --prerelease allow --from actionlineage==0.1.0a6 actionlineage version",
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
        "Version tag matches audited commit",
        "docs/GOOD_FIRST_ISSUES.md",
        "actionlineage doctor",
        'pipx run --pip-args="--pre"',
        "python -m pip install --pre actionlineage==0.1.0a6",
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
        "uvx --prerelease allow --from actionlineage==0.1.0a6",
        'pipx run --pip-args="--pre"',
        "python -m pip install --pre actionlineage==0.1.0a6",
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
        "--package-spec dist/actionlineage-0.1.0a6-py3-none-any.whl",
        "--package-spec dist/actionlineage-0.1.0a6.tar.gz",
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
        "local Markdown heading fragments resolve",
        "GHCR preview container images remain version-tagged",
        "packages: write",
        "deploy/docker/Dockerfile",
        "See `docs/PACKAGE_MANAGERS.md`.",
    ):
        assert command in checklist


def test_ci_runs_local_release_proof_gates() -> None:
    workflow = (PROJECT_ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")

    assert "python-version: ['3.12', '3.13', '3.14']" in workflow
    assert "python-version: ${{ matrix.python-version }}" in workflow
    assert "fetch-depth: 0" in workflow
    assert "uv sync --locked --all-extras" in workflow
    assert "name: Test with branch coverage" in workflow
    assert "--cov=actionlineage" in workflow
    assert "--cov-branch" in workflow
    assert "--cov-report=xml:/tmp/actionlineage-coverage.xml" in workflow
    assert "--cov-fail-under=85" in workflow
    assert (
        "uv run --all-extras python scripts/generate_sbom.py --output /tmp/actionlineage-sbom.json"
        in workflow
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
    assert 'python-version: ["3.12", "3.13", "3.14"]' in workflow
    assert "python-version: ${{ matrix.python-version }}" in workflow
    assert "name: Verify release candidate" in workflow
    assert "name: Build release artifacts" in workflow
    assert "name: Dependency license check" in workflow
    assert "name: Generate dependency license report" in workflow
    assert "build/release/actionlineage-license-report.json" in workflow
    assert "build/release/actionlineage-release-provenance.json" in workflow
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
    assert combined.count(f"actions/upload-artifact@{upload_artifact_v7_0_1}") == 6
    assert "actions/download-artifact@" not in combined
    assert 'python-version: ["3.12", "3.13", "3.14"]' in agent_validation
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
    assert "actionlineage_evals check-public-baseline" in workflow
    assert "--allow-input-drift" in workflow
    assert "--json-output build/evals/reports/agent-validation-baseline.json" in workflow
    assert "--markdown-output build/evals/reports/agent-validation-baseline.md" in workflow
    assert "id: live-secret" in workflow
    assert "GH_MODELS_TOKEN: ${{ secrets.GH_MODELS_TOKEN }}" in workflow
    assert "Skipped: GH_MODELS_TOKEN is not configured; no model requests were made." in workflow
    assert "if: steps.live-secret.outputs.configured == 'true'" in workflow
    assert "GITHUB_TOKEN: ${{ github.token }}" not in workflow
    assert "failure_fingerprint" in docs
    assert "Scheduled no-model lane" in docs
    assert "check-public-baseline" in docs
    assert "semantic-only" in docs
    assert "explicit `GH_MODELS_TOKEN`" in docs
    assert "Scheduled no-model lane" in evidence
    assert "Baseline freshness gate" in evidence
    assert "input drift remains reported" in evidence
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

    assert "Trusted Publisher records" in publishing
    assert "Do not add PyPI API tokens" in publishing
    assert "GHCR Container Images" in publishing
    assert "https://pypi.org/project/actionlineage/" in publishing
    assert "https://test.pypi.org/project/actionlineage/" in publishing
    assert "Current public version: `0.1.0a5`" in publishing
    assert "Next prepared corrective version: `0.1.0a6`" in publishing
    assert "Current GitHub Release: `v0.1.0a5`" in publishing
    assert "post-publication verification job runs only after the selected publishing" in publishing
    assert "index-propagation.json" in publishing
    assert "installed-metadata.json" in publishing
    assert "public-smoke.json" in publishing
    assert "Organization ownership transfer remains an external follow-up" in publishing
    assert "ghcr.io/vectortrace-labs/actionlineage" in package_managers
    assert "PyPI/TestPyPI | Alpha-supported" in package_managers
    assert (
        "uvx --prerelease allow --from actionlineage==0.1.0a6 actionlineage version"
    ) in package_managers
    assert "Python 3.12/3.13/3.14 alpha release candidate" in package_managers
    assert "do not publish or document a `latest` tag" in package_managers
    assert "Homebrew tap" in package_managers
    assert "Do not commit an unvalidated formula" in package_managers
    assert "PyPI and TestPyPI package publication" in maturity
    assert "package ownership transfer to the organization account" in maturity
    assert "GHCR container-image publication" in maturity
    assert "Transfer package ownership to the organization" in package_managers
    assert "public GHCR package visibility" in package_managers
    assert "Homebrew tap repository" in package_managers


def test_quality_scorecard_tracks_package_description_drift() -> None:
    scorecard = (PROJECT_ROOT / "docs/QUALITY_SCORECARD.md").read_text(encoding="utf-8")

    assert "bounded read-only `curl` fallback" in scorecard
    assert "Local Python certificate stores can block online release checks" in scorecard
    assert "Public package long descriptions can lag" in scorecard
    assert "recommended repair version is `0.1.0a6`" in scorecard
    assert "Release workflow prepares owner-review artifacts without publishing" in scorecard


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
