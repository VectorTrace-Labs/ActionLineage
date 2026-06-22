"""Redaction audit for generated Agent Validation Lab artifacts."""

from __future__ import annotations

import re
from pathlib import Path

from actionlineage_evals.models import JsonMap

FORBIDDEN_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("synthetic_canary", re.compile(r"AVL_CANARY_[A-Za-z0-9_-]+")),
    ("authorization_header", re.compile(r"Authorization\s*:\s*Bearer\s+\S+", re.IGNORECASE)),
    ("bearer_token", re.compile(r"Bearer\s+[A-Za-z0-9._~+/=-]{16,}")),
    ("github_classic_token", re.compile(r"ghp_[A-Za-z0-9_]{20,}")),
    ("github_fine_grained_token", re.compile(r"github_pat_[A-Za-z0-9_]{20,}")),
    ("openai_key", re.compile(r"sk-[A-Za-z0-9_-]{20,}")),
)


def audit_artifacts(root: Path, *, extra_canaries: tuple[str, ...] = ()) -> JsonMap:
    """Scan generated artifacts without echoing matched secret material."""

    root = Path(root)
    leaks: list[JsonMap] = []
    files_scanned = 0
    patterns = list(FORBIDDEN_PATTERNS)
    patterns.extend(
        (f"extra_canary_{index}", re.compile(re.escape(canary)))
        for index, canary in enumerate(extra_canaries)
        if canary
    )
    if root.exists():
        for path in sorted(root.rglob("*")):
            if not path.is_file():
                continue
            try:
                text = path.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                continue
            files_scanned += 1
            for pattern_name, pattern in patterns:
                if pattern.search(text):
                    leaks.append(
                        {
                            "path": str(path),
                            "pattern": pattern_name,
                        }
                    )
    return {
        "files_scanned": files_scanned,
        "leak_count": len(leaks),
        "leaks": leaks,
        "ok": not leaks,
        "root": str(root),
        "schema_version": "actionlineage.dev/eval-artifact-audit/v0",
    }
