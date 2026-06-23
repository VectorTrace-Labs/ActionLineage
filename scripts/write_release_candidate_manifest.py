#!/usr/bin/env python3
"""Write a local release-candidate manifest from generated proof artifacts."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import tomllib
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

MANIFEST_SCHEMA_VERSION = "actionlineage.dev/release-candidate-manifest-v0"
REQUIRED_ARTIFACT_PATTERNS = (
    "dist/*.whl",
    "dist/*.tar.gz",
    "actionlineage-sbom.json",
    "actionlineage-license-report.json",
    "actionlineage-release-provenance.json",
    "SHA256SUMS.txt",
)
OPTIONAL_ARTIFACT_PATTERNS = (
    "coverage.xml",
    "release-consistency-offline.json",
    "release-consistency-online.json",
)


@dataclass(frozen=True, slots=True)
class ManifestResult:
    """Generated manifest and validation issues found while building it."""

    ok: bool
    manifest: dict[str, Any]
    issues: tuple[dict[str, str], ...]


def build_release_candidate_manifest(
    *,
    project_path: Path,
    artifact_root: Path,
    repository_root: Path,
    audited_implementation_commit: str | None = None,
    gates: Sequence[Mapping[str, str]] = (),
    generated_at: datetime | None = None,
) -> ManifestResult:
    """Build a JSON-compatible release-candidate manifest from local artifacts."""

    repository_root = repository_root.resolve()
    artifact_root = artifact_root.resolve()
    project = tomllib.loads(project_path.read_text(encoding="utf-8"))["project"]
    release = str(project["version"])
    issues: list[dict[str, str]] = []
    artifacts, artifact_issues = _artifact_rows(
        artifact_root=artifact_root,
        repository_root=repository_root,
    )
    issues.extend(artifact_issues)
    commit = audited_implementation_commit or _git_head(repository_root)
    if commit is None:
        commit = "UNKNOWN"
        issues.append(
            {
                "code": "commit_unknown",
                "path": str(repository_root),
                "message": "could not resolve audited implementation commit",
            }
        )

    generated = generated_at or datetime.now(tz=UTC)
    manifest: dict[str, Any] = {
        "schema_version": MANIFEST_SCHEMA_VERSION,
        "generated_at": generated.isoformat().replace("+00:00", "Z"),
        "release": release,
        "artifact_root": _display_path(artifact_root, repository_root=repository_root),
        "audited_implementation_commit": commit,
        "artifacts": artifacts,
        "gates": [_gate_row(gate) for gate in gates],
    }
    sbom_count = _sbom_package_count(artifact_root / "actionlineage-sbom.json")
    if sbom_count is not None:
        manifest["sbom_package_count"] = sbom_count
    license_report = _license_report_summary(artifact_root / "actionlineage-license-report.json")
    if license_report is not None:
        manifest["license_report"] = license_report
    public_state = _public_state_summary(artifact_root, release=release)
    if public_state:
        manifest["public_state"] = public_state
    return ManifestResult(ok=not issues, manifest=manifest, issues=tuple(issues))


def main(argv: Sequence[str] | None = None) -> int:
    """Run the release-candidate manifest writer."""

    try:
        args = _parse_args(tuple(sys.argv[1:] if argv is None else argv))
        gates = tuple(_parse_gate(value) for value in args.gate)
        result = build_release_candidate_manifest(
            project_path=args.project,
            artifact_root=args.artifact_root,
            repository_root=args.repository_root,
            audited_implementation_commit=args.audited_implementation_commit,
            gates=gates,
        )
    except (OSError, ValueError, tomllib.TOMLDecodeError, json.JSONDecodeError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, sort_keys=True))
        return 1

    if result.ok:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(result.manifest, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    print(
        json.dumps(
            {
                "ok": result.ok,
                "output": str(args.output) if result.ok else None,
                "issues": list(result.issues),
                "artifacts": len(result.manifest["artifacts"]),
                "gates": len(result.manifest["gates"]),
            },
            sort_keys=True,
        )
    )
    return 0 if result.ok else 1


def _parse_args(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", type=Path, default=Path("pyproject.toml"))
    parser.add_argument("--artifact-root", type=Path, default=Path("build/release-candidate"))
    parser.add_argument("--repository-root", type=Path, default=Path("."))
    parser.add_argument(
        "--audited-implementation-commit",
        help="Commit SHA the generated artifacts were built and verified from.",
    )
    parser.add_argument(
        "--gate",
        action="append",
        default=[],
        metavar="NAME|STATUS|EVIDENCE",
        help="Append a gate row. Repeat for each audited release gate.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("build/release-candidate/manifest.json"),
    )
    return parser.parse_args(argv)


def _artifact_rows(
    *,
    artifact_root: Path,
    repository_root: Path,
) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    issues: list[dict[str, str]] = []
    artifact_paths: set[Path] = set()
    for pattern in REQUIRED_ARTIFACT_PATTERNS:
        matches = tuple(path for path in artifact_root.glob(pattern) if path.is_file())
        if not matches:
            issues.append(
                {
                    "code": "required_artifact_missing",
                    "path": str(artifact_root / pattern),
                    "message": f"required release artifact pattern did not match: {pattern}",
                }
            )
        artifact_paths.update(matches)
    for pattern in OPTIONAL_ARTIFACT_PATTERNS:
        artifact_paths.update(path for path in artifact_root.glob(pattern) if path.is_file())
    rows = [
        {
            "path": _display_path(path, repository_root=repository_root),
            "sha256": _sha256_file(path),
            "size_bytes": path.stat().st_size,
        }
        for path in sorted(artifact_paths)
    ]
    return rows, issues


def _parse_gate(value: str) -> dict[str, str]:
    parts = value.split("|", 2)
    if len(parts) != 3 or not all(part.strip() for part in parts):
        raise ValueError("gate must use NAME|STATUS|EVIDENCE")
    return {
        "name": parts[0].strip(),
        "status": parts[1].strip(),
        "evidence": parts[2].strip(),
    }


def _gate_row(gate: Mapping[str, str]) -> dict[str, str]:
    return {
        "name": str(gate["name"]),
        "status": str(gate["status"]),
        "evidence": str(gate["evidence"]),
    }


def _license_report_summary(path: Path) -> dict[str, Any] | None:
    report = _load_json_if_present(path)
    if not isinstance(report, dict):
        return None
    issues = report.get("issues")
    return {
        "allowed_licenses": report.get("allowed_licenses", []),
        "issue_count": len(issues) if isinstance(issues, list) else 0,
        "packages_checked": report.get("packages_checked", 0),
    }


def _sbom_package_count(path: Path) -> int | None:
    sbom = _load_json_if_present(path)
    if not isinstance(sbom, dict):
        return None
    packages = sbom.get("packages")
    return len(packages) if isinstance(packages, list) else None


def _public_state_summary(artifact_root: Path, *, release: str) -> dict[str, Any]:
    summary: dict[str, Any] = {}
    pypi = _package_index_state(artifact_root / "pypi.json")
    if pypi:
        summary["pypi"] = pypi
    testpypi = _package_index_state(artifact_root / "testpypi.json")
    if testpypi:
        summary["testpypi"] = testpypi
    github = _github_state(artifact_root, release=release)
    if github:
        summary["github"] = github
    return summary


def _package_index_state(path: Path) -> dict[str, Any]:
    data = _load_json_if_present(path)
    if not isinstance(data, dict):
        return {}
    info = data.get("info")
    if not isinstance(info, dict):
        return {}
    return {
        "project_urls": info.get("project_urls"),
        "requires_python": info.get("requires_python"),
        "version": info.get("version"),
    }


def _github_state(artifact_root: Path, *, release: str) -> dict[str, Any]:
    tags = _load_json_if_present(artifact_root / "github-tags.json")
    release_lookup = _load_json_if_present(artifact_root / f"github-release-v{release}.json")
    releases = _load_json_if_present(artifact_root / "github-releases.json")
    state: dict[str, Any] = {}
    if isinstance(tags, list):
        state["tag_refs"] = [row["ref"] for row in tags if isinstance(row, dict) and "ref" in row]
    if isinstance(release_lookup, dict):
        if "message" in release_lookup:
            state["release_lookup_message"] = release_lookup["message"]
        elif "tag_name" in release_lookup:
            state["release_lookup_message"] = release_lookup["tag_name"]
    if isinstance(releases, list):
        state["published_release_tags"] = [
            row["tag_name"] for row in releases if isinstance(row, dict) and "tag_name" in row
        ]
    return state


def _load_json_if_present(path: Path) -> Any | None:
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _git_head(repository_root: Path) -> str | None:
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=repository_root,
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return None
    return result.stdout.strip() or None


def _display_path(path: Path, *, repository_root: Path) -> str:
    try:
        return path.resolve().relative_to(repository_root.resolve()).as_posix()
    except ValueError:
        return str(path)


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


if __name__ == "__main__":
    raise SystemExit(main())
