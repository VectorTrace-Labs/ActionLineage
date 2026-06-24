#!/usr/bin/env python3
"""Benchmark local journal verification and idempotency scan costs."""

from __future__ import annotations

import argparse
import json
import statistics
import tempfile
import time
from collections.abc import Callable, Iterable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from actionlineage.domain import (
    Classification,
    Correlation,
    EventType,
    FixedClock,
    PrefixedUuidGenerator,
    Principal,
    PrincipalType,
    Sensitivity,
    Source,
    TrustLevel,
)
from actionlineage.evidence import (
    EvidenceNormalizer,
    EvidenceRecord,
    EvidenceSourceKind,
    import_evidence_batch_atomically,
)
from actionlineage.journal import LocalJournal

SCHEMA_VERSION = "actionlineage.dev/journal-ingest-benchmark-v1"
BASE_TIME = datetime(2026, 6, 24, 12, 0, tzinfo=UTC)


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Generate synthetic ActionLineage journals and benchmark verified "
            "snapshot plus duplicate-idempotency scan timings."
        )
    )
    parser.add_argument(
        "--counts",
        default="10000,100000",
        help="Comma-separated positive record counts to benchmark.",
    )
    parser.add_argument(
        "--chunk-size",
        type=int,
        default=5000,
        help="Records to generate per setup import chunk.",
    )
    parser.add_argument(
        "--repetitions",
        type=int,
        default=3,
        help="Timing repetitions for each measured operation.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="Directory for generated synthetic journals. Defaults to a temporary directory.",
    )
    parser.add_argument(
        "--report-path",
        type=Path,
        default=None,
        help="Optional JSON file path for the benchmark report. Stdout is still written.",
    )
    args = parser.parse_args()

    counts = _parse_counts(args.counts)
    if args.chunk_size <= 0:
        raise SystemExit("--chunk-size must be positive")
    if args.repetitions <= 0:
        raise SystemExit("--repetitions must be positive")

    if args.output_dir is None:
        with tempfile.TemporaryDirectory(prefix="actionlineage-bench-") as temp_dir:
            report = _run_benchmarks(
                output_dir=Path(temp_dir),
                counts=counts,
                chunk_size=args.chunk_size,
                repetitions=args.repetitions,
                temporary_output_dir=True,
            )
            _write_report(report, report_path=args.report_path)
    else:
        report = _run_benchmarks(
            output_dir=args.output_dir,
            counts=counts,
            chunk_size=args.chunk_size,
            repetitions=args.repetitions,
            temporary_output_dir=False,
        )
        _write_report(report, report_path=args.report_path)
    return 0


def _run_benchmarks(
    *,
    output_dir: Path,
    counts: tuple[int, ...],
    chunk_size: int,
    repetitions: int,
    temporary_output_dir: bool,
) -> dict[str, object]:
    output_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
    results: list[dict[str, object]] = []
    for count in counts:
        journal_path = output_dir / f"journal-{count}.jsonl"
        setup_started = time.perf_counter()
        _prepare_journal(journal_path, record_count=count, chunk_size=chunk_size)
        setup_seconds = time.perf_counter() - setup_started
        journal = LocalJournal(journal_path)
        size_bytes = journal_path.stat().st_size

        verify_seconds = _measure(
            lambda journal=journal, count=count: _verify_expected_count(
                journal,
                expected_count=count,
            ),
            repetitions=repetitions,
        )
        duplicate_seconds = _measure(
            lambda journal=journal, count=count: _scan_duplicate(
                journal,
                record_index=count - 1,
            ),
            repetitions=repetitions,
        )
        results.append(
            {
                "record_count": count,
                "journal_path": str(journal_path),
                "journal_size_bytes": size_bytes,
                "setup_seconds": round(setup_seconds, 6),
                "verify_seconds": _summary(verify_seconds),
                "duplicate_idempotency_scan_seconds": _summary(duplicate_seconds),
            }
        )
    return {
        "schema_version": SCHEMA_VERSION,
        "created_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "counts": list(counts),
        "chunk_size": chunk_size,
        "repetitions": repetitions,
        "temporary_output_dir": temporary_output_dir,
        "results": results,
        "limitations": [
            "Synthetic local benchmark; not production performance evidence.",
            "Duplicate idempotency timing includes journal verification and scan work.",
        ],
    }


