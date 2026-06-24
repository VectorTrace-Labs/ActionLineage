#!/usr/bin/env python3
"""Run the public quickstart path against an installed ActionLineage CLI."""

from __future__ import annotations

import argparse
import json
import shlex
import subprocess
import sys
import tempfile
from collections.abc import Sequence
from dataclasses import asdict, dataclass
from pathlib import Path

DEFAULT_TRACE_ID = "trace_demo_evidence_plane"
DEFAULT_EXPECTED_VERSION = "0.1.0a6"
DEFAULT_STEP_TIMEOUT_SECONDS = 120.0


@dataclass(frozen=True, slots=True)
class SmokeStep:
    """One public quickstart smoke-test step."""

    name: str
    command: tuple[str, ...]
    exit_code: int
    stdout: str
    stderr: str

    @property
    def ok(self) -> bool:
        return self.exit_code == 0

    def as_dict(self) -> dict[str, object]:
        result = asdict(self)
        result["command"] = list(self.command)
        result["ok"] = self.ok
        return result


@dataclass(frozen=True, slots=True)
class SmokeResult:
    """Machine-readable public quickstart smoke result."""

    ok: bool
    output_dir: Path
    demo_dir: Path
    contract_path: Path
    expected_version: str
    steps: tuple[SmokeStep, ...]

    def as_dict(self) -> dict[str, object]:
        return {
            "contract_path": str(self.contract_path),
            "demo_dir": str(self.demo_dir),
            "expected_version": self.expected_version,
            "ok": self.ok,
            "output_dir": str(self.output_dir),
            "steps": [step.as_dict() for step in self.steps],
        }


def run_smoke(
    *,
    cli_prefix: Sequence[str],
    output_dir: Path,
    contract_path: Path,
    expected_version: str = DEFAULT_EXPECTED_VERSION,
    trace_id: str = DEFAULT_TRACE_ID,
    step_timeout_seconds: float = DEFAULT_STEP_TIMEOUT_SECONDS,
) -> SmokeResult:
    """Run the public quickstart CLI path and return a structured result."""

    output_dir.mkdir(parents=True, exist_ok=True)
    demo_dir = output_dir / "demo"
    case_dir = output_dir / "case"
    console_path = output_dir / "console.html"
    steps: list[SmokeStep] = []

    commands = (
        ("version", ("version",)),
        ("demo", ("demo", "run", "--output-dir", str(demo_dir))),
        ("journal_verify", ("journal", "verify", str(demo_dir / "evidence.jsonl"))),
        (
            "contract_validate",
            (
                "contract",
                "validate",
                str(contract_path),
                str(demo_dir / "evidence.jsonl"),
            ),
        ),
        (
            "case_export",
            (
                "projection",
                "export-case",
                str(demo_dir / "projection.sqlite"),
                str(case_dir),
                "--journal-path",
                str(demo_dir / "evidence.jsonl"),
                "--trace-id",
                trace_id,
            ),
        ),
        (
            "console_export",
            (
                "projection",
                "export-console",
                str(demo_dir / "projection.sqlite"),
                str(console_path),
                "--journal-path",
                str(demo_dir / "evidence.jsonl"),
                "--trace-id",
                trace_id,
            ),
        ),
    )

    for name, suffix in commands:
        step = _run_step(
            name=name,
            command=(*cli_prefix, *suffix),
            timeout_seconds=step_timeout_seconds,
        )
        steps.append(step)
        if not step.ok:
            break
        if name == "version" and step.stdout.strip() != expected_version:
            steps.append(
                SmokeStep(
                    name="version_matches_expected",
                    command=(),
                    exit_code=1,
                    stdout=step.stdout,
                    stderr=(f"expected version {expected_version!r}, got {step.stdout.strip()!r}"),
                )
            )
            break
        artifact_step = _artifact_step(
            name=name,
            demo_dir=demo_dir,
            case_dir=case_dir,
            console_path=console_path,
        )
        if artifact_step is not None:
            steps.append(artifact_step)
            if not artifact_step.ok:
                break

    return SmokeResult(
        ok=all(step.ok for step in steps),
        output_dir=output_dir,
        demo_dir=demo_dir,
        contract_path=contract_path,
        expected_version=expected_version,
        steps=tuple(steps),
    )


