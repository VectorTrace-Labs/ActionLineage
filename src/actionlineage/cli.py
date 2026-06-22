"""ActionLineage evidence-plane CLI."""

from __future__ import annotations

import json
import platform
from pathlib import Path
from typing import Annotated, cast

import typer

from actionlineage import __version__
from actionlineage.console import (
    ConsoleContextError,
    load_console_context,
    write_console,
    write_desktop_bundle,
)
from actionlineage.contracts import (
    ContractResult,
    contract_result_annotations,
    explain_contract,
    load_contract,
    validate_contract,
    write_contract_template,
)
from actionlineage.demo import run_demo
from actionlineage.detection import (
    DetectionMatch,
    DetectionRuleLoadError,
    built_in_sequence_rules,
    evaluate_sequence_rule,
    explain_sequence_rule,
    load_sequence_rules,
)
from actionlineage.domain import EventEnvelope
from actionlineage.errors import ActionLineageValidationError
from actionlineage.journal import (
    ExternalAttestationType,
    JournalAnchorError,
    LocalJournal,
    append_journal_anchor_log,
    create_external_anchor_attestation,
    create_git_anchor_statement,
    create_journal_anchor,
    create_journal_archive_manifest,
    export_verified_prefix,
    load_external_anchor_attestation,
    load_git_anchor_statement,
    load_journal_anchor,
    load_journal_archive_manifest,
    verify_external_anchor_attestation,
    verify_git_anchor_statement,
    verify_journal,
    verify_journal_anchor,
    verify_journal_anchor_log,
    verify_journal_archive_manifest,
    write_external_anchor_attestation,
    write_git_anchor_statement,
    write_journal_anchor,
    write_journal_archive_manifest,
)
from actionlineage.journal.archive import ArchiveRetentionMode
from actionlineage.packs import load_pack_manifest, pack_artifact_index, validate_pack_manifest
from actionlineage.projection import (
    ProjectionError,
    ProjectionVerificationError,
    explain_event,
    export_case_bundle,
    export_incident,
    export_investigation_graph,
    query_filtered_timeline,
    query_timeline,
    rebuild_projection,
    summarize_incident,
)

app = typer.Typer(no_args_is_help=True, help="ActionLineage evidence-plane CLI")
journal_app = typer.Typer(no_args_is_help=True, help="Local journal commands")
projection_app = typer.Typer(no_args_is_help=True, help="SQLite projection commands")
demo_app = typer.Typer(no_args_is_help=True, help="Deterministic evidence-plane demo")
contract_app = typer.Typer(no_args_is_help=True, help="Lineage Contract commands")
detection_app = typer.Typer(no_args_is_help=True, help="Detection rule commands")
pack_app = typer.Typer(no_args_is_help=True, help="Extension pack manifest commands")
app.add_typer(journal_app, name="journal")
app.add_typer(projection_app, name="projection")
app.add_typer(demo_app, name="demo")
app.add_typer(contract_app, name="contract")
app.add_typer(detection_app, name="detection")
app.add_typer(pack_app, name="pack")


@app.command()
def version() -> None:
    """Print the package version."""
    typer.echo(__version__)


@app.command()
def doctor() -> None:
    """Print basic local development diagnostics."""
    typer.echo(f"actionlineage={__version__}")
    typer.echo(f"python={platform.python_version()}")
    typer.echo(f"platform={platform.platform()}")


@pack_app.command("validate")
def pack_validate_command(
    manifest_path: Annotated[
        Path,
        typer.Argument(exists=True, dir_okay=False, path_type=Path),
    ],
) -> None:
    """Validate a local extension pack manifest."""

    try:
        result = validate_pack_manifest(manifest_path)
    except ActionLineageValidationError as exc:
        typer.echo(json.dumps({"ok": False, "error": str(exc)}, sort_keys=True))
        raise typer.Exit(1) from None

    typer.echo(json.dumps(result.as_dict(), sort_keys=True))
    if not result.ok:
        raise typer.Exit(1)