def _prepare_journal(path: Path, *, record_count: int, chunk_size: int) -> None:
    path.unlink(missing_ok=True)
    path.with_suffix(f"{path.suffix}.lock").unlink(missing_ok=True)
    journal = LocalJournal(path)
    for start in range(0, record_count, chunk_size):
        stop = min(start + chunk_size, record_count)
        records = tuple(_records(range(start, stop)))
        result = import_evidence_batch_atomically(
            records,
            normalizer=_normalizer(),
            journal=journal,
        )
        if result.imported_count != len(records) or not result.ok:
            raise RuntimeError("benchmark journal generation failed")


def _records(indexes: Iterable[int]) -> Iterable[EvidenceRecord]:
    for index in indexes:
        yield _record(index)


def _record(index: int) -> EvidenceRecord:
    key = f"bench-{index:012d}"
    return EvidenceRecord(
        idempotency_key=key,
        event_type=EventType.AGENT_INTENT_RECORDED,
        payload={"intent": {"summary": "benchmark ingest", "index": index}},
        source_kind=EvidenceSourceKind.EXTERNAL_JSON,
        sort_key=key,
    )


def _normalizer() -> EvidenceNormalizer:
    return EvidenceNormalizer(
        correlation=Correlation(trace_id="trace_benchmark", run_id="run_benchmark"),
        source=Source(component="benchmark", instance_id="journal_ingest", version="1.0.0"),
        principal=Principal(
            principal_id="benchmark_agent",
            principal_type=PrincipalType.AGENT,
        ),
        classification=Classification(sensitivity=Sensitivity.INTERNAL, trust=TrustLevel.LOCAL),
        clock=FixedClock(BASE_TIME),
        id_generator=PrefixedUuidGenerator(),
    )


def _verify_expected_count(journal: LocalJournal, *, expected_count: int) -> None:
    snapshot = journal.verified_snapshot()
    if not snapshot.ok or snapshot.record_count != expected_count:
        raise RuntimeError("journal verification did not produce the expected record count")


def _scan_duplicate(journal: LocalJournal, *, record_index: int) -> None:
    result = import_evidence_batch_atomically(
        (_record(record_index),),
        normalizer=_normalizer(),
        journal=journal,
    )
    if result.duplicate_count != 1 or result.imported_count != 0 or not result.ok:
        raise RuntimeError("duplicate idempotency scan did not report one duplicate")


def _measure(operation: Callable[[], None], *, repetitions: int) -> tuple[float, ...]:
    samples: list[float] = []
    for _ in range(repetitions):
        started = time.perf_counter()
        operation()
        samples.append(time.perf_counter() - started)
    return tuple(samples)


def _summary(samples: tuple[float, ...]) -> dict[str, object]:
    return {
        "min": round(min(samples), 6),
        "median": round(statistics.median(samples), 6),
        "max": round(max(samples), 6),
        "samples": [round(sample, 6) for sample in samples],
    }


def _parse_counts(raw: str) -> tuple[int, ...]:
    counts: list[int] = []
    for value in raw.split(","):
        value = value.strip()
        if not value:
            continue
        try:
            count = int(value)
        except ValueError as exc:
            raise SystemExit(f"invalid record count: {value}") from exc
        if count <= 0:
            raise SystemExit("record counts must be positive")
        if count not in counts:
            counts.append(count)
    if not counts:
        raise SystemExit("at least one record count is required")
    return tuple(counts)


def _write_report(report: dict[str, object], *, report_path: Path | None) -> None:
    payload = json.dumps(_json_ready(report), indent=2, sort_keys=True)
    if report_path is not None:
        report_path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        report_path.write_text(payload + "\n", encoding="utf-8")
        report_path.chmod(0o600)
    print(payload)


def _json_ready(value: Any) -> Any:
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, tuple):
        return [_json_ready(item) for item in value]
    if isinstance(value, list):
        return [_json_ready(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _json_ready(item) for key, item in value.items()}
    return value


if __name__ == "__main__":
    raise SystemExit(main())