def cli_prefix_from_args(args: argparse.Namespace) -> tuple[str, ...]:
    if args.package_spec is not None:
        prefix = ["uvx"]
        if args.uvx_prerelease is not None:
            prefix.extend(("--prerelease", args.uvx_prerelease))
        prefix.extend(("--from", args.package_spec, "actionlineage"))
        return tuple(prefix)
    return tuple(shlex.split(args.command))


def _run_step(*, name: str, command: tuple[str, ...], timeout_seconds: float) -> SmokeStep:
    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            check=False,
            text=True,
            timeout=timeout_seconds,
        )
    except subprocess.TimeoutExpired as exc:
        return SmokeStep(
            name=name,
            command=command,
            exit_code=124,
            stdout=_bounded_output(_output_text(exc.stdout)),
            stderr=_bounded_output(
                _output_text(exc.stderr) + f"\nstep timed out after {timeout_seconds:g} seconds"
            ),
        )
    return SmokeStep(
        name=name,
        command=command,
        exit_code=completed.returncode,
        stdout=_bounded_output(completed.stdout),
        stderr=_bounded_output(completed.stderr),
    )


def _artifact_step(
    *,
    name: str,
    demo_dir: Path,
    case_dir: Path,
    console_path: Path,
) -> SmokeStep | None:
    required_by_step = {
        "demo": (demo_dir / "evidence.jsonl", demo_dir / "projection.sqlite"),
        "case_export": (case_dir / "case.json", case_dir / "events.ndjson", case_dir / "report.md"),
        "console_export": (console_path,),
    }
    required_paths = required_by_step.get(name)
    if required_paths is None:
        return None
    missing = [str(path) for path in required_paths if not path.exists()]
    return SmokeStep(
        name=f"{name}_artifacts_exist",
        command=(),
        exit_code=1 if missing else 0,
        stdout=json.dumps({"missing": missing}, sort_keys=True),
        stderr="expected smoke artifacts were not created" if missing else "",
    )


def _bounded_output(value: str, *, limit: int = 4000) -> str:
    if len(value) <= limit:
        return value
    digest_note = f"\n[TRUNCATED original_length={len(value)}]\n"
    return value[: limit - len(digest_note)] + digest_note


def _output_text(value: bytes | str | None) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode(errors="replace")
    return value


def _parse_args(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--command",
        default="actionlineage",
        help="Installed CLI command prefix, for example: 'uv run actionlineage'.",
    )
    parser.add_argument(
        "--package-spec",
        help=(
            "Package spec or artifact path used with uvx --from, such as a "
            "wheel, sdist, or actionlineage==0.1.0a6."
        ),
    )
    parser.add_argument(
        "--uvx-prerelease",
        choices=("allow", "if-necessary", "explicit", "if-necessary-or-explicit", "disallow"),
        help="Optional uvx prerelease policy, useful for package index smoke tests.",
    )
    parser.add_argument("--output-dir", type=Path, help="Directory for generated smoke artifacts.")
    parser.add_argument(
        "--contract",
        type=Path,
        default=Path("contracts/examples/outbound-http.json"),
        help="Contract used to validate the generated demo journal.",
    )
    parser.add_argument("--expected-version", default=DEFAULT_EXPECTED_VERSION)
    parser.add_argument("--trace-id", default=DEFAULT_TRACE_ID)
    parser.add_argument(
        "--step-timeout-seconds",
        type=float,
        default=DEFAULT_STEP_TIMEOUT_SECONDS,
        help="Maximum runtime for each public quickstart CLI step.",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(tuple(sys.argv[1:] if argv is None else argv))
    output_dir = args.output_dir or Path(tempfile.mkdtemp(prefix="actionlineage-quickstart-"))
    result = run_smoke(
        cli_prefix=cli_prefix_from_args(args),
        output_dir=output_dir,
        contract_path=args.contract,
        expected_version=args.expected_version,
        trace_id=args.trace_id,
        step_timeout_seconds=args.step_timeout_seconds,
    )
    print(json.dumps(result.as_dict(), indent=2, sort_keys=True))
    return 0 if result.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
