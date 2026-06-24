from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from actionlineage.journal import LocalJournal

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def test_journal_ingest_benchmark_script_outputs_json_report(tmp_path: Path) -> None:
    output_dir = tmp_path / "benchmark"
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
        ],
        cwd=PROJECT_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    assert result.stderr == ""
    report = json.loads(result.stdout)
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