@pack_app.command("list")
def pack_list_command(
    manifest_path: Annotated[
        Path,
        typer.Argument(exists=True, dir_okay=False, path_type=Path),
    ],
) -> None:
    """List artifacts declared by a local extension pack manifest."""

    try:
        manifest = load_pack_manifest(manifest_path)
    except ActionLineageValidationError as exc:
        typer.echo(json.dumps({"ok": False, "error": str(exc)}, sort_keys=True))
        raise typer.Exit(1) from None

    typer.echo(
        json.dumps(
            {
                "ok": True,
                "schema_version": manifest.schema_version,
                "pack": {
                    "name": manifest.name,
                    "version": manifest.version,
                    "publisher": manifest.publisher,
                },
                "artifacts": pack_artifact_index(manifest),
            },
            sort_keys=True,
        )
    )


@demo_app.command("run")
def demo_run_command(
    output_dir: Annotated[
        Path,
        typer.Option(
            "--output-dir",
            dir_okay=True,
            file_okay=False,
            path_type=Path,
            help="Directory for generated demo journal, projection, and incident export.",
        ),
    ] = Path("build/actionlineage-demo"),
) -> None:
    """Run the deterministic local evidence-plane demo."""

    result = run_demo(output_dir)
    typer.echo(json.dumps(result.as_dict(), sort_keys=True))


@contract_app.command("init")
def contract_init_command(
    output_path: Annotated[
        Path,
        typer.Argument(exists=False, dir_okay=False, path_type=Path),
    ],
    name: Annotated[
        str,
        typer.Option("--name", help="Contract metadata name."),
    ] = "actionlineage-contract",
) -> None:
    """Write a starter JSON Lineage Contract."""

    contract = write_contract_template(output_path, name=name)
    typer.echo(json.dumps({"ok": True, "path": str(output_path), "contract": contract.name}))


@contract_app.command("explain")
def contract_explain_command(
    contract_path: Annotated[
        Path,
        typer.Argument(exists=True, dir_okay=False, path_type=Path),
    ],
) -> None:
    """Explain a JSON Lineage Contract."""

    try:
        contract = load_contract(contract_path)
    except ActionLineageValidationError as exc:
        typer.echo(json.dumps({"ok": False, "error": str(exc)}, sort_keys=True))
        raise typer.Exit(1) from None
    typer.echo(json.dumps(explain_contract(contract), sort_keys=True))


@contract_app.command("validate")
def contract_validate_command(
    contract_path: Annotated[
        Path,
        typer.Argument(exists=True, dir_okay=False, path_type=Path),
    ],
    journal_path: Annotated[
        Path,
        typer.Argument(exists=True, dir_okay=False, path_type=Path),
    ],
    output_format: Annotated[
        str,
        typer.Option("--format", help="Output format: json or annotations."),
    ] = "json",
    built_in_detections: Annotated[
        bool,
        typer.Option(
            "--built-in-detections/--no-built-in-detections",
            help="Evaluate built-in sequence detections for coverage requirements.",
        ),
    ] = True,
) -> None:
    """Validate a journal against a JSON Lineage Contract."""

    result = _validate_contract_from_files(
        contract_path,
        journal_path,
        built_in_detections=built_in_detections,
    )
    _echo_contract_result(result, output_format=output_format)


@contract_app.command("test")
def contract_test_command(
    contract_path: Annotated[
        Path,
        typer.Argument(exists=True, dir_okay=False, path_type=Path),
    ],
    journal_path: Annotated[
        Path,
        typer.Argument(exists=True, dir_okay=False, path_type=Path),
    ],
    output_format: Annotated[
        str,
        typer.Option("--format", help="Output format: json or annotations."),
    ] = "json",
) -> None:
    """Validate a contract for CI and exit nonzero on failure."""

    result = _validate_contract_from_files(
        contract_path,
        journal_path,
        built_in_detections=True,
    )
    _echo_contract_result(result, output_format=output_format)
    if not result.ok:
        raise typer.Exit(1)


def _validate_contract_from_files(
    contract_path: Path,
    journal_path: Path,
    *,
    built_in_detections: bool,
) -> ContractResult:
    try:
        contract = load_contract(contract_path)
        events = tuple(LocalJournal(journal_path).iter_events())
    except ActionLineageValidationError as exc:
        typer.echo(json.dumps({"ok": False, "error": str(exc)}, sort_keys=True))
        raise typer.Exit(1) from None
    detection_results = _evaluate_built_in_detections(events) if built_in_detections else ()
    return validate_contract(events, contract, detection_results=detection_results)


