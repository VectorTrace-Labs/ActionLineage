from __future__ import annotations

import argparse
import email.parser
import json
import re
import subprocess
import sys
import tarfile
import tomllib
import urllib.error
import urllib.request
import zipfile
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

PASS = "PASS"
FAIL = "FAIL"
UNKNOWN = "UNKNOWN"
STALE_PACKAGE_DESCRIPTION_CLAIMS = (
    (
        "github_release_artifacts_attached",
        "Public alpha artifacts are attached to GitHub Releases",
    ),
    (
        "github_release_artifacts_local_proof",
        "| GitHub release artifacts and attestations | Local-proof |",
    ),
)


@dataclass(frozen=True)
class Check:
    id: str
    status: str
    summary: str
    expected: str | None = None
    actual: str | None = None
    severity: str = "P1"
    details: dict[str, Any] | None = None


def build_report(
    project_root: Path,
    *,
    dist_dir: Path | None = None,
    online: bool = False,
    repository: str = "VectorTrace-Labs/ActionLineage",
    timeout_seconds: float = 10.0,
) -> dict[str, Any]:
    project_root = project_root.resolve()
    pyproject = _load_pyproject(project_root)
    project = pyproject["project"]
    expected_version = str(project["version"])
    expected_python = str(project["requires-python"])
    checks: list[Check] = []

    runtime_version = _read_runtime_version(project_root)
    checks.append(
        _compare(
            "local.version.runtime",
            expected_version,
            runtime_version,
            "pyproject version matches actionlineage.__version__",
            severity="P0",
        )
    )

    readme_versions = _read_readme_install_versions(project_root)
    checks.append(
        _set_compare(
            "local.version.readme_install",
            {expected_version},
            readme_versions,
            "README pinned installation commands match pyproject version",
            severity="P0",
        )
    )

    changelog_version = _read_latest_changelog_version(project_root)
    checks.append(
        _compare(
            "local.version.changelog",
            expected_version,
            changelog_version,
            "CHANGELOG latest release heading matches pyproject version",
            severity="P0",
        )
    )

    checks.extend(_check_python_support(pyproject, expected_python))
    checks.extend(_check_project_urls(project))
    checks.extend(_check_local_tag(project_root, expected_version))
    checks.extend(_check_dist_metadata(dist_dir, expected_version, expected_python))

    if online:
        checks.extend(
            _check_online_state(
                expected_version=expected_version,
                expected_python=expected_python,
                repository=repository,
                project_urls=project.get("urls", {}),
                timeout_seconds=timeout_seconds,
            )
        )

    fail_count = sum(1 for check in checks if check.status == FAIL)
    unknown_count = sum(1 for check in checks if check.status == UNKNOWN)
    return {
        "schema_version": "actionlineage.dev/release-consistency-report-v0",
        "generated_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "project_root": str(project_root),
        "mode": "online" if online else "offline",
        "expected_version": expected_version,
        "expected_python": expected_python,
        "ok": fail_count == 0,
        "fail_count": fail_count,
        "unknown_count": unknown_count,
        "checks": [asdict(check) for check in checks],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check ActionLineage release consistency.")
    parser.add_argument("--project-root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--dist-dir", type=Path, default=None)
    parser.add_argument("--online", action="store_true", help="Include read-only public checks.")
    parser.add_argument(
        "--repository",
        default="VectorTrace-Labs/ActionLineage",
        help="GitHub repository in OWNER/REPO form.",
    )
    parser.add_argument("--timeout", type=float, default=10.0)
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args(argv)

    report = build_report(
        args.project_root,
        dist_dir=args.dist_dir,
        online=args.online,
        repository=args.repository,
        timeout_seconds=args.timeout,
    )
    encoded = json.dumps(report, indent=2, sort_keys=True)
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(encoded + "\n", encoding="utf-8")
    print(encoded)
    return 0 if report["ok"] else 1


def _load_pyproject(project_root: Path) -> dict[str, Any]:
    return tomllib.loads((project_root / "pyproject.toml").read_text(encoding="utf-8"))


def _read_runtime_version(project_root: Path) -> str | None:
    init_py = project_root / "src" / "actionlineage" / "__init__.py"
    match = re.search(r'^__version__\s*=\s*"([^"]+)"', init_py.read_text(encoding="utf-8"), re.M)
    return match.group(1) if match else None


def _read_readme_install_versions(project_root: Path) -> set[str]:
    readme = (project_root / "README.md").read_text(encoding="utf-8")
    return set(re.findall(r"actionlineage==([0-9][A-Za-z0-9.!+-]*)", readme))


def _read_latest_changelog_version(project_root: Path) -> str | None:
    changelog = (project_root / "CHANGELOG.md").read_text(encoding="utf-8")
    for match in re.finditer(r"^##\s+([0-9][^\s]+)\s+-\s+\d{4}-\d{2}-\d{2}\s*$", changelog, re.M):
        return match.group(1)
    return None


def _check_python_support(pyproject: dict[str, Any], expected_python: str) -> list[Check]:
    project = pyproject["project"]
    classifiers = set(project.get("classifiers", []))
    checks = [
        Check(
            id="local.python.requires",
            status=PASS if expected_python == ">=3.12" else FAIL,
            summary="requires-python declares the supported alpha floor",
            expected=">=3.12",
            actual=expected_python,
            severity="P0",
        ),
        Check(
            id="local.python.classifiers",
            status=PASS
            if {
                "Programming Language :: Python :: 3.12",
                "Programming Language :: Python :: 3.13",
            }
            <= classifiers
            else FAIL,
            summary="Python classifiers include supported 3.12 and 3.13 versions",
            expected="3.12 and 3.13 classifiers",
            actual=", ".join(
                sorted(c for c in classifiers if c.startswith("Programming Language :: Python"))
            ),
            severity="P1",
        ),
        Check(
            id="local.python.tooling",
            status=PASS
            if pyproject.get("tool", {}).get("ruff", {}).get("target-version") == "py312"
            and pyproject.get("tool", {}).get("mypy", {}).get("python_version") == "3.12"
            else FAIL,
            summary="Ruff and mypy target the documented Python floor",
            expected="py312 / 3.12",
            actual=(
                f"{pyproject.get('tool', {}).get('ruff', {}).get('target-version')} / "
                f"{pyproject.get('tool', {}).get('mypy', {}).get('python_version')}"
            ),
            severity="P1",
        ),
    ]
    return checks


def _check_project_urls(project: dict[str, Any]) -> list[Check]:
    urls = project.get("urls", {})
    expected = {"Homepage", "Repository", "Documentation", "Issues", "Changelog", "Security policy"}
    actual = set(urls)
    return [
        Check(
            id="local.metadata.project_urls",
            status=PASS if expected <= actual else FAIL,
            summary="PEP 621 project URLs include public discovery links",
            expected=", ".join(sorted(expected)),
            actual=", ".join(sorted(actual)),
            severity="P1",
            details={"urls": urls},
        )
    ]


def _check_local_tag(project_root: Path, expected_version: str) -> list[Check]:
    tag = f"v{expected_version}"
    result = _run_git(project_root, ["tag", "--list", tag])
    if result is None:
        return [
            Check(
                id="local.git.tag",
                status=UNKNOWN,
                summary="local git tags could not be inspected",
                expected=tag,
                severity="P1",
            )
        ]
    status = PASS if result.strip() == tag else FAIL
    details: dict[str, Any] = {}
    if status == PASS:
        rev = _run_git(project_root, ["rev-parse", f"{tag}^{{}}"])
        if rev:
            details["resolved_commit"] = rev.strip()
    return [
        Check(
            id="local.git.tag",
            status=status,
            summary="matching local version tag exists",
            expected=tag,
            actual=result.strip() or None,
            severity="P0",
            details=details or None,
        )
    ]


def _check_dist_metadata(
    dist_dir: Path | None, expected_version: str, expected_python: str
) -> list[Check]:
    if dist_dir is None:
        return [
            Check(
                id="dist.present",
                status=UNKNOWN,
                summary="distribution directory was not provided",
                severity="P1",
            )
        ]
    if not dist_dir.exists():
        return [
            Check(
                id="dist.present",
                status=UNKNOWN,
                summary="distribution directory does not exist",
                actual=str(dist_dir),
                severity="P1",
            )
        ]
    wheels = sorted(dist_dir.glob("*.whl"))
    sdists = sorted(dist_dir.glob("*.tar.gz"))
    checks = [
        Check(
            id="dist.artifacts.wheel",
            status=PASS if wheels else FAIL,
            summary="built wheel is present",
            expected="one or more .whl files",
            actual=", ".join(path.name for path in wheels) or None,
            severity="P0",
        ),
        Check(
            id="dist.artifacts.sdist",
            status=PASS if sdists else FAIL,
            summary="built source distribution is present",
            expected="one or more .tar.gz files",
            actual=", ".join(path.name for path in sdists) or None,
            severity="P0",
        ),
    ]
    for wheel in wheels:
        checks.extend(
            _check_metadata_file(
                f"dist.wheel.{wheel.name}",
                _read_wheel_metadata(wheel),
                expected_version,
                expected_python,
            )
        )
    for sdist in sdists:
        checks.extend(
            _check_metadata_file(
                f"dist.sdist.{sdist.name}",
                _read_sdist_metadata(sdist),
                expected_version,
                expected_python,
            )
        )
        checks.append(_check_sdist_local_state(sdist))
    return checks


def _check_metadata_file(
    prefix: str, metadata: email.message.Message | None, expected_version: str, expected_python: str
) -> list[Check]:
    if metadata is None:
        return [
            Check(
                id=f"{prefix}.metadata",
                status=FAIL,
                summary="artifact metadata could not be read",
                severity="P0",
            )
        ]
    project_urls = metadata.get_all("Project-URL", [])
    return [
        _compare(
            f"{prefix}.version",
            expected_version,
            metadata.get("Version"),
            "artifact metadata version matches pyproject",
            severity="P0",
        ),
        _compare(
            f"{prefix}.requires_python",
            expected_python,
            metadata.get("Requires-Python"),
            "artifact metadata Python requirement matches pyproject",
            severity="P0",
        ),
        Check(
            id=f"{prefix}.project_urls",
            status=PASS if len(project_urls) >= 6 else FAIL,
            summary="artifact metadata includes project URLs",
            expected="at least six Project-URL fields",
            actual=str(len(project_urls)),
            severity="P1",
            details={"project_urls": project_urls},
        ),
    ]


def _read_wheel_metadata(path: Path) -> email.message.Message | None:
    with zipfile.ZipFile(path) as archive:
        metadata_names = [
            name for name in archive.namelist() if name.endswith(".dist-info/METADATA")
        ]
        if not metadata_names:
            return None
        return email.parser.Parser().parsestr(archive.read(metadata_names[0]).decode("utf-8"))


def _read_sdist_metadata(path: Path) -> email.message.Message | None:
    with tarfile.open(path, "r:gz") as archive:
        members = [member for member in archive.getmembers() if member.name.endswith("/PKG-INFO")]
        if not members:
            return None
        extracted = archive.extractfile(members[0])
        if extracted is None:
            return None
        return email.parser.Parser().parsestr(extracted.read().decode("utf-8"))


def _check_sdist_local_state(path: Path) -> Check:
    with tarfile.open(path, "r:gz") as archive:
        local_state = [
            name
            for name in archive.getnames()
            if "/.hypothesis/" in name or "/__pycache__/" in name or name.endswith(".pyc")
        ]
    return Check(
        id=f"dist.sdist.{path.name}.local_state",
        status=PASS if not local_state else FAIL,
        summary="sdist excludes local test caches and bytecode",
        expected="no .hypothesis, __pycache__, or .pyc entries",
        actual=str(len(local_state)),
        severity="P1",
        details={"sample": local_state[:10]},
    )


def _check_online_state(
    *,
    expected_version: str,
    expected_python: str,
    repository: str,
    project_urls: dict[str, str],
    timeout_seconds: float,
) -> list[Check]:
    checks: list[Check] = []
    checks.extend(
        _check_package_index(
            "online.pypi",
            "https://pypi.org/pypi/actionlineage/json",
            expected_version,
            expected_python,
            timeout_seconds,
        )
    )
    checks.extend(
        _check_package_index(
            "online.testpypi",
            "https://test.pypi.org/pypi/actionlineage/json",
            expected_version,
            expected_python,
            timeout_seconds,
        )
    )
    checks.extend(_check_github(repository, expected_version, timeout_seconds))
    checks.extend(_check_url_heads(project_urls, timeout_seconds))
    return checks


def _check_package_index(
    prefix: str, url: str, expected_version: str, expected_python: str, timeout_seconds: float
) -> list[Check]:
    data, error = _fetch_json(url, timeout_seconds)
    if error is not None:
        return [
            Check(
                id=f"{prefix}.reachable",
                status=UNKNOWN,
                summary="package index JSON could not be fetched",
                actual=error,
                severity="P1",
            )
        ]
    assert data is not None
    info = data.get("info", {})
    urls = data.get("urls", [])
    filenames = [str(item.get("filename")) for item in urls]
    checks = [
        _compare(
            f"{prefix}.version",
            expected_version,
            str(info.get("version")),
            "public package index latest version matches pyproject",
            severity="P0",
        ),
        _compare(
            f"{prefix}.requires_python",
            expected_python,
            str(info.get("requires_python")),
            "public package Python requirement matches pyproject",
            severity="P0",
        ),
        Check(
            id=f"{prefix}.artifacts",
            status=PASS
            if any(name.endswith(".whl") for name in filenames)
            and any(name.endswith(".tar.gz") for name in filenames)
            else FAIL,
            summary="public package index exposes wheel and sdist for latest version",
            expected="wheel and sdist",
            actual=", ".join(filenames) or None,
            severity="P0",
        ),
        Check(
            id=f"{prefix}.project_urls",
            status=PASS if info.get("project_urls") else FAIL,
            summary="public package metadata exposes project URLs",
            expected="project_urls present",
            actual=json.dumps(info.get("project_urls"), sort_keys=True),
            severity="P1",
        ),
    ]
    checks.append(
        _check_public_description_claims(
            prefix=prefix,
            description=info.get("description"),
            expected_version=expected_version,
        )
    )
    return checks


def _check_public_description_claims(
    *, prefix: str, description: object, expected_version: str
) -> Check:
    if not isinstance(description, str):
        return Check(
            id=f"{prefix}.description_claims",
            status=UNKNOWN,
            summary="public package long description could not be inspected",
            expected="description string",
            actual=type(description).__name__,
            severity="P1",
        )
    stale_claims = [
        claim_id for claim_id, needle in STALE_PACKAGE_DESCRIPTION_CLAIMS if needle in description
    ]
    pending_publish_phrase = f"After the `{expected_version}` Trusted Publishing run completes"
    if pending_publish_phrase in description:
        stale_claims.append("trusted_publishing_run_pending")
    return Check(
        id=f"{prefix}.description_claims",
        status=PASS if not stale_claims else FAIL,
        summary="public package long description avoids stale owner-gated release claims",
        expected="no known stale GitHub Release or pending-publication wording",
        actual=", ".join(stale_claims) or "none",
        severity="P1",
        details={"stale_claims": stale_claims} if stale_claims else None,
    )


def _check_github(repository: str, expected_version: str, timeout_seconds: float) -> list[Check]:
    tag = f"v{expected_version}"
    tags, tags_error = _fetch_json(
        f"https://api.github.com/repos/{repository}/tags", timeout_seconds
    )
    release, release_error = _fetch_json(
        f"https://api.github.com/repos/{repository}/releases/tags/{tag}", timeout_seconds
    )
    checks = []
    if tags_error is not None:
        checks.append(
            Check(
                id="online.github.tag",
                status=UNKNOWN,
                summary="GitHub tags could not be fetched",
                expected=tag,
                actual=tags_error,
                severity="P1",
            )
        )
    else:
        tag_names = {str(item.get("name")) for item in tags or []}
        checks.append(
            Check(
                id="online.github.tag",
                status=PASS if tag in tag_names else FAIL,
                summary="GitHub exposes the expected version tag",
                expected=tag,
                actual=", ".join(sorted(tag_names)) or None,
                severity="P0",
            )
        )
    if release_error is not None:
        status = FAIL if _is_not_found_error(release_error) else UNKNOWN
        checks.append(
            Check(
                id="online.github.release",
                status=status,
                summary="GitHub exposes a release object for the expected tag",
                expected=tag,
                actual=release_error,
                severity="P0",
            )
        )
    else:
        checks.append(
            Check(
                id="online.github.release",
                status=PASS if str((release or {}).get("tag_name")) == tag else FAIL,
                summary="GitHub release object tag matches expected version",
                expected=tag,
                actual=str((release or {}).get("tag_name")),
                severity="P0",
            )
        )
    return checks


def _is_not_found_error(error: str) -> bool:
    return "HTTP 404" in error or "returned error: 404" in error


def _check_url_heads(project_urls: dict[str, str], timeout_seconds: float) -> list[Check]:
    checks: list[Check] = []
    for name, url in sorted(project_urls.items()):
        details: dict[str, Any] = {"url": url}
        request = urllib.request.Request(
            url,
            method="HEAD",
            headers={"User-Agent": "actionlineage-release-consistency/0"},
        )
        try:
            with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
                status_code = response.status
        except urllib.error.HTTPError as exc:
            status_code = exc.code
        except (OSError, urllib.error.URLError) as exc:
            status_code, fallback_error = _fetch_head_status_with_curl(
                url, timeout_seconds, str(exc)
            )
            if fallback_error is not None:
                checks.append(
                    Check(
                        id=f"online.project_url.{_slug(name)}",
                        status=UNKNOWN,
                        summary=f"project URL could not be checked: {name}",
                        actual=fallback_error,
                        severity="P2",
                        details=details,
                    )
                )
                continue
            assert status_code is not None
            details["fallback"] = "curl"
            details["original_error"] = str(exc)
        checks.append(
            Check(
                id=f"online.project_url.{_slug(name)}",
                status=PASS if 200 <= status_code < 400 else FAIL,
                summary=f"project URL is reachable: {name}",
                expected="2xx or 3xx",
                actual=str(status_code),
                severity="P1",
                details=details,
            )
        )
    return checks


def _fetch_json(url: str, timeout_seconds: float) -> tuple[Any | None, str | None]:
    request = urllib.request.Request(
        url, headers={"User-Agent": "actionlineage-release-consistency/0"}
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            return json.loads(response.read().decode("utf-8")), None
    except urllib.error.HTTPError as exc:
        return None, f"HTTP {exc.code}: {exc.reason}"
    except json.JSONDecodeError as exc:
        return None, str(exc)
    except (OSError, urllib.error.URLError) as exc:
        return _fetch_json_with_curl(url, timeout_seconds, str(exc))


def _fetch_json_with_curl(
    url: str, timeout_seconds: float, original_error: str
) -> tuple[Any | None, str | None]:
    curl_timeout = max(1.0, timeout_seconds)
    command = [
        "curl",
        "--fail",
        "--silent",
        "--show-error",
        "--location",
        "--max-time",
        str(curl_timeout),
        "--user-agent",
        "actionlineage-release-consistency/0",
        url,
    ]
    try:
        result = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            timeout=curl_timeout + 1.0,
        )
    except FileNotFoundError as exc:
        return None, f"{original_error}; curl fallback unavailable: {exc}"
    except subprocess.TimeoutExpired:
        return None, f"{original_error}; curl fallback timed out after {curl_timeout} seconds"
    if result.returncode != 0:
        diagnostic = result.stderr.strip() or result.stdout.strip() or "no diagnostic"
        return None, f"{original_error}; curl fallback failed ({result.returncode}): {diagnostic}"
    try:
        return json.loads(result.stdout), None
    except json.JSONDecodeError as exc:
        return None, f"{original_error}; curl fallback returned invalid JSON: {exc}"


def _fetch_head_status_with_curl(
    url: str, timeout_seconds: float, original_error: str
) -> tuple[int | None, str | None]:
    curl_timeout = max(1.0, timeout_seconds)
    command = [
        "curl",
        "--head",
        "--silent",
        "--show-error",
        "--location",
        "--max-time",
        str(curl_timeout),
        "--output",
        "/dev/null",
        "--write-out",
        "%{http_code}",
        "--user-agent",
        "actionlineage-release-consistency/0",
        url,
    ]
    try:
        result = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            timeout=curl_timeout + 1.0,
        )
    except FileNotFoundError as exc:
        return None, f"{original_error}; curl HEAD fallback unavailable: {exc}"
    except subprocess.TimeoutExpired:
        return None, f"{original_error}; curl HEAD fallback timed out after {curl_timeout} seconds"
    status_text = result.stdout.strip()
    if result.returncode != 0:
        diagnostic = result.stderr.strip() or status_text or "no diagnostic"
        return (
            None,
            f"{original_error}; curl HEAD fallback failed ({result.returncode}): {diagnostic}",
        )
    if not status_text.isdecimal():
        return None, f"{original_error}; curl HEAD fallback returned invalid status: {status_text}"
    status_code = int(status_text)
    if status_code == 0:
        return None, f"{original_error}; curl HEAD fallback returned no HTTP status"
    return status_code, None


def _compare(
    check_id: str,
    expected: str | None,
    actual: str | None,
    summary: str,
    *,
    severity: str,
) -> Check:
    return Check(
        id=check_id,
        status=PASS if expected == actual else FAIL,
        summary=summary,
        expected=expected,
        actual=actual,
        severity=severity,
    )


def _set_compare(
    check_id: str,
    expected: set[str],
    actual: set[str],
    summary: str,
    *,
    severity: str,
) -> Check:
    return Check(
        id=check_id,
        status=PASS if expected == actual else FAIL,
        summary=summary,
        expected=", ".join(sorted(expected)),
        actual=", ".join(sorted(actual)),
        severity=severity,
    )


def _run_git(project_root: Path, args: list[str]) -> str | None:
    try:
        result = subprocess.run(
            ["git", *args],
            cwd=project_root,
            check=True,
            text=True,
            capture_output=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return None
    return result.stdout


def _slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_")


if __name__ == "__main__":
    sys.exit(main())
