#!/usr/bin/env python3
"""Generate a lightweight JSON SBOM from pyproject metadata."""

from __future__ import annotations

import argparse
import json
import re
import tomllib
from datetime import UTC, datetime
from importlib import metadata
from pathlib import Path
from typing import Any

SBOM_FORMAT = "actionlineage.dev/simple-sbom-v0"


def build_sbom(project_path: Path) -> dict[str, Any]:
    """Build a JSON-compatible SBOM from a pyproject file."""

    project_data = tomllib.loads(project_path.read_text(encoding="utf-8"))
    project = project_data["project"]
    package_rows = []
    for scope, requirement in _requirements(project).items():
        name = _requirement_name(requirement)
        if name is None:
            continue
        package_rows.append(_package_row(name, requirement, scope))

    return {
        "bom_format": SBOM_FORMAT,
        "generated_at": datetime.now(tz=UTC).isoformat().replace("+00:00", "Z"),
        "project": {
            "name": project["name"],
            "version": project["version"],
            "license": _project_license(project),
        },
        "packages": sorted(package_rows, key=lambda row: (row["scope"], row["name"])),
    }


def main() -> int:
    """Run the SBOM generator."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", type=Path, default=Path("pyproject.toml"))
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    sbom = build_sbom(args.project)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(sbom, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"ok": True, "output": str(args.output), "packages": len(sbom["packages"])}))
    return 0


def _requirements(project: dict[str, Any]) -> dict[str, str]:
    requirements: dict[str, str] = {}
    for requirement in project.get("dependencies", []):
        requirements[f"runtime:{requirement}"] = requirement
    optional_dependencies = project.get("optional-dependencies", {})
    for extra, extra_requirements in optional_dependencies.items():
        for requirement in extra_requirements:
            requirements[f"extra:{extra}:{requirement}"] = requirement
    return requirements


def _project_license(project: dict[str, Any]) -> str:
    license_value = project.get("license")
    if isinstance(license_value, str):
        return license_value
    if isinstance(license_value, dict):
        text = license_value.get("text")
        if isinstance(text, str):
            return text
    return "unknown"


def _requirement_name(requirement: str) -> str | None:
    match = re.match(r"([A-Za-z0-9_.-]+)", requirement)
    return match.group(1).replace("_", "-").lower() if match else None


def _package_row(name: str, requirement: str, scope: str) -> dict[str, str]:
    try:
        distribution = metadata.distribution(name)
    except metadata.PackageNotFoundError:
        return {
            "name": name,
            "requirement": requirement,
            "scope": scope,
            "status": "not_installed",
            "version": "unknown",
            "license": "unknown",
        }

    return {
        "name": name,
        "requirement": requirement,
        "scope": scope,
        "status": "installed",
        "version": distribution.version,
        "license": _license(distribution),
    }


def _license(distribution: metadata.Distribution) -> str:
    license_value = distribution.metadata.get("License")
    if license_value:
        return license_value
    classifiers = distribution.metadata.get_all("Classifier", [])
    license_classifiers = [
        classifier.removeprefix("License :: ").strip()
        for classifier in classifiers
        if classifier.startswith("License :: ")
    ]
    return "; ".join(license_classifiers) if license_classifiers else "unknown"


if __name__ == "__main__":
    raise SystemExit(main())
