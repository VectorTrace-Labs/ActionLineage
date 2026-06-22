"""Command line entry point for development-only evals."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from actionlineage_evals.artifact_audit import audit_artifacts
from actionlineage_evals.boundary import check_eval_import_boundaries
from actionlineage_evals.environment import DockerComposeEnvironmentController
from actionlineage_evals.linting import lint_scenarios
from actionlineage_evals.models import RunMode
from actionlineage_evals.replay import promote_regression_bundle
from actionlineage_evals.runner import (
    DEFAULT_ARTIFACT_ROOT,
    replay_artifacts,
    replay_bundle,
    run_regression_corpus,
    run_suite,
)
from actionlineage_evals.scenarios import (
    SCENARIO_DIR,
    load_scenarios,
    validate_capability_coverage,
)
from actionlineage_evals.summary import (
    summarize_scorecards,
    summarize_scorecards_markdown,
    summarize_scorecards_text,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m actionlineage_evals")
    subcommands = parser.add_subparsers(dest="command", required=True)

    validate = subcommands.add_parser("validate-scenarios")
    validate.add_argument("--scenario-path", type=Path, default=SCENARIO_DIR)

    lint = subcommands.add_parser("lint-scenarios")
    lint.add_argument("--scenario-path", type=Path, default=SCENARIO_DIR)
    lint.add_argument(
        "--coverage-path",
        type=Path,
        default=Path("evals/CAPABILITY_COVERAGE.yaml"),
    )

    boundary = subcommands.add_parser("check-boundaries")
    boundary.add_argument("--project-root", type=Path, default=Path("."))

    coverage = subcommands.add_parser("coverage")
    coverage.add_argument(
        "--coverage-path",
        type=Path,
        default=Path("evals/CAPABILITY_COVERAGE.yaml"),
    )
    coverage.add_argument("--strict", action="store_true")

    run = subcommands.add_parser("run")
    run.add_argument("--scenario-path", type=Path, default=SCENARIO_DIR)
    run.add_argument("--artifact-root", type=Path, default=DEFAULT_ARTIFACT_ROOT)
    run.add_argument(
        "--mode",
        choices=[mode.value for mode in RunMode],
        default=RunMode.SCRIPTED.value,
    )
    run.add_argument(
        "--model-adapter",
        choices=["scripted", "replay", "github_models", "openai_compatible", "ollama"],
        default="scripted",
    )
    run.add_argument("--model-id")
    run.add_argument("--seeds", type=int, default=1)
    run.add_argument("--max-scenarios", type=int)
    run.add_argument("--use-docker", action="store_true")
    run.add_argument("--promote-regressions", action="store_true")

    replay = subcommands.add_parser("replay")
    replay.add_argument("bundle_dir", type=Path)
    replay.add_argument("--artifact-root", type=Path, default=DEFAULT_ARTIFACT_ROOT / "replay")

    replay_artifact_root = subcommands.add_parser("replay-artifacts")
    replay_artifact_root.add_argument("artifact_root", type=Path)
    replay_artifact_root.add_argument(
        "--replay-artifact-root",
        dest="replay_artifact_root",
        type=Path,
        default=DEFAULT_ARTIFACT_ROOT / "artifact-replay",
    )

    replay_regressions = subcommands.add_parser("replay-regressions")
    replay_regressions.add_argument(
        "--regression-dir",
        type=Path,
        default=Path("evals/regressions"),
    )
    replay_regressions.add_argument(
        "--artifact-root",
        type=Path,
        default=DEFAULT_ARTIFACT_ROOT / "regression-replay",
    )
    replay_regressions.add_argument("--allow-empty", action="store_true")

    promote_regression = subcommands.add_parser("promote-regression")
    promote_regression.add_argument("bundle_dir", type=Path)
    promote_regression.add_argument(
        "--regression-dir",
        type=Path,
        default=Path("evals/regressions"),
    )
    promote_regression.add_argument("--reviewed", action="store_true")
    promote_regression.add_argument("--reviewed-by")
    promote_regression.add_argument("--reason")
    promote_regression.add_argument("--source-run")

    docker_smoke = subcommands.add_parser("docker-smoke")
    docker_smoke.add_argument(
        "--compose-file",
        type=Path,
        default=Path("evals/docker/compose.yaml"),
    )
    docker_smoke.add_argument(
        "--artifact-root",
        type=Path,
        default=DEFAULT_ARTIFACT_ROOT / "docker-smoke",
    )

    summarize = subcommands.add_parser("summarize")
    summarize.add_argument("artifact_root", type=Path)
    summarize.add_argument("--format", choices=["json", "text", "markdown"], default="json")

    audit = subcommands.add_parser("audit-artifacts")
    audit.add_argument("artifact_root", type=Path)
    audit.add_argument("--canary", action="append", default=[])

    args = parser.parse_args(argv)
    if args.command == "validate-scenarios":
        scenarios = load_scenarios(args.scenario_path)
        _print(
            {
                "ok": True,
                "scenario_count": len(scenarios),
                "scenario_ids": [scenario.scenario_id for scenario in scenarios],
            }
        )
        return 0
    if args.command == "lint-scenarios":
        lint_report = lint_scenarios(
            scenario_path=args.scenario_path,
            coverage_path=args.coverage_path,
        )
        _print(lint_report)
        return 0 if lint_report["ok"] else 1
    if args.command == "check-boundaries":
        boundary_report = check_eval_import_boundaries(args.project_root)
        _print(boundary_report)
        return 0 if boundary_report["ok"] else 1
    if args.command == "coverage":
        report = validate_capability_coverage(args.coverage_path, strict=args.strict)
        _print(report)
        return 0 if report["ok"] else 1
    if args.command == "run":
        suite_result = run_suite(
            scenario_path=args.scenario_path,
            artifact_root=args.artifact_root,
            mode=RunMode(args.mode),
            model_adapter_name=args.model_adapter,
            model_id=args.model_id,
            seeds=args.seeds,
            max_scenarios=args.max_scenarios,
            use_docker=args.use_docker,
            promote_regressions=args.promote_regressions,
        )
        _print(suite_result.as_dict())
        return 0 if suite_result.passed else 1
    if args.command == "replay":
        replay_result = replay_bundle(args.bundle_dir, artifact_root=args.artifact_root)
        _print(replay_result.as_dict())
        return 0 if replay_result.passed else 1
    if args.command == "replay-artifacts":
        replay_artifact_result = replay_artifacts(
            artifact_root=args.artifact_root,
            replay_artifact_root=args.replay_artifact_root,
        )
        _print(replay_artifact_result.as_dict())
        return 0 if replay_artifact_result.passed else 1
    if args.command == "replay-regressions":
        regression_result = run_regression_corpus(
            regression_dir=args.regression_dir,
            artifact_root=args.artifact_root,
            allow_empty=args.allow_empty,
        )
        _print(regression_result.as_dict())
        return 0 if regression_result.passed else 1
    if args.command == "promote-regression":
        destination = promote_regression_bundle(
            args.bundle_dir,
            args.regression_dir,
            reviewed=args.reviewed,
            reviewed_by=args.reviewed_by,
            reason=args.reason,
            source_run=args.source_run,
        )
        _print({"destination": str(destination), "reviewed": args.reviewed})
        return 0
    if args.command == "docker-smoke":
        controller = DockerComposeEnvironmentController(
            run_id="smoke",
            compose_file=args.compose_file,
            artifact_root=args.artifact_root,
        )
        start = controller.start()
        stop = controller.stop()
        _print({"ok": True, "start": start, "stop": stop})
        return 0
    if args.command == "summarize":
        if args.format == "text":
            sys.stdout.write(summarize_scorecards_text(args.artifact_root))
            return 0
        if args.format == "markdown":
            sys.stdout.write(summarize_scorecards_markdown(args.artifact_root))
            return 0
        summary = summarize_scorecards(args.artifact_root)
        _print(summary)
        return 0 if summary["ok"] else 1
    if args.command == "audit-artifacts":
        audit_result = audit_artifacts(
            args.artifact_root,
            extra_canaries=tuple(str(value) for value in args.canary),
        )
        _print(audit_result)
        return 0 if audit_result["ok"] else 1
    raise AssertionError(f"unhandled command: {args.command}")


def _print(value: object) -> None:
    sys.stdout.write(json.dumps(value, indent=2, sort_keys=True) + "\n")


if __name__ == "__main__":
    raise SystemExit(main())
