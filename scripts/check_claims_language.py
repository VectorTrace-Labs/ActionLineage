#!/usr/bin/env python3
"""Check public wording for unsupported security overclaims."""

from __future__ import annotations

import argparse
import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Final

SKIPPED_DIRS: Final = {
    ".git",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".tox",
    ".venv",
    "__pycache__",
    "build",
    "dist",
}
SKIPPED_SUFFIXES: Final = {
    ".db",
    ".gif",
    ".gz",
    ".ico",
    ".jpg",
    ".jpeg",
    ".png",
    ".pyc",
    ".sqlite",
    ".tar",
    ".zip",
}
LOCAL_ONLY_NAMES: Final = {
    "AGENTS.md",
    "CLAUDE.md",
    "GEMINI.md",
    "Uplift.md",
}
SCANNED_SUFFIXES: Final = {
    ".cfg",
    ".json",
    ".md",
    ".py",
    ".toml",
    ".txt",
    ".yaml",
    ".yml",
}
CLAIM_PATTERNS: Final = (
    re.compile(r"\btamper[- ]proof\b", re.IGNORECASE),
    re.compile(r"\bforensically complete\b", re.IGNORECASE),
    re.compile(r"\buniversally secure\b", re.IGNORECASE),
    re.compile(r"\bproof of absence\b", re.IGNORECASE),
)
NEGATING_CONTEXT: Final = (
    "avoid ",
    "do not ",
    "does not ",
    "must not ",
    "not ",
    "not described as ",
    "not treated as ",
    "not “",
    'not "',
    "without ",
)
LINE_WIDE_NEGATING_CONTEXT: Final = (
    "avoid ",
    "do not ",
    "must never ",
    "must not ",
    "never treat ",
    "not in ",
    "not described as ",
)


@dataclass(frozen=True, slots=True)
class ClaimFinding:
    """One unsupported claim-language finding."""

    path: str
    line: int
    phrase: str
    text: str


def scan_paths(paths: list[Path], *, include_local_only: bool = False) -> list[ClaimFinding]:
    """Scan paths for unsupported claim language."""

    findings: list[ClaimFinding] = []
    for file_path in _iter_files(paths, include_local_only=include_local_only):
        for line_number, line in enumerate(file_path.read_text(encoding="utf-8").splitlines(), 1):
            for pattern in CLAIM_PATTERNS:
                for match in pattern.finditer(line):
                    if _is_negated(line, match.start()):
                        continue
                    findings.append(
                        ClaimFinding(
                            path=str(file_path),
                            line=line_number,
                            phrase=match.group(0),
                            text=line.strip(),
                        )
                    )
    return findings


def main() -> int:
    """Run the claim-language scanner."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("paths", nargs="+", type=Path)
    parser.add_argument(
        "--include-local-only",
        action="store_true",
        help="Also scan ignored local assistant/planning files such as AGENTS.md and Uplift.md.",
    )
    args = parser.parse_args()

    findings = scan_paths(args.paths, include_local_only=args.include_local_only)
    print(json.dumps({"ok": not findings, "findings": [asdict(f) for f in findings]}, indent=2))
    return 1 if findings else 0


def _iter_files(paths: list[Path], *, include_local_only: bool) -> list[Path]:
    files: list[Path] = []
    for path in paths:
        if path.is_file() and _should_scan(path, include_local_only=include_local_only):
            files.append(path)
        elif path.is_dir():
            for candidate in path.rglob("*"):
                if candidate.is_file() and _should_scan(
                    candidate,
                    include_local_only=include_local_only,
                ):
                    files.append(candidate)
    return sorted(files)


def _should_scan(path: Path, *, include_local_only: bool) -> bool:
    if any(part in SKIPPED_DIRS for part in path.parts):
        return False
    if not include_local_only and path.name in LOCAL_ONLY_NAMES:
        return False
    if path.suffix.lower() in SKIPPED_SUFFIXES:
        return False
    return path.suffix.lower() in SCANNED_SUFFIXES or path.name in {
        "Dockerfile",
        "LICENSE",
        "SECURITY.md",
    }


def _is_negated(line: str, match_start: int) -> bool:
    normalized_line = line.lower()
    if any(context in normalized_line for context in LINE_WIDE_NEGATING_CONTEXT):
        return True
    prefix = line[max(0, match_start - 48) : match_start].lower()
    return any(context in prefix for context in NEGATING_CONTEXT)


if __name__ == "__main__":
    raise SystemExit(main())
