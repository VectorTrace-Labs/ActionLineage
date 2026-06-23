#!/usr/bin/env python3
"""Small repository secret scanner for release gates."""

from __future__ import annotations

import argparse
import json
import math
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
    "cdk.out",
    "dist",
    "node_modules",
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
SKIPPED_NAMES: Final = {
    ".coverage",
    "uv.lock",
}
LOCAL_ONLY_NAMES: Final = {
    "AGENTS.md",
    "CLAUDE.md",
    "GEMINI.md",
    "Uplift.md",
}
ALLOWLIST_SUBSTRINGS: Final = (
    "[REDACTED",
    "al_canary_token",
    "Bearer [REDACTED",
    "Bearer exporter-secret-value",
    "Bearer journal-parse-secret-value",
    "Bearer should-not-appear-in-error",
    "failure-secret-value",
    "journal-secret-value",
    "local-token",
    "path-secret-value",
    "source-neutral-secret-value",
)
SECRET_PATTERNS: Final = (
    ("private_key", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
    ("aws_access_key", re.compile(r"\bA(?:KIA|SIA)[A-Z0-9]{16}\b")),
    ("github_token", re.compile(r"\bgh[pousr]_[A-Za-z0-9_]{36,}\b")),
    ("slack_token", re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{20,}\b")),
    ("stripe_key", re.compile(r"\b(?:sk|rk)_(?:live|test)_[A-Za-z0-9]{20,}\b")),
    ("bearer_token", re.compile(r"\bBearer\s+[A-Za-z0-9._~+/=-]{20,}\b")),
    (
        "assigned_secret",
        re.compile(
            r"(?i)\b(api[_-]?key|password|private[_-]?key|secret|token)\b"
            r"\s*[:=]\s*['\"]?([A-Za-z0-9._~+/=-]{24,})"
        ),
    ),
)


@dataclass(frozen=True, slots=True)
class SecretFinding:
    """One potential secret finding."""

    path: str
    line: int
    kind: str
    fingerprint: str


def scan_paths(paths: list[Path], *, include_local_only: bool = False) -> list[SecretFinding]:
    """Scan paths for high-confidence secret patterns."""

    findings: list[SecretFinding] = []
    for file_path in _iter_files(paths, include_local_only=include_local_only):
        try:
            text = file_path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        for line_number, line in enumerate(text.splitlines(), 1):
            if _is_allowlisted(line):
                continue
            for kind, pattern in SECRET_PATTERNS:
                for match in pattern.finditer(line):
                    candidate = match.group(0)
                    if kind == "assigned_secret":
                        candidate = match.group(2)
                        if "." in candidate and not any(
                            character.isdigit() for character in candidate
                        ):
                            continue
                        if _entropy(candidate) < 3.5:
                            continue
                    findings.append(
                        SecretFinding(
                            path=str(file_path),
                            line=line_number,
                            kind=kind,
                            fingerprint=_fingerprint(candidate),
                        )
                    )
    return findings


def main() -> int:
    """Run the repository secret scanner."""

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
    if path.name in SKIPPED_NAMES:
        return False
    return path.suffix.lower() not in SKIPPED_SUFFIXES


def _is_allowlisted(line: str) -> bool:
    return any(value in line for value in ALLOWLIST_SUBSTRINGS)


def _fingerprint(value: str) -> str:
    if len(value) <= 8:
        return "*" * len(value)
    return f"{value[:4]}...{value[-4:]}"


def _entropy(value: str) -> float:
    if not value:
        return 0.0
    counts = {character: value.count(character) for character in set(value)}
    length = len(value)
    return -sum((count / length) * math.log2(count / length) for count in counts.values())


if __name__ == "__main__":
    raise SystemExit(main())
