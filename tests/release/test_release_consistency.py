from __future__ import annotations

import importlib.util
import io
import sys
import tarfile
import zipfile
from pathlib import Path
from types import ModuleType

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def test_release_consistency_offline_current_repo_has_no_failures() -> None:
    checker = _load_checker()

    report = checker.build_report(PROJECT_ROOT)

    assert report["ok"] is True
    assert report["fail_count"] == 0
    checks = {check["id"]: check for check in report["checks"]}
    assert checks["local.version.runtime"]["status"] == "PASS"
    assert checks["local.version.readme_install"]["status"] == "PASS"
    assert checks["local.version.changelog"]["status"] == "PASS"
    assert checks["local.metadata.project_urls"]["status"] == "PASS"
    assert checks["dist.present"]["status"] == "UNKNOWN"


def test_release_consistency_detects_runtime_version_mismatch(tmp_path: Path) -> None:
    checker = _load_checker()
    _write_minimal_project(tmp_path, runtime_version="1.2.4")

    report = checker.build_report(tmp_path)

    checks = {check["id"]: check for check in report["checks"]}
    assert report["ok"] is False
    assert checks["local.version.runtime"]["status"] == "FAIL"
    assert checks["local.version.runtime"]["expected"] == "1.2.3"
    assert checks["local.version.runtime"]["actual"] == "1.2.4"


def test_release_consistency_rejects_sdist_local_state(tmp_path: Path) -> None:
    checker = _load_checker()
    dist_dir = tmp_path / "dist"
    dist_dir.mkdir()
    metadata = _metadata("0.1.0a3", ">=3.12")
    _write_wheel(dist_dir / "actionlineage-0.1.0a3-py3-none-any.whl", metadata)
    _write_sdist(
        dist_dir / "actionlineage-0.1.0a3.tar.gz",
        metadata,
        extra_name="actionlineage-0.1.0a3/.hypothesis/constants/example",
    )

    report = checker.build_report(PROJECT_ROOT, dist_dir=dist_dir)

    checks = {check["id"]: check for check in report["checks"]}
    assert report["ok"] is False
    assert checks["dist.sdist.actionlineage-0.1.0a3.tar.gz.local_state"]["status"] == "FAIL"
    assert checks["dist.wheel.actionlineage-0.1.0a3-py3-none-any.whl.version"]["status"] == "PASS"
    assert checks["dist.sdist.actionlineage-0.1.0a3.tar.gz.version"]["status"] == "PASS"


def test_release_consistency_flags_stale_public_description_claims() -> None:
    checker = _load_checker()

    check = checker._check_public_description_claims(
        prefix="online.pypi",
        description=(
            "| GitHub release artifacts and attestations | Local-proof |\n"
            "Public alpha artifacts are attached to GitHub Releases.\n"
            "After the `0.1.0a3` Trusted Publishing run completes, run the package."
        ),
        expected_version="0.1.0a3",
    )

    assert check.status == "FAIL"
    assert check.id == "online.pypi.description_claims"
    assert check.severity == "P1"
    assert check.details == {
        "stale_claims": [
            "github_release_artifacts_attached",
            "github_release_artifacts_local_proof",
            "trusted_publishing_run_pending",
        ]
    }


def test_fetch_json_falls_back_to_bounded_curl_after_url_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    checker = _load_checker()
    url = "https://example.test/data.json"
    observed_args: list[str] = []

    def fail_urlopen(*_args: object, **_kwargs: object) -> object:
        raise checker.urllib.error.URLError("certificate verify failed")

    def fake_run(
        args: list[str], *, check: bool, capture_output: bool, text: bool, timeout: float
    ) -> object:
        observed_args[:] = args
        assert check is False
        assert capture_output is True
        assert text is True
        assert timeout == 4.5
        return checker.subprocess.CompletedProcess(args, 0, stdout='{"ok": true}', stderr="")

    monkeypatch.setattr(checker.urllib.request, "urlopen", fail_urlopen)
    monkeypatch.setattr(checker.subprocess, "run", fake_run)

    data, error = checker._fetch_json(url, 3.5)

    assert data == {"ok": True}
    assert error is None
    assert observed_args == [
        "curl",
        "--fail",
        "--silent",
        "--show-error",
        "--location",
        "--max-time",
        "3.5",
        "--user-agent",
        "actionlineage-release-consistency/0",
        url,
    ]


