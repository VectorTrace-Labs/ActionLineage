#!/usr/bin/env python3
"""Generate an unsigned local release provenance manifest."""

from __future__ import annotations

import argparse
import hashlib
import json
import tomllib
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

PROVENANCE_FORMAT = "actionlineage.dev/release-provenance-v0"
RELEASE_ARTIFACT_SUFFIXES = (".whl", ".tar.gz", ".zip")


def build_release_provenance(project_path: Path, dist_dir: Path) -> dict[str, Any]:
    """Build a JSON-compatible unsigned provenance manifest for release artifacts."""

    project_data = tomllib.loads(project_path.read_text(encoding="utf-8"))
    project = project_data["project"]
    subjects = [_artifact_row(path, root=dist_dir) for path in sorted(_dist_files(dist_dir))]
    return {
        "provenance_format": PROVENANCE_FORMAT,
        "generated_at": datetime.now(tz=UTC).isoformat().replace("+00:00", "Z"),
        "project": {
            "name": project["name"],
            "version": project["version"],
        },
        "builder": {
            "name": "actionlineage-local-release",
            "signature": None,
            "limitations": [
                "unsigned local manifest",
                "does not replace signed release artifacts or hosted attestations",
            ],
        },
        "materials": [
            {
                "path": str(project_path),
                "sha256": _sha256_file(project_path),
                "size_bytes": project_path.stat().st_size,
            }
        ],
        "subjects": subjects,
    }


def main() -> int:
    """Run the release provenance generator."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", type=Path, default=Path("pyproject.toml"))
    parser.add_argument("--dist-dir", type=Path, default=Path("dist"))
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    provenance = build_release_provenance(args.project, args.dist_dir)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(provenance, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "ok": True,
                "output": str(args.output),
                "subjects": len(provenance["subjects"]),
            }
        )
    )
    return 0


def _dist_files(dist_dir: Path) -> tuple[Path, ...]:
    if not dist_dir.exists():
        return ()
    return tuple(
        path
        for path in dist_dir.rglob("*")
        if path.is_file() and path.name.endswith(RELEASE_ARTIFACT_SUFFIXES)
    )


def _artifact_row(path: Path, *, root: Path) -> dict[str, object]:
    return {
        "path": str(path.relative_to(root)),
        "sha256": _sha256_file(path),
        "size_bytes": path.stat().st_size,
    }


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return f"sha256:{digest.hexdigest()}"


if __name__ == "__main__":
    raise SystemExit(main())
