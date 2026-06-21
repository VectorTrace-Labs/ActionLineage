from __future__ import annotations

import hashlib
import json
from pathlib import Path

from typer.testing import CliRunner

from actionlineage import (
    PACK_MANIFEST_SCHEMA_VERSION,
    ExtensionPackManifest,
    PackArtifact,
    load_pack_manifest,
    pack_artifact_index,
    validate_pack_manifest,
)
from actionlineage.cli import app

runner = CliRunner()


def _sha256(data: bytes) -> str:
    return f"sha256:{hashlib.sha256(data).hexdigest()}"


def _write_manifest(
    tmp_path: Path,
    *,
    artifacts: list[dict[str, object]],
    schema_version: str = PACK_MANIFEST_SCHEMA_VERSION,
) -> Path:
    manifest_path = tmp_path / "actionlineage-pack.json"
    manifest_path.write_text(
        json.dumps(
            {
                "schema_version": schema_version,
                "name": "demo-pack",
                "version": "1.0.0",
                "publisher": "VectorTrace Labs",
                "license": "Apache-2.0",
                "description": "Reviewed local pack fixture.",
                "tags": ["demo", "detection"],
                "compatibility": {"actionlineage": ">=1.0,<2"},
                "artifacts": artifacts,
            },
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    return manifest_path


def test_pack_manifest_validates_local_artifacts_with_checksums(tmp_path: Path) -> None:
    rule_path = tmp_path / "rules" / "sequence.json"
    rule_bytes = b'{"rules":[]}\n'
    rule_path.parent.mkdir()
    rule_path.write_bytes(rule_bytes)
    manifest_path = _write_manifest(
        tmp_path,
        artifacts=[
            {
                "kind": "detection_rule",
                "name": "empty-sequence-pack",
                "path": "rules/sequence.json",
                "sha256": _sha256(rule_bytes),
                "media_type": "application/json",
            }
        ],
    )

    result = validate_pack_manifest(manifest_path)
    manifest = load_pack_manifest(manifest_path)

    assert result.ok is True
    assert result.as_dict()["pack"]["artifact_count"] == 1
    assert pack_artifact_index(manifest)["detection_rule"][0]["name"] == "empty-sequence-pack"


def test_pack_manifest_rejects_path_escape_and_bad_checksum(tmp_path: Path) -> None:
    rule_path = tmp_path / "rules" / "sequence.json"
    rule_path.parent.mkdir()
    rule_path.write_text("{}", encoding="utf-8")
    manifest_path = _write_manifest(
        tmp_path,
        artifacts=[
            {
                "kind": "detection_rule",
                "name": "bad-checksum",
                "path": "rules/sequence.json",
                "sha256": "sha256:" + "0" * 64,
            },
            {
                "kind": "contract",
                "name": "escape",
                "path": "../outside.json",
            },
        ],
    )

    result = validate_pack_manifest(manifest_path)
    codes = {issue.code for issue in result.issues}

    assert result.ok is False
    assert {"sha256_mismatch", "unsafe_artifact_path"} <= codes


def test_pack_manifest_reports_duplicate_and_unsupported_artifacts(tmp_path: Path) -> None:
    artifact_path = tmp_path / "artifact.json"
    artifact_path.write_text("{}", encoding="utf-8")
    manifest_path = _write_manifest(
        tmp_path,
        artifacts=[
            {"kind": "observer", "name": "local", "path": "artifact.json"},
            {"kind": "observer", "name": "local", "path": "artifact.json"},
            {"kind": "unknown", "name": "future", "path": "artifact.json"},
        ],
    )

    result = validate_pack_manifest(manifest_path)
    codes = [issue.code for issue in result.issues]

    assert result.ok is False
    assert "duplicate_artifact" in codes
    assert "unsupported_artifact_kind" in codes


def test_pack_manifest_dict_roundtrip_is_public_api() -> None:
    manifest = ExtensionPackManifest(
        name="api-pack",
        version="1.0.0",
        publisher="VectorTrace Labs",
        license="Apache-2.0",
        artifacts=(PackArtifact(kind="adapter", name="mcp", path="adapter.json"),),
    )

    data = manifest.as_dict()

    assert data["schema_version"] == PACK_MANIFEST_SCHEMA_VERSION
    assert data["artifacts"][0]["kind"] == "adapter"


def test_pack_cli_validate_and_list(tmp_path: Path) -> None:
    contract_path = tmp_path / "contracts" / "demo.json"
    contract_bytes = b'{"contract":true}\n'
    contract_path.parent.mkdir()
    contract_path.write_bytes(contract_bytes)
    manifest_path = _write_manifest(
        tmp_path,
        artifacts=[
            {
                "kind": "contract",
                "name": "demo-contract",
                "path": "contracts/demo.json",
                "sha256": _sha256(contract_bytes),
            }
        ],
    )

    validate_result = runner.invoke(app, ["pack", "validate", str(manifest_path)])
    list_result = runner.invoke(app, ["pack", "list", str(manifest_path)])
    validate_data = json.loads(validate_result.stdout)
    list_data = json.loads(list_result.stdout)

    assert validate_result.exit_code == 0
    assert validate_data["ok"] is True
    assert list_result.exit_code == 0
    assert list_data["artifacts"]["contract"][0]["name"] == "demo-contract"


def test_pack_cli_validate_exits_nonzero_for_invalid_pack(tmp_path: Path) -> None:
    manifest_path = _write_manifest(
        tmp_path,
        artifacts=[{"kind": "contract", "name": "missing", "path": "missing.json"}],
    )

    result = runner.invoke(app, ["pack", "validate", str(manifest_path)])
    data = json.loads(result.stdout)

    assert result.exit_code == 1
    assert data["ok"] is False
    assert data["issues"][0]["code"] == "artifact_missing"
