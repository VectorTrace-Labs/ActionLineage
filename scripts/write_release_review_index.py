#!/usr/bin/env python3
"""Write a deterministic Markdown index for local release-candidate proof."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

MANIFEST_SCHEMA_VERSION = "actionlineage.dev/release-candidate-manifest-v0"


@dataclass(frozen=True, slots=True)
class ArtifactCheck:
    """Verification result for one manifest-listed artifact."""

    path: str
    size_bytes: int | None
    expected_sha256: str
    actual_sha256: str | None
    status: str


@dataclass(frozen=True, slots=True)
class ReviewIndexResult:
    """Rendered release-proof index and verifier result."""

    ok: bool
    markdown: str
    issues: tuple[dict[str, str], ...]


def build_review_index(
    manifest_path: Path,
    *,
    repository_root: Path | None = None,
) -> ReviewIndexResult:
    """Build a human-readable release-proof index from a candidate manifest."""

    root = (repository_root or Path.cwd()).resolve()
    manifest = _load_json_object(manifest_path)
    issues: list[dict[str, str]] = []
    schema_version = _string_value(manifest, "schema_version")
    if schema_version != MANIFEST_SCHEMA_VERSION:
        issues.append(
            {
                "code": "schema_version_mismatch",
                "path": str(manifest_path),
                "message": f"expected {MANIFEST_SCHEMA_VERSION}, got {schema_version or 'missing'}",
            }
        )

    artifact_checks = _check_artifacts(manifest, manifest_path=manifest_path, root=root)
    issues.extend(_artifact_issues(artifact_checks))
    markdown = _render_markdown(
        manifest_path=manifest_path,
        manifest=manifest,
        checks=artifact_checks,
    )
    return ReviewIndexResult(ok=not issues, markdown=markdown, issues=tuple(issues))


def main(argv: Sequence[str] | None = None) -> int:
    """Run the review-index writer."""

    args = _parse_args(tuple(sys.argv[1:] if argv is None else argv))
    result = build_review_index(args.manifest, repository_root=args.repository_root)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(result.markdown, encoding="utf-8")
    print(
        json.dumps(
            {
                "ok": result.ok,
                "output": str(args.output),
                "issues": list(result.issues),
            },
            sort_keys=True,
        )
    )
    return 0 if result.ok else 1


def _parse_args(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--manifest",
        type=Path,
        default=Path("build/release-candidate/manifest.json"),
        help="Release-candidate manifest generated during local release proof.",
    )
    parser.add_argument(
        "--repository-root",
        type=Path,
        default=Path("."),
        help="Repository root used to resolve manifest artifact paths.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("build/release-candidate/REVIEW_INDEX.md"),
        help="Markdown index output path.",
    )
    return parser.parse_args(argv)


def _load_json_object(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"manifest must be a JSON object: {path}")
    return data


def _check_artifacts(
    manifest: Mapping[str, Any],
    *,
    manifest_path: Path,
    root: Path,
) -> tuple[ArtifactCheck, ...]:
    rows = manifest.get("artifacts")
    if not isinstance(rows, list):
        return ()
    return tuple(
        _check_artifact(row, manifest_dir=manifest_path.parent.resolve(), root=root)
        for row in rows
        if isinstance(row, dict)
    )


def _check_artifact(
    row: Mapping[str, Any],
    *,
    manifest_dir: Path,
    root: Path,
) -> ArtifactCheck:
    raw_path = _string_value(row, "path")
    expected_sha256 = _string_value(row, "sha256")
    size_bytes = _int_value(row, "size_bytes")
    if raw_path is None or expected_sha256 is None:
        return ArtifactCheck(
            path=raw_path or "missing",
            size_bytes=size_bytes,
            expected_sha256=expected_sha256 or "missing",
            actual_sha256=None,
            status="MALFORMED",
        )
    artifact_path = _resolve_artifact_path(raw_path, manifest_dir=manifest_dir, root=root)
    if not artifact_path.exists():
        return ArtifactCheck(
            path=raw_path,
            size_bytes=size_bytes,
            expected_sha256=expected_sha256,
            actual_sha256=None,
            status="MISSING",
        )
    actual_sha256 = _sha256_file(artifact_path)
    status = "PASS" if actual_sha256 == expected_sha256 else "HASH_MISMATCH"
    return ArtifactCheck(
        path=raw_path,
        size_bytes=artifact_path.stat().st_size,
        expected_sha256=expected_sha256,
        actual_sha256=actual_sha256,
        status=status,
    )


def _resolve_artifact_path(raw_path: str, *, manifest_dir: Path, root: Path) -> Path:
    path = Path(raw_path)
    if path.is_absolute():
        return path
    root_candidate = root / path
    if root_candidate.exists():
        return root_candidate
    return manifest_dir / path


def _artifact_issues(checks: Sequence[ArtifactCheck]) -> list[dict[str, str]]:
    issues = []
    for check in checks:
        if check.status == "PASS":
            continue
        issues.append(
            {
                "code": check.status.lower(),
                "path": check.path,
                "message": f"artifact verification status {check.status}",
            }
        )
    return issues


def _render_markdown(
    *,
    manifest_path: Path,
    manifest: Mapping[str, Any],
    checks: Sequence[ArtifactCheck],
) -> str:
    release = _string_value(manifest, "release") or "unknown"
    commit = _string_value(manifest, "audited_implementation_commit") or "unknown"
    generated_at = _string_value(manifest, "generated_at") or "unknown"
    gate_rows = _gate_rows(manifest)
    gate_counts = Counter(row["status"] for row in gate_rows)
    passing_artifacts = sum(1 for check in checks if check.status == "PASS")
    lines = [
        "# ActionLineage Release Proof Review Index",
        "",
        "This index is generated from local release-candidate proof. It is a reviewer navigation "
        "aid, not publication evidence, not a GitHub Release object, and not a signed "
        "attestation.",
        "",
        "## Candidate",
        "",
        "| Field | Value |",
        "| --- | --- |",
        f"| Release | `{_md_cell(release)}` |",
        f"| Audited implementation commit | `{_md_cell(commit)}` |",
        f"| Manifest | `{_md_cell(str(manifest_path))}` |",
        f"| Manifest generated at | `{_md_cell(generated_at)}` |",
        f"| Artifacts verified locally | `{passing_artifacts}/{len(checks)}` |",
        f"| Gate status counts | `{_md_cell(_format_counts(gate_counts))}` |",
        "",
        "## Local Artifacts",
        "",
        "| Artifact | Status | Size bytes | SHA256 |",
        "| --- | --- | --- | --- |",
    ]
    for check in checks:
        size = "unknown" if check.size_bytes is None else str(check.size_bytes)
        lines.append(
            f"| `{_md_cell(check.path)}` | `{check.status}` | `{size}` | "
            f"`{_md_cell(check.expected_sha256)}` |"
        )
    lines.extend(
        [
            "",
            "## Gate Evidence",
            "",
            "| Gate | Status | Evidence |",
            "| --- | --- | --- |",
        ]
    )
    for row in gate_rows:
        lines.append(
            f"| `{_md_cell(row['name'])}` | `{_md_cell(row['status'])}` | "
            f"{_md_cell(row['evidence'])} |"
        )
    lines.extend(_supply_chain_section(manifest))
    lines.extend(_public_state_section(manifest))
    lines.extend(
        [
            "",
            "## Reviewer Checks",
            "",
            "Run these checks against the local artifact directory before attaching or reviewing "
            "release assets:",
            "",
            "```bash",
            *_reviewer_commands(manifest=manifest, manifest_path=manifest_path, checks=checks),
            "```",
            "",
            "Owner-gated actions remain separate: do not push, tag, publish, upload, or create a "
            "GitHub Release from this index alone.",
            "",
        ]
    )
    return "\n".join(lines)


def _reviewer_commands(
    *,
    manifest: Mapping[str, Any],
    manifest_path: Path,
    checks: Sequence[ArtifactCheck],
) -> tuple[str, ...]:
    artifact_root = _string_value(manifest, "artifact_root") or manifest_path.parent.as_posix()
    checksum_path = (
        _artifact_path_with_name(checks, "SHA256SUMS.txt") or f"{artifact_root}/SHA256SUMS.txt"
    )
    wheel_path = _artifact_path_with_suffix(checks, ".whl") or "dist/actionlineage-<version>.whl"
    sdist_path = (
        _artifact_path_with_suffix(checks, ".tar.gz") or "dist/actionlineage-<version>.tar.gz"
    )
    return (
        f"shasum -a 256 -c {checksum_path}",
        f"uvx --from {wheel_path} actionlineage version",
        f"uvx --from {sdist_path} actionlineage version",
    )


def _artifact_path_with_name(checks: Sequence[ArtifactCheck], name: str) -> str | None:
    for check in checks:
        if Path(check.path).name == name:
            return check.path
    return None


def _artifact_path_with_suffix(checks: Sequence[ArtifactCheck], suffix: str) -> str | None:
    for check in checks:
        if check.path.endswith(suffix):
            return check.path
    return None


def _gate_rows(manifest: Mapping[str, Any]) -> tuple[dict[str, str], ...]:
    rows = manifest.get("gates")
    if not isinstance(rows, list):
        return ()
    normalized = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        normalized.append(
            {
                "name": _string_value(row, "name") or "unknown",
                "status": _string_value(row, "status") or "UNKNOWN",
                "evidence": _string_value(row, "evidence") or "",
            }
        )
    return tuple(normalized)


def _supply_chain_section(manifest: Mapping[str, Any]) -> list[str]:
    license_report = manifest.get("license_report")
    if not isinstance(license_report, dict):
        license_report = {}
    allowed = license_report.get("allowed_licenses")
    allowed_licenses = ", ".join(str(item) for item in allowed) if isinstance(allowed, list) else ""
    return [
        "",
        "## Supply Chain Summary",
        "",
        "| Evidence | Value |",
        "| --- | --- |",
        f"| SBOM package count | `{_int_or_unknown(manifest.get('sbom_package_count'))}` |",
        "| Dependency licenses checked | "
        f"`{_int_or_unknown(license_report.get('packages_checked'))}` |",
        f"| Dependency license issues | `{_int_or_unknown(license_report.get('issue_count'))}` |",
        f"| Allowed license set | `{_md_cell(allowed_licenses or 'unknown')}` |",
    ]


def _public_state_section(manifest: Mapping[str, Any]) -> list[str]:
    public_state = manifest.get("public_state")
    if not isinstance(public_state, dict):
        public_state = {}
    pypi = _mapping(public_state.get("pypi"))
    testpypi = _mapping(public_state.get("testpypi"))
    github = _mapping(public_state.get("github"))
    release_tags = github.get("published_release_tags")
    release_tag_text = (
        ", ".join(str(tag) for tag in release_tags) if isinstance(release_tags, list) else ""
    )
    return [
        "",
        "## Public State And External Gates",
        "",
        "| Source | Current evidence | Gate status |",
        "| --- | --- | --- |",
        f"| PyPI | version `{_md_cell(str(pypi.get('version', 'unknown')))}`, "
        f"Requires-Python `{_md_cell(str(pypi.get('requires_python', 'unknown')))}`, "
        f"project URLs `{_urls_status(pypi)}` | "
        f"{_metadata_gate(pypi)} |",
        f"| TestPyPI | version `{_md_cell(str(testpypi.get('version', 'unknown')))}`, "
        f"Requires-Python `{_md_cell(str(testpypi.get('requires_python', 'unknown')))}`, "
        f"project URLs `{_urls_status(testpypi)}` | "
        f"{_metadata_gate(testpypi)} |",
        f"| GitHub Releases | listed tags `{_md_cell(release_tag_text or 'none')}`, "
        f"release lookup `{_md_cell(str(github.get('release_lookup_message', 'unknown')))}` | "
        "BLOCKED_ON_OWNER if the expected release object is absent |",
    ]


def _mapping(value: object) -> Mapping[str, Any]:
    return value if isinstance(value, dict) else {}


def _metadata_gate(state: Mapping[str, Any]) -> str:
    return "PASS" if state.get("project_urls") else "BLOCKED_ON_RELEASE"


def _urls_status(state: Mapping[str, Any]) -> str:
    return "present" if state.get("project_urls") else "absent"


def _format_counts(counts: Counter[str]) -> str:
    if not counts:
        return "none"
    return ", ".join(f"{status}={count}" for status, count in sorted(counts.items()))


def _string_value(row: Mapping[str, Any], key: str) -> str | None:
    value = row.get(key)
    return value if isinstance(value, str) else None


def _int_value(row: Mapping[str, Any], key: str) -> int | None:
    value = row.get(key)
    return value if isinstance(value, int) else None


def _int_or_unknown(value: object) -> str:
    return str(value) if isinstance(value, int) else "unknown"


def _md_cell(value: str) -> str:
    return value.replace("\\", "\\\\").replace("|", "\\|").replace("\n", " ")


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


if __name__ == "__main__":
    raise SystemExit(main())
