"""Development-only import-boundary checks for eval dependencies."""

from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path

from actionlineage_evals.models import JsonMap

FORBIDDEN_CORE_IMPORT_PREFIXES = (
    "actionlineage_evals",
    "inspect_ai",
    "openai",
)


@dataclass(frozen=True, slots=True)
class ImportBoundaryViolation:
    """One forbidden import from ActionLineage core into eval-only dependencies."""

    file: Path
    line: int
    module: str

    def as_dict(self, *, project_root: Path) -> JsonMap:
        return {
            "file": str(self.file.relative_to(project_root)),
            "line": self.line,
            "module": self.module,
        }


def check_eval_import_boundaries(project_root: Path = Path(".")) -> JsonMap:
    """Return a machine-readable report for core imports of eval-only modules."""

    root = Path(project_root)
    src_root = root / "src" / "actionlineage"
    violations: list[ImportBoundaryViolation] = []
    for path in sorted(src_root.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            for module in _imported_modules(node):
                if _is_forbidden(module):
                    violations.append(
                        ImportBoundaryViolation(
                            file=path,
                            line=int(getattr(node, "lineno", 0)),
                            module=module,
                        )
                    )
    return {
        "forbidden_prefixes": list(FORBIDDEN_CORE_IMPORT_PREFIXES),
        "ok": not violations,
        "schema_version": "actionlineage.dev/eval-import-boundary/v0",
        "violations": [violation.as_dict(project_root=root) for violation in violations],
    }


def _imported_modules(node: ast.AST) -> tuple[str, ...]:
    if isinstance(node, ast.Import):
        return tuple(str(alias.name) for alias in node.names)
    if isinstance(node, ast.ImportFrom) and node.module:
        return (str(node.module),)
    return ()


def _is_forbidden(module: str) -> bool:
    return any(
        module == prefix or module.startswith(f"{prefix}.")
        for prefix in FORBIDDEN_CORE_IMPORT_PREFIXES
    )
