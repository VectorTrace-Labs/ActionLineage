#!/usr/bin/env python3
"""Check repository-local Markdown links without network access."""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections.abc import Iterator, Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from urllib.parse import unquote

EXCLUDED_DIR_NAMES = {
    ".git",
    ".hypothesis",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".tox",
    ".venv",
    "__pycache__",
    "build",
    "dist",
    "node_modules",
}
REFERENCE_LINK_PATTERN = re.compile(r"^\s{0,3}\[[^\]\n]+]:\s*(?P<target>\S+)")
INLINE_LINK_PATTERN = re.compile(r"(?P<image>!)?\[[^\]\n]*]\((?P<target>[^)\n]+)\)")
SCHEME_PATTERN = re.compile(r"^[A-Za-z][A-Za-z0-9+.-]*:")


@dataclass(frozen=True, slots=True)
class LinkIssue:
    """One Markdown link issue."""

    path: str
    line: int
    target: str
    code: str
    message: str


@dataclass(frozen=True, slots=True)
class LinkCheckResult:
    """Machine-readable Markdown link check result."""

    ok: bool
    checked_links: int
    files_scanned: int
    issues: tuple[LinkIssue, ...]

    def as_dict(self) -> dict[str, object]:
        return {
            "checked_links": self.checked_links,
            "files_scanned": self.files_scanned,
            "issues": [asdict(issue) for issue in self.issues],
            "ok": self.ok,
        }


def scan_paths(paths: Sequence[Path], *, repository_root: Path) -> LinkCheckResult:
    """Scan Markdown files below paths for repository-local link drift."""

    root = repository_root.resolve(strict=False)
    issues: list[LinkIssue] = []
    checked_links = 0
    files_scanned = 0

    for markdown_path in _iter_markdown_files(paths):
        files_scanned += 1
        for line_number, target in _iter_markdown_targets(markdown_path):
            normalized_target = _link_destination(target)
            if normalized_target is None or _is_external_or_anchor(normalized_target):
                continue

            checked_links += 1
            issues.extend(
                _check_local_target(
                    markdown_path=markdown_path,
                    line_number=line_number,
                    target=normalized_target,
                    repository_root=root,
                )
            )

    return LinkCheckResult(
        ok=not issues,
        checked_links=checked_links,
        files_scanned=files_scanned,
        issues=tuple(issues),
    )


def _iter_markdown_files(paths: Sequence[Path]) -> Iterator[Path]:
    for path in paths:
        if _is_excluded(path):
            continue
        if path.is_file() and path.suffix.lower() == ".md":
            yield path
            continue
        if path.is_dir():
            for candidate in sorted(path.rglob("*.md")):
                if not _is_excluded(candidate):
                    yield candidate


def _iter_markdown_targets(path: Path) -> Iterator[tuple[int, str]]:
    in_fence = False
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        stripped = line.lstrip()
        if stripped.startswith(("```", "~~~")):
            in_fence = not in_fence
            continue
        if in_fence:
            continue

        reference_match = REFERENCE_LINK_PATTERN.match(line)
        if reference_match:
            yield line_number, reference_match.group("target")

        for inline_match in INLINE_LINK_PATTERN.finditer(line):
            yield line_number, inline_match.group("target")


def _link_destination(raw_target: str) -> str | None:
    target = raw_target.strip()
    if not target:
        return None
    if target.startswith("<"):
        end_index = target.find(">")
        if end_index == -1:
            return target.strip("<>")
        return target[1:end_index].strip()
    return target.split(maxsplit=1)[0].strip()


def _is_external_or_anchor(target: str) -> bool:
    lowered = target.lower()
    if lowered.startswith(("#", "http://", "https://", "mailto:", "tel:")):
        return True
    return bool(SCHEME_PATTERN.match(target)) and not lowered.startswith("file:")


def _check_local_target(
    *,
    markdown_path: Path,
    line_number: int,
    target: str,
    repository_root: Path,
) -> tuple[LinkIssue, ...]:
    if target.lower().startswith("file:"):
        return (
            _issue(
                markdown_path,
                line_number,
                target,
                "file_uri",
                "file URI links are not portable repository-local Markdown links",
            ),
        )

    local_target = unquote(target.split("#", 1)[0])
    if not local_target:
        return ()

    candidate = (markdown_path.parent / local_target).resolve(strict=False)
    try:
        candidate.relative_to(repository_root)
    except ValueError:
        return (
            _issue(
                markdown_path,
                line_number,
                target,
                "target_escapes_repository",
                "link target escapes the repository root",
            ),
        )

    if not candidate.exists():
        return (
            _issue(
                markdown_path,
                line_number,
                target,
                "missing_target",
                "link target does not exist",
            ),
        )

    return ()


def _issue(path: Path, line_number: int, target: str, code: str, message: str) -> LinkIssue:
    return LinkIssue(
        path=str(path),
        line=line_number,
        target=target,
        code=code,
        message=message,
    )


def _is_excluded(path: Path) -> bool:
    return any(part in EXCLUDED_DIR_NAMES for part in path.parts)


def _parse_args(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("paths", nargs="*", type=Path, default=[Path(".")])
    parser.add_argument(
        "--root",
        type=Path,
        default=Path("."),
        help="Repository root used to reject escaping paths.",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(tuple(sys.argv[1:] if argv is None else argv))
    result = scan_paths(args.paths, repository_root=args.root)
    print(json.dumps(result.as_dict(), indent=2, sort_keys=True))
    return 0 if result.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
