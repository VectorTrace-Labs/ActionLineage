from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from actionlineage.journal import LocalJournal

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def test_journal_ingest_benchmark_script_outputs_json_report(tmp_path: Path) -> None:
    output_dir = tmp_path / "benchmark"
    report_path = tmp_path / "reports" / "journal-benchmark.json"
    result = subprocess.run(
        [
            sys.executable,
            "scripts/benchmark_journal_ingest.py",
            "--counts",
            "3,3",
            "--chunk-size",
            "2",
            "--repetitions",
            "1",
            "--output-dir",
            str(output_dir),
            "--report-path",
            str(report_path),
        ],
        cwd=PROJECT_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    assert result.stderr == ""
    report = json.loads(result.stdout)
    assert json.loads(report_path.read_text(encoding="utf-8")) == report
    assert report_path.stat().st_mode & 0o777 == 0o600
    benchmark = report["results"][0]
    journal_path = Path(benchmark["journal_path"])
    snapshot = LocalJournal(journal_path).verified_snapshot()

    assert report["schema_version"] == "actionlineage.dev/journal-ingest-benchmark-v1"
    assert report["counts"] == [3]
    assert report["chunk_size"] == 2
    assert report["repetitions"] == 1
    assert report["temporary_output_dir"] is False
    assert benchmark["record_count"] == 3
    assert journal_path.parent == output_dir
    assert snapshot.ok
    assert snapshot.record_count == 3
    assert benchmark["verify_seconds"]["samples"]
    assert benchmark["duplicate_idempotency_scan_seconds"]["samples"]

    analysis = report["analysis"]
    assert analysis["schema_version"] == "actionlineage.dev/journal-ingest-benchmark-analysis-v1"
    assert analysis["measured_operations"] == [
        "verified_snapshot",
        "duplicate_idempotency_scan",
    ]
    assert analysis["largest_record_count"] == 3
    assert analysis["largest_verify_median_seconds"] == benchmark["verify_seconds"]["median"]
    assert (
        analysis["largest_duplicate_idempotency_scan_median_seconds"]
        == benchmark["duplicate_idempotency_scan_seconds"]["median"]
    )
    assert analysis["median_seconds_per_10000_records"][0]["record_count"] == 3
    assert analysis["decision_boundary"] == {
        "trusted_append_index": "not_allowed",
        "future_append_index_scope": "rebuildable_cache_only",
        "canonical_evidence": "append_only_journal",
        "required_future_cache_tests": [
            "stale_index_fails_closed",
            "tampered_index_fails_closed",
            "mismatched_journal_identity_fails_closed",
            "mismatched_journal_digest_fails_closed",
            "mismatched_record_count_or_terminal_hash_fails_closed",
            "cache_rebuilds_from_verified_journal",
        ],
    }
