#!/usr/bin/env python3
"""Write a concise GitHub Actions quality summary from local CI artifacts."""

from __future__ import annotations

import argparse
import sys
import xml.etree.ElementTree as ET
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

DEFAULT_COVERAGE_FLOOR = 85.0


@dataclass(frozen=True, slots=True)
class CoverageSummary:
    """Coverage percentages parsed from coverage.py XML."""

    line_percent: float
    branch_percent: float
    combined_percent: float
    lines_covered: int
    lines_valid: int
    branches_covered: int
    branches_valid: int


@dataclass(frozen=True, slots=True)
class SummaryResult:
    """Rendered CI summary and the coverage-floor result."""

    ok: bool
    markdown: str


def build_summary(
    *,
    python_version: str,
    coverage_xml: Path,
    coverage_floor: float = DEFAULT_COVERAGE_FLOOR,
    sbom_path: Path,
    provenance_path: Path,
    dist_dir: Path,
    wheel_smoke_dir: Path,
    sdist_smoke_dir: Path,
    demo_map_svg: Path,
) -> SummaryResult:
    """Build the Markdown summary and return whether enforced local evidence passed."""

    coverage_error: str | None = None
    try:
        coverage = parse_coverage_xml(coverage_xml)
    except (FileNotFoundError, ValueError, ET.ParseError) as exc:
        coverage = None
        coverage_error = str(exc)
    artifact_checks = (
        ("Demo evidence map", demo_map_svg.exists(), str(demo_map_svg)),
        ("SBOM", sbom_path.exists(), str(sbom_path)),
        ("Release provenance", provenance_path.exists(), str(provenance_path)),
        ("Wheel artifact", bool(list(dist_dir.glob("*.whl"))), str(dist_dir)),
        ("Source distribution", bool(list(dist_dir.glob("*.tar.gz"))), str(dist_dir)),
        ("Wheel quickstart smoke", _quickstart_smoke_exists(wheel_smoke_dir), str(wheel_smoke_dir)),
        ("Sdist quickstart smoke", _quickstart_smoke_exists(sdist_smoke_dir), str(sdist_smoke_dir)),
    )
    coverage_ok = coverage is not None and coverage.combined_percent >= coverage_floor
    ok = coverage_ok and all(check_ok for _, check_ok, _ in artifact_checks)

    lines = [
        "## ActionLineage Quality Evidence",
        "",
        f"- Python: `{python_version}`",
    ]
    if coverage is None:
        lines.append(f"- Branch-enabled total coverage: `MISSING` (floor `{coverage_floor:.2f}%`)")
        lines.append(f"- Coverage XML error: `{coverage_error}`")
    else:
        lines.extend(
            (
                f"- Branch-enabled total coverage: `{coverage.combined_percent:.2f}%` "
                f"(floor `{coverage_floor:.2f}%`)",
                f"- Line coverage: `{coverage.line_percent:.2f}%` "
                f"({coverage.lines_covered}/{coverage.lines_valid})",
                f"- Branch coverage: `{coverage.branch_percent:.2f}%` "
                f"({coverage.branches_covered}/{coverage.branches_valid})",
            )
        )
    lines.extend(("", "| Evidence | Status | Path |", "| --- | --- | --- |"))
    for label, check_ok, path in artifact_checks:
        lines.append(f"| {label} | {_status(check_ok)} | `{path}` |")
    lines.extend(
        (
            "",
            "Security and release proof steps in this job include Ruff, format check, strict mypy, "
            "pytest with branch coverage, claim-language guard, repository-local Markdown link "
            "check, project secret scan, dependency audit, SBOM generation, built wheel/sdist "
            "smoke tests, release consistency, and local provenance generation.",
            "",
            "Agent Validation Lab evidence is produced by the dedicated "
            "`agent-validation` workflow.",
            "",
        )
    )
    return SummaryResult(ok=ok, markdown="\n".join(lines))


def parse_coverage_xml(path: Path) -> CoverageSummary:
    if not path.exists():
        raise FileNotFoundError(f"coverage XML not found: {path}")
    root = ET.parse(path).getroot()
    lines_valid = _int_attr(root, "lines-valid")
    lines_covered = _int_attr(root, "lines-covered")
    branches_valid = _int_attr(root, "branches-valid")
    branches_covered = _int_attr(root, "branches-covered")
    covered = lines_covered + branches_covered
    total = lines_valid + branches_valid
    return CoverageSummary(
        line_percent=_percent(lines_covered, lines_valid),
        branch_percent=_percent(branches_covered, branches_valid),
        combined_percent=_percent(covered, total),
        lines_covered=lines_covered,
        lines_valid=lines_valid,
        branches_covered=branches_covered,
        branches_valid=branches_valid,
    )


def _quickstart_smoke_exists(path: Path) -> bool:
    return (
        (path / "demo" / "evidence.jsonl").exists()
        and (path / "case" / "case.json").exists()
        and (path / "console.html").exists()
    )


def _int_attr(root: ET.Element, name: str) -> int:
    value = root.attrib.get(name)
    if value is None:
        raise ValueError(f"coverage XML missing {name!r}")
    return int(value)


def _percent(covered: int, total: int) -> float:
    if total == 0:
        return 100.0
    return covered / total * 100.0


def _status(ok: bool) -> str:
    return "PASS" if ok else "MISSING"


def _parse_args(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--python-version", required=True)
    parser.add_argument("--coverage-xml", type=Path, required=True)
    parser.add_argument("--coverage-floor", type=float, default=DEFAULT_COVERAGE_FLOOR)
    parser.add_argument("--sbom", type=Path, required=True)
    parser.add_argument("--provenance", type=Path, required=True)
    parser.add_argument("--dist-dir", type=Path, required=True)
    parser.add_argument("--wheel-smoke-dir", type=Path, required=True)
    parser.add_argument("--sdist-smoke-dir", type=Path, required=True)
    parser.add_argument("--demo-map-svg", type=Path, required=True)
    parser.add_argument("--output", type=Path, help="Optional Markdown output path.")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(tuple(sys.argv[1:] if argv is None else argv))
    result = build_summary(
        python_version=args.python_version,
        coverage_xml=args.coverage_xml,
        coverage_floor=args.coverage_floor,
        sbom_path=args.sbom,
        provenance_path=args.provenance,
        dist_dir=args.dist_dir,
        wheel_smoke_dir=args.wheel_smoke_dir,
        sdist_smoke_dir=args.sdist_smoke_dir,
        demo_map_svg=args.demo_map_svg,
    )
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(result.markdown, encoding="utf-8")
    else:
        print(result.markdown)
    return 0 if result.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