def _evaluate_built_in_detections(events: tuple[EventEnvelope, ...]) -> tuple[DetectionMatch, ...]:
    matches: list[DetectionMatch] = []
    for rule in built_in_sequence_rules():
        matches.extend(evaluate_sequence_rule(events, rule))
    return tuple(matches)


def _echo_contract_result(result: ContractResult, *, output_format: str) -> None:
    if output_format == "json":
        typer.echo(json.dumps(result.as_dict(), sort_keys=True))
        return
    if output_format == "annotations":
        for line in contract_result_annotations(result):
            typer.echo(line)
        return
    typer.echo(
        json.dumps(
            {
                "ok": False,
                "error": "unsupported contract output format",
                "supported_formats": ["annotations", "json"],
            },
            sort_keys=True,
        )
    )
    raise typer.Exit(2)


@detection_app.command("explain-sequence")
def detection_explain_sequence_command(
    rule_path: Annotated[
        Path,
        typer.Argument(exists=True, dir_okay=False, path_type=Path),
    ],
    journal_path: Annotated[
        Path,
        typer.Argument(exists=True, dir_okay=False, path_type=Path),
    ],
) -> None:
    """Explain sequence-rule stage candidates for a journal."""

    try:
        rules = load_sequence_rules(rule_path)
        events = tuple(LocalJournal(journal_path).iter_events())
    except (ActionLineageValidationError, DetectionRuleLoadError) as exc:
        typer.echo(json.dumps({"ok": False, "error": str(exc)}, sort_keys=True))
        raise typer.Exit(1) from None

    explanations = [explain_sequence_rule(events, rule).as_dict() for rule in rules]
    typer.echo(json.dumps({"ok": True, "rules": explanations}, sort_keys=True))


@journal_app.command("verify")
def verify_journal_command(
    journal_path: Annotated[
        Path,
        typer.Argument(exists=False, dir_okay=False, path_type=Path),
    ],
    expected_record_count: Annotated[
        int | None,
        typer.Option(
            "--expected-record-count",
            min=0,
            help="Trusted record count used to detect truncation.",
        ),
    ] = None,
    expected_last_event_hash: Annotated[
        str | None,
        typer.Option(
            "--expected-last-event-hash",
            help="Trusted last event hash used to detect truncation or full rewrite.",
        ),
    ] = None,
) -> None:
    """Verify a local ActionLineage journal and print JSON."""

    result = verify_journal(
        journal_path,
        expected_record_count=expected_record_count,
        expected_last_event_hash=expected_last_event_hash,
    )
    typer.echo(json.dumps(result.as_dict(), sort_keys=True))
    if not result.ok:
        raise typer.Exit(1)


@journal_app.command("create-anchor")
def create_anchor_command(
    journal_path: Annotated[
        Path,
        typer.Argument(exists=False, dir_okay=False, path_type=Path),
    ],
    anchor_path: Annotated[
        Path,
        typer.Argument(exists=False, dir_okay=False, path_type=Path),
    ],
    signing_key_file: Annotated[
        Path | None,
        typer.Option(
            "--signing-key-file",
            exists=True,
            dir_okay=False,
            path_type=Path,
            help="File containing HMAC signing key bytes for a signed anchor.",
        ),
    ] = None,
) -> None:
    """Create a trusted local journal anchor."""

    signing_key = signing_key_file.read_bytes() if signing_key_file is not None else None
    anchor = create_journal_anchor(journal_path, signing_key=signing_key)
    write_journal_anchor(anchor, anchor_path)
    typer.echo(json.dumps(anchor.as_dict(), sort_keys=True))


@journal_app.command("verify-anchor")
def verify_anchor_command(
    journal_path: Annotated[
        Path,
        typer.Argument(exists=False, dir_okay=False, path_type=Path),
    ],
    anchor_path: Annotated[
        Path,
        typer.Argument(exists=True, dir_okay=False, path_type=Path),
    ],
    signing_key_file: Annotated[
        Path | None,
        typer.Option(
            "--signing-key-file",
            exists=True,
            dir_okay=False,
            path_type=Path,
            help="File containing HMAC signing key bytes for a signed anchor.",
        ),
    ] = None,
) -> None:
    """Verify a journal against a trusted local anchor."""

    signing_key = signing_key_file.read_bytes() if signing_key_file is not None else None
    result = verify_journal_anchor(
        journal_path,
        load_journal_anchor(anchor_path),
        signing_key=signing_key,
    )
    typer.echo(json.dumps(result.as_dict(), sort_keys=True))
    if not result.ok:
        raise typer.Exit(1)


