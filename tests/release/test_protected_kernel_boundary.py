from __future__ import annotations

import ast
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]

PROTECTED_KERNEL_PATHS = (
    "src/actionlineage/domain",
    "src/actionlineage/errors.py",
    "src/actionlineage/compatibility.py",
    "src/actionlineage/evidence",
    "src/actionlineage/journal",
    "src/actionlineage/observers/attestation.py",
    "src/actionlineage/observers/verification.py",
    "src/actionlineage/projection",
    "src/actionlineage/contracts",
    "src/actionlineage/exporters",
    "src/actionlineage/cli.py",
)

FORBIDDEN_OPTIONAL_IMPORT_ROOTS = frozenset(
    {
        "boto3",
        "botocore",
        "fastapi",
        "httpx",
        "httpx2",
        "jwt",
        "langchain",
        "llama_index",
        "mcp",
        "openai",
        "opentelemetry",
        "pydantic_settings",
        "sqlalchemy",
        "uvicorn",
        "yaml",
    }
)


def test_protected_kernel_paths_do_not_import_optional_runtime_dependencies() -> None:
    violations: list[str] = []

    for path in _python_files(PROTECTED_KERNEL_PATHS):
        for imported_root in _import_roots(path):
            if imported_root in FORBIDDEN_OPTIONAL_IMPORT_ROOTS:
                violations.append(f"{path.relative_to(PROJECT_ROOT)} imports {imported_root}")

    assert violations == []


def test_protected_kernel_boundary_roots_stay_documented() -> None:
    adr = (PROJECT_ROOT / "docs/ADR/0016-protected-evidence-kernel-boundary.md").read_text(
        encoding="utf-8"
    )

    for path in PROTECTED_KERNEL_PATHS:
        assert path in adr


def _python_files(paths: tuple[str, ...]) -> tuple[Path, ...]:
    files: list[Path] = []
    for path_name in paths:
        path = PROJECT_ROOT / path_name
        if path.is_file():
            files.append(path)
            continue
        files.extend(sorted(path.rglob("*.py")))
    return tuple(files)


def _import_roots(path: Path) -> tuple[str, ...]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    roots: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            roots.update(_root_name(alias.name) for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            roots.add(_root_name(node.module))
    return tuple(sorted(roots))


def _root_name(name: str) -> str:
    return name.split(".", maxsplit=1)[0]
