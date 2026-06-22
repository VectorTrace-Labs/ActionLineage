from __future__ import annotations

import importlib.util
import json
import string
import sys
from pathlib import Path
from types import ModuleType

from hypothesis import given, settings
from hypothesis import strategies as st

from actionlineage.demo import run_demo
from actionlineage.domain import RedactionPolicy, capture_string, serialize_event_for_persistence
from tests.domain.test_events import build_event

PROJECT_ROOT = Path(__file__).resolve().parents[2]
ADVERSARIAL_FIXTURE = PROJECT_ROOT / "tests/fixtures/adversarial/security-regressions.json"


def test_claim_language_guard_passes_current_repository() -> None:
    scanner = _load_script("check_claims_language")

    findings = scanner.scan_paths([PROJECT_ROOT])

    assert findings == []


def test_claim_language_guard_flags_positive_overclaim(tmp_path: Path) -> None:
    scanner = _load_script("check_claims_language")
    claim_file = tmp_path / "claim.md"
    claim_file.write_text("This product is tamper" + "-proof.\n", encoding="utf-8")

    findings = scanner.scan_paths([claim_file])

    assert len(findings) == 1
    assert findings[0].phrase == "tamper" + "-proof"


def test_claim_language_guard_skips_local_assistant_docs_by_default(tmp_path: Path) -> None:
    scanner = _load_script("check_claims_language")
    local_doc = tmp_path / "Uplift.md"
    local_doc.write_text("This includes the phrase tamper" + "-proof.\n", encoding="utf-8")

    assert scanner.scan_paths([tmp_path]) == []
    assert len(scanner.scan_paths([tmp_path], include_local_only=True)) == 1


def test_secret_scan_passes_current_repository() -> None:
    scanner = _load_script("secret_scan")

    findings = scanner.scan_paths([PROJECT_ROOT])

    assert findings == []


def test_secret_scan_flags_private_key(tmp_path: Path) -> None:
    scanner = _load_script("secret_scan")
    secret_file = tmp_path / "leak.txt"
    secret_file.write_text(
        "-----BEGIN " + "PRIVATE KEY-----\nnot-a-real-key\n-----END PRIVATE KEY-----\n",
        encoding="utf-8",
    )

    findings = scanner.scan_paths([secret_file])

    assert len(findings) == 1
    assert findings[0].kind == "private_key"


def test_secret_scan_skips_local_assistant_docs_by_default(tmp_path: Path) -> None:
    scanner = _load_script("secret_scan")
    local_doc = tmp_path / "AGENTS.md"
    local_doc.write_text("Bearer " + "local-only-token-value-1234567890\n", encoding="utf-8")

    assert scanner.scan_paths([tmp_path]) == []
    assert len(scanner.scan_paths([tmp_path], include_local_only=True)) == 1


def test_markdown_link_check_passes_current_repository() -> None:
    checker = _load_script("check_markdown_links")

    result = checker.scan_paths([PROJECT_ROOT], repository_root=PROJECT_ROOT)

    assert result.ok
    assert result.issues == ()
    assert result.checked_links >= 40


def test_markdown_link_check_flags_missing_and_escaping_targets(tmp_path: Path) -> None:
    checker = _load_script("check_markdown_links")
    readme = tmp_path / "README.md"
    readme.write_text(
        "[missing](docs/missing.md)\n"
        "[escape](../outside.md)\n"
        "[external](https://example.com/actionlineage)\n"
        "```md\n"
        "[ignored](missing-in-code-fence.md)\n"
        "```\n",
        encoding="utf-8",
    )

    result = checker.scan_paths([tmp_path], repository_root=tmp_path)

    assert not result.ok
    assert result.checked_links == 2
    assert [issue.code for issue in result.issues] == [
        "missing_target",
        "target_escapes_repository",
    ]