@journal_app.command("append-anchor-log")
def append_anchor_log_command(
    anchor_path: Annotated[
        Path,
        typer.Argument(exists=True, dir_okay=False, path_type=Path),
    ],
    log_path: Annotated[
        Path,
        typer.Argument(exists=False, dir_okay=False, path_type=Path),
    ],
) -> None:
    """Append a trusted anchor to a local anchor log."""

    entry = append_journal_anchor_log(log_path, load_journal_anchor(anchor_path))
    typer.echo(json.dumps(entry.as_dict(), sort_keys=True))


@journal_app.command("verify-anchor-log")
def verify_anchor_log_command(
    log_path: Annotated[
        Path,
        typer.Argument(exists=False, dir_okay=False, path_type=Path),
    ],
    expected_record_count: Annotated[
        int | None,
        typer.Option(
            "--expected-record-count",
            min=0,
            help="Trusted anchor-log record count used to detect truncation.",
        ),
    ] = None,
    expected_last_entry_hash: Annotated[
        str | None,
        typer.Option(
            "--expected-last-entry-hash",
            help="Trusted last anchor-log entry hash used to detect truncation or rewrite.",
        ),
    ] = None,
) -> None:
    """Verify a local append-only anchor log."""

    result = verify_journal_anchor_log(
        log_path,
        expected_record_count=expected_record_count,
        expected_last_entry_hash=expected_last_entry_hash,
    )
    typer.echo(json.dumps(result.as_dict(), sort_keys=True))
    if not result.ok:
        raise typer.Exit(1)


@journal_app.command("create-git-anchor-statement")
def create_git_anchor_statement_command(
    anchor_path: Annotated[
        Path,
        typer.Argument(exists=True, dir_okay=False, path_type=Path),
    ],
    statement_path: Annotated[
        Path,
        typer.Argument(exists=False, dir_okay=False, path_type=Path),
    ],
    repository_path: Annotated[
        Path,
        typer.Option(
            "--repo",
            exists=True,
            file_okay=False,
            path_type=Path,
            help="Git repository containing the trusted ref.",
        ),
    ] = Path("."),
    ref: Annotated[
        str,
        typer.Option("--ref", help="Git ref or commit to record in the statement."),
    ] = "HEAD",
) -> None:
    """Create a Git-backed sidecar statement for a trusted anchor."""

    try:
        statement = create_git_anchor_statement(
            anchor_path,
            repository_path=repository_path,
            ref=ref,
        )
    except JournalAnchorError as exc:
        typer.echo(json.dumps({"ok": False, "error": str(exc)}, sort_keys=True))
        raise typer.Exit(1) from None

    write_git_anchor_statement(statement, statement_path)
    typer.echo(json.dumps(statement.as_dict(), sort_keys=True))


@journal_app.command("verify-git-anchor-statement")
def verify_git_anchor_statement_command(
    anchor_path: Annotated[
        Path,
        typer.Argument(exists=False, dir_okay=False, path_type=Path),
    ],
    statement_path: Annotated[
        Path,
        typer.Argument(exists=True, dir_okay=False, path_type=Path),
    ],
    repository_path: Annotated[
        Path | None,
        typer.Option(
            "--repo",
            exists=True,
            file_okay=False,
            path_type=Path,
            help="Override the repository path recorded in the statement.",
        ),
    ] = None,
    ref: Annotated[
        str | None,
        typer.Option(
            "--ref",
            help="Optionally require this ref to resolve to the recorded commit.",
        ),
    ] = None,
) -> None:
    """Verify a Git-backed sidecar statement for a trusted anchor."""

    try:
        statement = load_git_anchor_statement(statement_path)
        result = verify_git_anchor_statement(
            statement,
            anchor_path=anchor_path,
            repository_path=repository_path,
            ref=ref,
        )
    except JournalAnchorError as exc:
        typer.echo(json.dumps({"ok": False, "error": str(exc)}, sort_keys=True))
        raise typer.Exit(1) from None

    typer.echo(json.dumps(result.as_dict(), sort_keys=True))
    if not result.ok:
        raise typer.Exit(1)


