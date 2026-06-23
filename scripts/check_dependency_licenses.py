#!/usr/bin/env python3
"""Check direct dependency license metadata for the public-alpha release gate."""

from __future__ import annotations

import argparse
import importlib.util
import json
import re
import sys
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from types import ModuleType
from typing import Any

REPORT_FORMAT = "actionlineage.dev/dependency-license-report-v0"
DEFAULT_ALLOWED_LICENSES = frozenset({"Apache-2.0", "BSD", "BSD-3-Clause", "MIT", "MPL-2.0"})
DENIED_LICENSE_MARKERS = frozenset(
    {
        "AGPL",
        "GPL",
        "LGPL",
        "GNU AFFERO GENERAL PUBLIC LICENSE",
        "GNU GENERAL PUBLIC LICENSE",
        "GNU LESSER GENERAL PUBLIC LICENSE",
    }
)
CLASSIFIER_LICENSE_MAP = {
    "OSI Approved :: Apache Software License": "Apache-2.0",
    "OSI Approved :: BSD License": "BSD",
    "OSI Approved :: MIT License": "MIT",
    "OSI Approved :: Mozilla Public License 2.0 (MPL 2.0)": "MPL-2.0",
}


@dataclass(frozen=True, slots=True)
class LicenseIssue:
    """A dependency license issue found during local metadata checks."""

    name: str
    scope: str
    version: str
    license: str
    normalized_license: str
    reason: str

    def to_json(self) -> dict[str, str]:
        return {
            "name": self.name,
            "scope": self.scope,
            "version": self.version,
            "license": self.license,
            "normalized_license": self.normalized_license,
            "reason": self.reason,
        }


def build_license_report(
    project_path: Path,
    *,
    allowed_licenses: Iterable[str] = DEFAULT_ALLOWED_LICENSES,
) -> dict[str, Any]:
    """Build a JSON-compatible dependency license report from project metadata."""

    sbom = _generate_sbom().build_sbom(project_path)
    return evaluate_packages(sbom["packages"], allowed_licenses=allowed_licenses)


def evaluate_packages(
    packages: Sequence[dict[str, str]],
    *,
    allowed_licenses: Iterable[str] = DEFAULT_ALLOWED_LICENSES,
) -> dict[str, Any]:
    """Evaluate direct dependency package rows emitted by the lightweight SBOM."""

    allowed = frozenset(allowed_licenses)
    checked_packages: list[dict[str, str]] = []
    issues: list[LicenseIssue] = []
    for package in sorted(packages, key=lambda row: (row["scope"], row["name"])):
        normalized_license = normalize_license(package["license"])
        checked = {
            "name": package["name"],
            "scope": package["scope"],
            "status": package["status"],
            "version": package["version"],
            "license": package["license"],
            "normalized_license": normalized_license,
        }
        checked_packages.append(checked)
        reason = _issue_reason(package, normalized_license, allowed)
        if reason is not None:
            issues.append(
                LicenseIssue(
                    name=package["name"],
                    scope=package["scope"],
                    version=package["version"],
                    license=package["license"],
                    normalized_license=normalized_license,
                    reason=reason,
                )
            )

    return {
        "schema_version": REPORT_FORMAT,
        "ok": not issues,
        "packages_checked": len(checked_packages),
        "allowed_licenses": sorted(allowed),
        "denied_license_markers": sorted(DENIED_LICENSE_MARKERS),
        "issues": [issue.to_json() for issue in issues],
        "packages": checked_packages,
    }


def normalize_license(value: str) -> str:
    """Normalize common package metadata license strings to compact expressions."""

    normalized = re.sub(r"\s+", " ", value).strip()
    if not normalized:
        return "unknown"
    if normalized in CLASSIFIER_LICENSE_MAP:
        return CLASSIFIER_LICENSE_MAP[normalized]
    if normalized.startswith("OSI Approved :: "):
        return normalized.removeprefix("OSI Approved :: ").removesuffix(" License")
    return normalized


def _issue_reason(
    package: dict[str, str],
    normalized_license: str,
    allowed_licenses: frozenset[str],
) -> str | None:
    if package["status"] != "installed":
        return "dependency_not_installed"
    if normalized_license == "unknown":
        return "unknown_license"
    upper_license = normalized_license.upper()
    for marker in DENIED_LICENSE_MARKERS:
        if _contains_denied_marker(upper_license, marker):
            return "denied_license"
    if _all_license_terms_allowed(normalized_license, allowed_licenses):
        return None
    return "license_not_in_allowlist"


def _contains_denied_marker(upper_license: str, marker: str) -> bool:
    if marker in {"GPL", "LGPL", "AGPL"}:
        return bool(re.search(rf"(^|[^A-Z]){re.escape(marker)}([^A-Z]|$)", upper_license))
    return marker in upper_license


def _all_license_terms_allowed(expression: str, allowed_licenses: frozenset[str]) -> bool:
    terms = [
        term.strip() for term in re.split(r"\s+(?:AND|OR|WITH)\s+|[()]", expression) if term.strip()
    ]
    return bool(terms) and all(term in allowed_licenses for term in terms)


def _parse_args(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", type=Path, default=Path("pyproject.toml"))
    parser.add_argument("--output", type=Path, help="Optional JSON report output path.")
    return parser.parse_args(argv)


@lru_cache(maxsize=1)
def _generate_sbom() -> ModuleType:
    script_path = Path(__file__).resolve().with_name("generate_sbom.py")
    spec = importlib.util.spec_from_file_location("generate_sbom", script_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"could not load SBOM generator from {script_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules["generate_sbom"] = module
    spec.loader.exec_module(module)
    return module


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(tuple(sys.argv[1:] if argv is None else argv))
    report = build_license_report(args.project)
    rendered = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    print(
        json.dumps(
            {
                "issues": len(report["issues"]),
                "ok": report["ok"],
                "output": str(args.output) if args.output is not None else None,
                "packages_checked": report["packages_checked"],
            },
            sort_keys=True,
        )
    )
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