def test_markdown_link_check_handles_reference_links_and_file_uris(tmp_path: Path) -> None:
    checker = _load_script("check_markdown_links")
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir()
    (docs_dir / "guide.md").write_text("# Guide\n", encoding="utf-8")
    readme = tmp_path / "README.md"
    readme.write_text(
        "[guide]: docs/guide.md\n"
        "[Guide][guide]\n"
        "[local-file](file:///tmp/actionlineage-secret.md)\n",
        encoding="utf-8",
    )

    result = checker.scan_paths([tmp_path], repository_root=tmp_path)

    assert not result.ok
    assert result.checked_links == 2
    assert [issue.code for issue in result.issues] == ["file_uri"]


def test_public_quickstart_smoke_runs_local_cli(tmp_path: Path) -> None:
    smoker = _load_script("smoke_public_quickstart")

    result = smoker.run_smoke(
        cli_prefix=("uv", "run", "actionlineage"),
        output_dir=tmp_path / "quickstart",
        contract_path=PROJECT_ROOT / "contracts/examples/outbound-http.json",
    )

    assert result.ok
    assert [step.name for step in result.steps] == [
        "version",
        "demo",
        "demo_artifacts_exist",
        "journal_verify",
        "contract_validate",
        "case_export",
        "case_export_artifacts_exist",
        "console_export",
        "console_export_artifacts_exist",
    ]
    assert (tmp_path / "quickstart/demo/evidence.jsonl").exists()
    assert (tmp_path / "quickstart/case/case.json").exists()
    assert (tmp_path / "quickstart/console.html").exists()


def test_public_quickstart_smoke_builds_uvx_package_prefix() -> None:
    smoker = _load_script("smoke_public_quickstart")
    args = smoker._parse_args(
        (
            "--package-spec",
            "actionlineage==0.1.0a3",
            "--uvx-prerelease",
            "allow",
        )
    )

    assert smoker.cli_prefix_from_args(args) == (
        "uvx",
        "--prerelease",
        "allow",
        "--from",
        "actionlineage==0.1.0a3",
        "actionlineage",
    )


def test_public_quickstart_smoke_fails_when_expected_artifacts_are_missing(
    monkeypatch,
    tmp_path: Path,
) -> None:
    smoker = _load_script("smoke_public_quickstart")

    def fake_run_step(*, name: str, command: tuple[str, ...], timeout_seconds: float):
        assert timeout_seconds == smoker.DEFAULT_STEP_TIMEOUT_SECONDS
        return smoker.SmokeStep(
            name=name,
            command=command,
            exit_code=0,
            stdout="0.1.0a3\n" if name == "version" else "{}\n",
            stderr="",
        )

    monkeypatch.setattr(smoker, "_run_step", fake_run_step)

    result = smoker.run_smoke(
        cli_prefix=("actionlineage",),
        output_dir=tmp_path / "quickstart",
        contract_path=PROJECT_ROOT / "contracts/examples/outbound-http.json",
    )

    assert not result.ok
    assert result.steps[-1].name == "demo_artifacts_exist"
    assert "evidence.jsonl" in result.steps[-1].stdout


def test_public_quickstart_smoke_reports_timed_out_step(monkeypatch) -> None:
    smoker = _load_script("smoke_public_quickstart")

    def fake_run(*args, **kwargs):
        raise smoker.subprocess.TimeoutExpired(
            cmd=args[0],
            timeout=kwargs["timeout"],
            output="partial stdout",
            stderr="partial stderr",
        )

    monkeypatch.setattr(smoker.subprocess, "run", fake_run)

    result = smoker._run_step(
        name="demo",
        command=("actionlineage", "demo", "run"),
        timeout_seconds=0.01,
    )

    assert result.exit_code == 124
    assert "partial stdout" in result.stdout
    assert "partial stderr" in result.stderr
    assert "step timed out after 0.01 seconds" in result.stderr