@journal_app.command("create-external-attestation")
def create_external_attestation_command(
    anchor_path: Annotated[
        Path,
        typer.Argument(exists=True, dir_okay=False, path_type=Path),
    ],
    attestation_path: Annotated[
        Path,
        typer.Argument(exists=False, dir_okay=False, path_type=Path),
    ],
    statement_file: Annotated[
        Path,
        typer.Option(
            "--statement-file",
            exists=True,
            dir_okay=False,
            path_type=Path,
            help="External attestation statement bytes, such as HSM or TSA output.",
        ),
    ],
    attester: Annotated[str, typer.Option("--attester", help="External attester identity.")],
    attestation_type: Annotated[
        ExternalAttestationType,
        typer.Option("--attestation-type", help="External attestation mechanism label."),
    ] = ExternalAttestationType.REMOTE_ATTESTATION,
    statement_reference: Annotated[
        str | None,
        typer.Option("--statement-reference", help="Optional external statement reference."),
    ] = None,
) -> None:
    """Create a sidecar linking an anchor to external attestation bytes."""

    try:
        anchor = load_journal_anchor(anchor_path)
        attestation = create_external_anchor_attestation(
            anchor,
            attester=attester,
            attestation_type=attestation_type,
            statement_bytes=statement_file.read_bytes(),
            statement_reference=statement_reference,
        )
    except (JournalAnchorError, ValueError) as exc:
        typer.echo(json.dumps({"ok": False, "error": str(exc)}, sort_keys=True))
        raise typer.Exit(1) from None

    write_external_anchor_attestation(attestation, attestation_path)
    typer.echo(json.dumps(attestation.as_dict(), sort_keys=True))


@journal_app.command("verify-external-attestation")
def verify_external_attestation_command(
    anchor_path: Annotated[
        Path,
        typer.Argument(exists=True, dir_okay=False, path_type=Path),
    ],
    attestation_path: Annotated[
        Path,
        typer.Argument(exists=True, dir_okay=False, path_type=Path),
    ],
    statement_file: Annotated[
        Path | None,
        typer.Option(
            "--statement-file",
            exists=True,
            dir_okay=False,
            path_type=Path,
            help="Optional local statement bytes to compare with the recorded digest.",
        ),
    ] = None,
) -> None:
    """Verify local consistency of an external anchor attestation sidecar."""

    try:
        anchor = load_journal_anchor(anchor_path)
        attestation = load_external_anchor_attestation(attestation_path)
        result = verify_external_anchor_attestation(
            anchor,
            attestation,
            statement_bytes=statement_file.read_bytes() if statement_file else None,
        )
    except (JournalAnchorError, ValueError) as exc:
        typer.echo(json.dumps({"ok": False, "error": str(exc)}, sort_keys=True))
        raise typer.Exit(1) from None

    typer.echo(json.dumps(result.as_dict(), sort_keys=True))
    if not result.ok:
        raise typer.Exit(1)


@journal_app.command("create-archive-manifest")
def create_archive_manifest_command(
    journal_path: Annotated[
        Path,
        typer.Argument(exists=False, dir_okay=False, path_type=Path),
    ],
    manifest_path: Annotated[
        Path,
        typer.Argument(exists=False, dir_okay=False, path_type=Path),
    ],
    object_uri: Annotated[
        str,
        typer.Option("--object-uri", help="Intended archived object URI, such as s3://bucket/key."),
    ],
    retention_mode: Annotated[
        str,
        typer.Option(
            "--retention-mode",
            help="Object retention label: none, governance, compliance, or legal_hold.",
        ),
    ] = "none",
    storage_class: Annotated[
        str | None,
        typer.Option("--storage-class", help="Optional object storage class label."),
    ] = None,
) -> None:
    """Create a local manifest for an archived journal object."""

    try:
        manifest = create_journal_archive_manifest(
            journal_path,
            object_uri=object_uri,
            retention_mode=_archive_retention_mode(retention_mode),
            storage_class=storage_class,
        )
    except JournalAnchorError as exc:
        typer.echo(json.dumps({"ok": False, "error": str(exc)}, sort_keys=True))
        raise typer.Exit(1) from None

    write_journal_archive_manifest(manifest, manifest_path)
    typer.echo(json.dumps(manifest.as_dict(), sort_keys=True))