def test_fetch_json_reports_urllib_and_curl_fallback_failures(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    checker = _load_checker()

    def fail_urlopen(*_args: object, **_kwargs: object) -> object:
        raise checker.urllib.error.URLError("certificate verify failed")

    def fake_run(
        args: list[str], *, check: bool, capture_output: bool, text: bool, timeout: float
    ) -> object:
        assert check is False
        assert capture_output is True
        assert text is True
        assert timeout == 4.5
        return checker.subprocess.CompletedProcess(
            args,
            60,
            stdout="",
            stderr="curl: (60) SSL certificate problem",
        )

    monkeypatch.setattr(checker.urllib.request, "urlopen", fail_urlopen)
    monkeypatch.setattr(checker.subprocess, "run", fake_run)

    data, error = checker._fetch_json("https://example.test/data.json", 3.5)

    assert data is None
    assert error is not None
    assert "certificate verify failed" in error
    assert "curl fallback failed (60)" in error
    assert "SSL certificate problem" in error


def test_github_release_404_from_curl_fallback_is_a_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    checker = _load_checker()

    def fake_fetch_json(url: str, _timeout_seconds: float) -> tuple[object | None, str | None]:
        if url.endswith("/tags"):
            return [{"name": "v0.1.0a3"}], None
        return (
            None,
            "urlopen TLS failure; curl fallback failed (56): "
            "curl: (56) The requested URL returned error: 404",
        )

    monkeypatch.setattr(checker, "_fetch_json", fake_fetch_json)

    checks = checker._check_github("VectorTrace-Labs/ActionLineage", "0.1.0a3", 10.0)

    by_id = {check.id: check for check in checks}
    assert by_id["online.github.tag"].status == "PASS"
    assert by_id["online.github.release"].status == "FAIL"


def _load_checker() -> ModuleType:
    script_path = PROJECT_ROOT / "scripts" / "check_release_consistency.py"
    spec = importlib.util.spec_from_file_location("check_release_consistency", script_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["check_release_consistency"] = module
    spec.loader.exec_module(module)
    return module


def _write_minimal_project(project_root: Path, *, runtime_version: str) -> None:
    (project_root / "src" / "actionlineage").mkdir(parents=True)
    (project_root / "src" / "actionlineage" / "__init__.py").write_text(
        f'__version__ = "{runtime_version}"\n', encoding="utf-8"
    )
    (project_root / "README.md").write_text(
        "uvx --from actionlineage==1.2.3 actionlineage version\n", encoding="utf-8"
    )
    (project_root / "CHANGELOG.md").write_text(
        "# Changelog\n\n## Unreleased\n\nNo unreleased changes.\n\n## 1.2.3 - 2026-06-22\n",
        encoding="utf-8",
    )
    (project_root / "pyproject.toml").write_text(
        """
[project]
name = "actionlineage"
version = "1.2.3"
requires-python = ">=3.12"
classifiers = [
  "Programming Language :: Python :: 3.12",
  "Programming Language :: Python :: 3.13",
]

[project.urls]
Homepage = "https://github.com/VectorTrace-Labs/ActionLineage"
Repository = "https://github.com/VectorTrace-Labs/ActionLineage"
Documentation = "https://github.com/VectorTrace-Labs/ActionLineage#readme"
Issues = "https://github.com/VectorTrace-Labs/ActionLineage/issues"
Changelog = "https://github.com/VectorTrace-Labs/ActionLineage/blob/main/CHANGELOG.md"
"Security policy" = "https://github.com/VectorTrace-Labs/ActionLineage/security/policy"

[tool.ruff]
target-version = "py312"

[tool.mypy]
python_version = "3.12"
""".lstrip(),
        encoding="utf-8",
    )


def _metadata(version: str, requires_python: str) -> str:
    return f"""Metadata-Version: 2.4
Name: actionlineage
Version: {version}
Requires-Python: {requires_python}
Project-URL: Homepage, https://github.com/VectorTrace-Labs/ActionLineage
Project-URL: Repository, https://github.com/VectorTrace-Labs/ActionLineage
Project-URL: Documentation, https://github.com/VectorTrace-Labs/ActionLineage#readme
Project-URL: Issues, https://github.com/VectorTrace-Labs/ActionLineage/issues
Project-URL: Changelog, https://github.com/VectorTrace-Labs/ActionLineage/blob/main/CHANGELOG.md
Project-URL: Security policy, https://github.com/VectorTrace-Labs/ActionLineage/security/policy
"""


def _write_wheel(path: Path, metadata: str) -> None:
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("actionlineage-0.1.0a3.dist-info/METADATA", metadata)


def _write_sdist(path: Path, metadata: str, *, extra_name: str) -> None:
    with tarfile.open(path, "w:gz") as archive:
        _add_tar_bytes(archive, "actionlineage-0.1.0a3/PKG-INFO", metadata.encode("utf-8"))
        _add_tar_bytes(archive, extra_name, b"cache")


def _add_tar_bytes(archive: tarfile.TarFile, name: str, payload: bytes) -> None:
    info = tarfile.TarInfo(name)
    info.size = len(payload)
    archive.addfile(info, io.BytesIO(payload))