def test_ci_quality_summary_reports_coverage_and_artifacts(tmp_path: Path) -> None:
    writer = _load_script("write_ci_quality_summary")
    coverage_xml = tmp_path / "coverage.xml"
    coverage_xml.write_text(
        '<coverage lines-valid="100" lines-covered="90" '
        'branches-valid="50" branches-covered="39" />',
        encoding="utf-8",
    )
    sbom_path = tmp_path / "sbom.json"
    provenance_path = tmp_path / "provenance.json"
    dist_dir = tmp_path / "dist"
    wheel_smoke_dir = tmp_path / "wheel-smoke"
    sdist_smoke_dir = tmp_path / "sdist-smoke"
    demo_map_svg = tmp_path / "demo" / "demo-evidence-map.svg"
    sbom_path.write_text("{}", encoding="utf-8")
    provenance_path.write_text("{}", encoding="utf-8")
    dist_dir.mkdir()
    (dist_dir / "actionlineage-0.1.0a3-py3-none-any.whl").write_text("", encoding="utf-8")
    (dist_dir / "actionlineage-0.1.0a3.tar.gz").write_text("", encoding="utf-8")
    demo_map_svg.parent.mkdir()
    demo_map_svg.write_text("<svg />", encoding="utf-8")
    _write_quickstart_smoke_artifacts(wheel_smoke_dir)
    _write_quickstart_smoke_artifacts(sdist_smoke_dir)

    result = writer.build_summary(
        python_version="3.13.5",
        coverage_xml=coverage_xml,
        coverage_floor=85,
        sbom_path=sbom_path,
        provenance_path=provenance_path,
        dist_dir=dist_dir,
        wheel_smoke_dir=wheel_smoke_dir,
        sdist_smoke_dir=sdist_smoke_dir,
        demo_map_svg=demo_map_svg,
    )

    assert result.ok
    assert "Branch-enabled total coverage: `86.00%`" in result.markdown
    assert "Line coverage: `90.00%`" in result.markdown
    assert "Branch coverage: `78.00%`" in result.markdown
    assert "| Wheel quickstart smoke | PASS |" in result.markdown
    assert "Agent Validation Lab evidence is produced by the dedicated" in result.markdown


def test_ci_quality_summary_reports_missing_evidence(tmp_path: Path) -> None:
    writer = _load_script("write_ci_quality_summary")

    result = writer.build_summary(
        python_version="3.13.5",
        coverage_xml=tmp_path / "missing-coverage.xml",
        coverage_floor=85,
        sbom_path=tmp_path / "missing-sbom.json",
        provenance_path=tmp_path / "missing-provenance.json",
        dist_dir=tmp_path / "missing-dist",
        wheel_smoke_dir=tmp_path / "missing-wheel-smoke",
        sdist_smoke_dir=tmp_path / "missing-sdist-smoke",
        demo_map_svg=tmp_path / "missing-demo-map.svg",
    )

    assert not result.ok
    assert "Branch-enabled total coverage: `MISSING`" in result.markdown
    assert "coverage XML not found" in result.markdown
    assert "| SBOM | MISSING |" in result.markdown
    assert "| Wheel quickstart smoke | MISSING |" in result.markdown


def test_lightweight_sbom_includes_runtime_dependency() -> None:
    generator = _load_script("generate_sbom")

    sbom = generator.build_sbom(PROJECT_ROOT / "pyproject.toml")
    packages = {(package["scope"], package["name"]) for package in sbom["packages"]}

    assert sbom["bom_format"] == "actionlineage.dev/simple-sbom-v0"
    assert sbom["project"]["license"] == "Apache-2.0"
    assert ("runtime:pydantic>=2.10,<3", "pydantic") in packages
    assert all("license" in package for package in sbom["packages"])


def test_release_provenance_hashes_dist_artifacts_without_signing_claims(tmp_path: Path) -> None:
    generator = _load_script("generate_release_provenance")
    dist_dir = tmp_path / "dist"
    dist_dir.mkdir()
    artifact = dist_dir / "actionlineage-0.1.0a1-py3-none-any.whl"
    artifact.write_bytes(b"wheel-bytes")
    (dist_dir / ".gitignore").write_text("*\n", encoding="utf-8")

    provenance = generator.build_release_provenance(PROJECT_ROOT / "pyproject.toml", dist_dir)

    assert provenance["provenance_format"] == "actionlineage.dev/release-provenance-v0"
    assert provenance["builder"]["signature"] is None
    assert "unsigned local manifest" in provenance["builder"]["limitations"]
    assert provenance["subjects"] == [
        {
            "path": "actionlineage-0.1.0a1-py3-none-any.whl",
            "sha256": ("sha256:9ceb18f15662bb87e54af2f5953c0484d2ef76f5444d87913360b9ef87d7296d"),
            "size_bytes": 11,
        }
    ]