@journal_app.command("verify-archive-manifest")
def verify_archive_manifest_command(
    manifest_path: Annotated[
        Path,
        typer.Argument(exists=True, dir_okay=False, path_type=Path),
    ],
    journal_path: Annotated[
        Path | None,
        typer.Option(
            "--journal",
            exists=False,
            dir_okay=False,
            path_type=Path,
            help="Override the journal path recorded in the manifest.",
        ),
    ] = None,
) -> None:
    """Verify local journal bytes against an archive manifest."""

    try:
        result = verify_journal_archive_manifest(
            load_journal_archive_manifest(manifest_path),
            journal_path=journal_path,
        )
    except JournalAnchorError as exc:
        typer.echo(json.dumps({"ok": False, "error": str(exc)}, sort_keys=True))
        raise typer.Exit(1) from None

    typer.echo(json.dumps(result.as_dict(), sort_keys=True))
    if not result.ok:
        raise typer.Exit(1)


def _archive_retention_mode(value: str) -> ArchiveRetentionMode:
    if value in {"none", "governance", "compliance", "legal_hold"}:
        return cast(ArchiveRetentionMode, value)
    raise JournalAnchorError("invalid archive retention mode")


@journal_app.command("export-verified-prefix")
def export_verified_prefix_command(
    journal_path: Annotated[
        Path,
        typer.Argument(exists=False, dir_okay=False, path_type=Path),
    ],
    output_path: Annotated[
        Path,
        typer.Argument(exists=False, dir_okay=False, path_type=Path),
    ],
    expected_record_count: Annotated[
        int | None,
        typer.Option(
            "--expected-record-count",
            min=0,
            help="Trusted record count used to detect truncation.",
        ),
    ] = None,
    expected_last_event_hash: Annotated[
        str | None,
        typer.Option(
            "--expected-last-event-hash",
            help="Trusted last event hash used to detect truncation or full rewrite.",
        ),
    ] = None,
) -> None:
    """Export records verified before the first detected journal issue."""

    try:
        result = export_verified_prefix(
            journal_path,
            output_path,
            expected_record_count=expected_record_count,
            expected_last_event_hash=expected_last_event_hash,
        )
    except JournalAnchorError as exc:
        typer.echo(json.dumps({"ok": False, "error": str(exc)}, sort_keys=True))
        raise typer.Exit(1) from None

    typer.echo(json.dumps(result.as_dict(), sort_keys=True))


@projection_app.command("rebuild")
def rebuild_projection_command(
    journal_path: Annotated[
        Path,
        typer.Argument(exists=False, dir_okay=False, path_type=Path),
    ],
    database_path: Annotated[
        Path,
        typer.Argument(exists=False, dir_okay=False, path_type=Path),
    ],
) -> None:
    """Rebuild the SQLite projection from a verified local journal."""

    try:
        result = rebuild_projection(journal_path, database_path)
    except ProjectionVerificationError as exc:
        typer.echo(
            json.dumps(
                {
                    "ok": False,
                    "error": "journal_verification_failed",
                    "journal_path": str(exc.journal_path),
                    "verification": exc.verification.as_dict(),
                },
                sort_keys=True,
            )
        )
        raise typer.Exit(1) from None
    except ProjectionError as exc:
        typer.echo(json.dumps({"ok": False, "error": str(exc)}, sort_keys=True))
        raise typer.Exit(1) from None

    typer.echo(json.dumps(result.as_dict(), sort_keys=True))


@projection_app.command("timeline")
def timeline_command(
    database_path: Annotated[
        Path,
        typer.Argument(exists=True, dir_okay=False, path_type=Path),
    ],
    trace_id: Annotated[
        str | None,
        typer.Option("--trace-id", help="Trace ID to query."),
    ] = None,
    run_id: Annotated[
        str | None,
        typer.Option("--run-id", help="Run ID to query."),
    ] = None,
) -> None:
    """Query a projected lineage timeline by trace or run."""

    try:
        result = query_timeline(database_path, trace_id=trace_id, run_id=run_id)
    except ProjectionError as exc:
        typer.echo(json.dumps({"ok": False, "error": str(exc)}, sort_keys=True))
        raise typer.Exit(1) from None

    typer.echo(json.dumps(result.as_dict(), sort_keys=True))


@projection_app.command("filter")
def filter_timeline_command(
    database_path: Annotated[
        Path,
        typer.Argument(exists=True, dir_okay=False, path_type=Path),
    ],
    trace_id: Annotated[str | None, typer.Option("--trace-id")] = None,
    run_id: Annotated[str | None, typer.Option("--run-id")] = None,
    event_type: Annotated[str | None, typer.Option("--event-type")] = None,
    principal_id: Annotated[str | None, typer.Option("--principal-id")] = None,
    tool_name: Annotated[str | None, typer.Option("--tool-name")] = None,
    resource: Annotated[str | None, typer.Option("--resource")] = None,
    verification_status: Annotated[str | None, typer.Option("--verification-status")] = None,
    sensitivity: Annotated[str | None, typer.Option("--sensitivity")] = None,
    trust: Annotated[str | None, typer.Option("--trust")] = None,
    descriptor_hash: Annotated[str | None, typer.Option("--descriptor-hash")] = None,
) -> None:
    """Query projected lineage events with investigation filters."""

    try:
        result = query_filtered_timeline(
            database_path,
            trace_id=trace_id,
            run_id=run_id,
            event_type=event_type,
            principal_id=principal_id,
            tool_name=tool_name,
            resource=resource,
            verification_status=verification_status,
            sensitivity=sensitivity,
            trust=trust,
            descriptor_hash=descriptor_hash,
        )
    except ProjectionError as exc:
        typer.echo(json.dumps({"ok": False, "error": str(exc)}, sort_keys=True))
        raise typer.Exit(1) from None

    typer.echo(json.dumps(result.as_dict(), sort_keys=True))


@projection_app.command("explain-event")
def explain_event_command(
    database_path: Annotated[
        Path,
        typer.Argument(exists=True, dir_okay=False, path_type=Path),
    ],
    event_id: Annotated[str, typer.Argument()],
) -> None:
    """Explain causal and evidence-link context for one event."""

    try:
        result = explain_event(database_path, event_id=event_id)
    except ProjectionError as exc:
        typer.echo(json.dumps({"ok": False, "error": str(exc)}, sort_keys=True))
        raise typer.Exit(1) from None

    typer.echo(json.dumps(result.as_dict(), sort_keys=True))


@projection_app.command("export-incident")
def export_incident_command(
    database_path: Annotated[
        Path,
        typer.Argument(exists=True, dir_okay=False, path_type=Path),
    ],
    trace_id: Annotated[
        str | None,
        typer.Option("--trace-id", help="Trace ID to export."),
    ] = None,
    run_id: Annotated[
        str | None,
        typer.Option("--run-id", help="Run ID to export."),
    ] = None,
) -> None:
    """Export a projected lineage timeline as incident JSON."""

    try:
        result = export_incident(database_path, trace_id=trace_id, run_id=run_id)
    except ProjectionError as exc:
        typer.echo(json.dumps({"ok": False, "error": str(exc)}, sort_keys=True))
        raise typer.Exit(1) from None

    typer.echo(json.dumps(result.as_dict(), sort_keys=True))


@projection_app.command("summarize")
def summarize_incident_command(
    database_path: Annotated[
        Path,
        typer.Argument(exists=True, dir_okay=False, path_type=Path),
    ],
    trace_id: Annotated[str | None, typer.Option("--trace-id")] = None,
    run_id: Annotated[str | None, typer.Option("--run-id")] = None,
) -> None:
    """Generate a deterministic evidence-grounded investigation summary."""

    try:
        result = summarize_incident(database_path, trace_id=trace_id, run_id=run_id)
    except ProjectionError as exc:
        typer.echo(json.dumps({"ok": False, "error": str(exc)}, sort_keys=True))
        raise typer.Exit(1) from None

    typer.echo(json.dumps(result.as_dict(), sort_keys=True))


@projection_app.command("export-graph")
def export_graph_command(
    database_path: Annotated[
        Path,
        typer.Argument(exists=True, dir_okay=False, path_type=Path),
    ],
    trace_id: Annotated[str | None, typer.Option("--trace-id")] = None,
    run_id: Annotated[str | None, typer.Option("--run-id")] = None,
) -> None:
    """Export a dependency-free investigation graph."""

    try:
        result = export_investigation_graph(database_path, trace_id=trace_id, run_id=run_id)
    except ProjectionError as exc:
        typer.echo(json.dumps({"ok": False, "error": str(exc)}, sort_keys=True))
        raise typer.Exit(1) from None

    typer.echo(json.dumps(result.as_dict(), sort_keys=True))