def test_demo_evidence_map_is_deterministic_and_checkable(tmp_path: Path) -> None:
    generator = _load_script("generate_demo_evidence_map")
    demo = run_demo(tmp_path / "demo")
    svg_path = tmp_path / "demo-evidence-map.svg"
    summary_path = tmp_path / "demo-evidence-map.json"

    evidence_map = generator.build_evidence_map(demo.incident_path)
    svg = generator.render_svg(evidence_map)
    written = generator.write_evidence_map(demo.incident_path, svg_path, summary_path)

    assert evidence_map["map_format"] == "actionlineage.dev/demo-evidence-map-v0"
    assert evidence_map["ok"] is True
    assert evidence_map["event_count"] == 18
    assert evidence_map["verification_status_counts"]["verified"] == 1
    assert evidence_map["verification_status_counts"]["unverified"] == 2
    assert evidence_map["verification_status_counts"]["conflicting"] == 1
    assert evidence_map["verification_status_counts"]["not_dispatched"] == 1
    assert "Tool acknowledgement is not side-effect evidence" in svg
    assert generator.render_svg(evidence_map) == svg
    assert written == evidence_map
    assert generator.check_evidence_map(demo.incident_path, svg_path, summary_path) == []

    svg_path.write_text(svg.replace("ActionLineage", "Changed", 1), encoding="utf-8")

    assert generator.check_evidence_map(demo.incident_path, svg_path, summary_path) == ["svg_stale"]


def test_adversarial_fixture_categories_are_complete() -> None:
    fixture = json.loads(ADVERSARIAL_FIXTURE.read_text(encoding="utf-8"))

    categories = {case["category"] for case in fixture["cases"]}

    assert categories == {
        "conflicting_observer",
        "correlation_ambiguity",
        "descriptor_drift",
        "malformed_adapter_payload",
        "oversized_payload",
        "prompt_injection",
        "replayed_approval",
    }


@settings(max_examples=25, derandomize=True)
@given(st.text(alphabet=string.ascii_letters + string.digits, min_size=8, max_size=48))
def test_bearer_token_redaction_property(token: str) -> None:
    bearer = f"Bearer {token}"
    event = build_event(payload={"headers": {"authorization": bearer}, "note": bearer})

    serialized = serialize_event_for_persistence(event).decode("utf-8")

    assert token not in serialized
    assert bearer not in serialized


@settings(max_examples=25, derandomize=True)
@given(st.text(min_size=0, max_size=256))
def test_capture_string_respects_configured_bound(value: str) -> None:
    captured = capture_string(value, max_length=16)

    if isinstance(captured, dict):
        assert captured["captured_length"] <= 16
        assert len(str(captured["value"])) <= 16
        assert captured["digest"].startswith("sha256:")
    else:
        assert len(captured) <= 16


@settings(max_examples=20, derandomize=True)
@given(st.dictionaries(st.sampled_from(["password", "api_key", "note"]), st.text(max_size=64)))
def test_sensitive_field_names_are_redacted_property(payload: dict[str, str]) -> None:
    redacted = RedactionPolicy().apply(payload)

    if "password" in payload:
        assert redacted["password"]["marker"] == "actionlineage.redacted.v1"
    if "api_key" in payload:
        assert redacted["api_key"]["marker"] == "actionlineage.redacted.v1"


def _load_script(name: str) -> ModuleType:
    script_path = PROJECT_ROOT / "scripts" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, script_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _write_quickstart_smoke_artifacts(path: Path) -> None:
    (path / "demo").mkdir(parents=True)
    (path / "case").mkdir()
    (path / "demo" / "evidence.jsonl").write_text("{}", encoding="utf-8")
    (path / "case" / "case.json").write_text("{}", encoding="utf-8")
    (path / "console.html").write_text("<html></html>", encoding="utf-8")