@projection_app.command("export-case")
def export_case_command(
    database_path: Annotated[
        Path,
        typer.Argument(exists=True, dir_okay=False, path_type=Path),
    ],
    output_dir: Annotated[
        Path,
        typer.Argument(exists=False, dir_okay=True, file_okay=False, path_type=Path),
    ],
    trace_id: Annotated[
        str | None,
        typer.Option("--trace-id", help="Trace ID to export."),
    ] = None,
    run_id: Annotated[
        str | None,
        typer.Option("--run-id", help="Run ID to export."),
    ] = None,
) -> None:
    """Export a redacted investigation case bundle."""

    try:
        result = export_case_bundle(database_path, output_dir, trace_id=trace_id, run_id=run_id)
    except ProjectionError as exc:
        typer.echo(json.dumps({"ok": False, "error": str(exc)}, sort_keys=True))
        raise typer.Exit(1) from None

    typer.echo(json.dumps(result.as_dict(), sort_keys=True))


@projection_app.command("export-console")
def export_console_command(
    database_path: Annotated[
        Path,
        typer.Argument(exists=True, dir_okay=False, path_type=Path),
    ],
    output_path: Annotated[
        Path,
        typer.Argument(exists=False, dir_okay=False, path_type=Path),
    ],
    trace_id: Annotated[
        str | None,
        typer.Option("--trace-id", help="Trace ID to render."),
    ] = None,
    run_id: Annotated[
        str | None,
        typer.Option("--run-id", help="Run ID to render."),
    ] = None,
    case_context: Annotated[
        Path | None,
        typer.Option(
            "--case-context",
            exists=True,
            dir_okay=False,
            path_type=Path,
            help="JSON file with sanitized console notes and saved views.",
        ),
    ] = None,
) -> None:
    """Export a static investigation console HTML file."""

    try:
        notes, saved_views = (
            load_console_context(case_context) if case_context is not None else ((), ())
        )
        result = write_console(
            database_path,
            output_path,
            trace_id=trace_id,
            run_id=run_id,
            notes=notes,
            saved_views=saved_views,
        )
    except ConsoleContextError as exc:
        typer.echo(json.dumps({"ok": False, "error": str(exc)}, sort_keys=True))
        raise typer.Exit(1) from None
    except ProjectionError as exc:
        typer.echo(json.dumps({"ok": False, "error": str(exc)}, sort_keys=True))
        raise typer.Exit(1) from None

    typer.echo(json.dumps(result.as_dict(), sort_keys=True))


@projection_app.command("export-desktop-bundle")
def export_desktop_bundle_command(
    database_path: Annotated[
        Path,
        typer.Argument(exists=True, dir_okay=False, path_type=Path),
    ],
    output_dir: Annotated[
        Path,
        typer.Argument(exists=False, dir_okay=True, file_okay=False, path_type=Path),
    ],
    trace_id: Annotated[
        str | None,
        typer.Option("--trace-id", help="Trace ID to render."),
    ] = None,
    run_id: Annotated[
        str | None,
        typer.Option("--run-id", help="Run ID to render."),
    ] = None,
    case_context: Annotated[
        Path | None,
        typer.Option(
            "--case-context",
            exists=True,
            dir_okay=False,
            path_type=Path,
            help="JSON file with sanitized console notes and saved view hints.",
        ),
    ] = None,
) -> None:
    """Export a static bundle for optional native desktop shells."""

    try:
        notes, saved_views = (
            load_console_context(case_context) if case_context is not None else ((), ())
        )
        result = write_desktop_bundle(
            database_path,
            output_dir,
            trace_id=trace_id,
            run_id=run_id,
            notes=notes,
            saved_views=saved_views,
        )
    except ConsoleContextError as exc:
        typer.echo(json.dumps({"ok": False, "error": str(exc)}, sort_keys=True))
        raise typer.Exit(1) from None
    except ProjectionError as exc:
        typer.echo(json.dumps({"ok": False, "error": str(exc)}, sort_keys=True))
        raise typer.Exit(1) from None

    typer.echo(json.dumps(result.as_dict(), sort_keys=True))
