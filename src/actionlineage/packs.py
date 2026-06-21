"""Local extension-pack manifest validation."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from actionlineage.errors import ActionLineageValidationError

PACK_MANIFEST_SCHEMA_VERSION = "actionlineage.dev/pack/v1"
SUPPORTED_PACK_ARTIFACT_KINDS = frozenset(
    {
        "adapter",
        "contract",
        "detection_rule",
        "export_profile",
        "lab_corpus",
        "observer",
    }
)


@dataclass(frozen=True, slots=True)
class PackArtifact:
    """One reviewed artifact listed in an extension pack manifest."""

    kind: str
    name: str
    path: str
    sha256: str | None = None
    media_type: str | None = None
    entrypoint: str | None = None
    metadata: dict[str, object] | None = None

    def as_dict(self) -> dict[str, object]:
        """Return a JSON-compatible artifact object."""

        return {
            "kind": self.kind,
            "name": self.name,
            "path": self.path,
            "sha256": self.sha256,
            "media_type": self.media_type,
            "entrypoint": self.entrypoint,
            "metadata": self.metadata or {},
        }


@dataclass(frozen=True, slots=True)
class ExtensionPackManifest:
    """Manifest for a local adapter, detection, contract, or observer pack."""

    name: str
    version: str
    publisher: str
    license: str
    artifacts: tuple[PackArtifact, ...]
    description: str = ""
    homepage: str | None = None
    tags: tuple[str, ...] = ()
    compatibility: dict[str, object] | None = None
    schema_version: str = PACK_MANIFEST_SCHEMA_VERSION

    def as_dict(self) -> dict[str, object]:
        """Return a JSON-compatible manifest object."""

        return {
            "schema_version": self.schema_version,
            "name": self.name,
            "version": self.version,
            "publisher": self.publisher,
            "license": self.license,
            "description": self.description,
            "homepage": self.homepage,
            "tags": list(self.tags),
            "compatibility": self.compatibility or {},
            "artifacts": [artifact.as_dict() for artifact in self.artifacts],
        }


@dataclass(frozen=True, slots=True)
class PackValidationIssue:
    """One machine-readable pack manifest validation issue."""

    code: str
    message: str
    artifact_name: str | None = None
    path: str | None = None

    def as_dict(self) -> dict[str, object]:
        """Return a JSON-compatible validation issue."""

        return {
            "code": self.code,
            "message": self.message,
            "artifact_name": self.artifact_name,
            "path": self.path,
        }


@dataclass(frozen=True, slots=True)
class PackValidationResult:
    """Validation result for one extension pack manifest."""

    manifest: ExtensionPackManifest
    manifest_path: Path
    ok: bool
    issues: tuple[PackValidationIssue, ...]

    def as_dict(self) -> dict[str, object]:
        """Return a JSON-compatible validation result."""

        return {
            "ok": self.ok,
            "schema_version": self.manifest.schema_version,
            "manifest_path": str(self.manifest_path),
            "pack": {
                "name": self.manifest.name,
                "version": self.manifest.version,
                "publisher": self.manifest.publisher,
                "artifact_count": len(self.manifest.artifacts),
            },
            "issues": [issue.as_dict() for issue in self.issues],
        }


def load_pack_manifest(path: Path) -> ExtensionPackManifest:
    """Load an extension pack manifest from JSON."""

    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ActionLineageValidationError("pack manifest is not valid JSON") from exc
    if not isinstance(data, dict):
        raise ActionLineageValidationError("pack manifest must be a JSON object")
    return pack_manifest_from_dict(data)


def pack_manifest_from_dict(data: dict[str, object]) -> ExtensionPackManifest:
    """Parse a pack manifest from a JSON-compatible dictionary."""

    schema_version = _required_string(data, "schema_version")
    artifacts_value = data.get("artifacts")
    if not isinstance(artifacts_value, list):
        raise ActionLineageValidationError("pack manifest artifacts must be a list")

    artifacts = tuple(_artifact_from_dict(value) for value in artifacts_value)
    return ExtensionPackManifest(
        schema_version=schema_version,
        name=_required_string(data, "name"),
        version=_required_string(data, "version"),
        publisher=_required_string(data, "publisher"),
        license=_required_string(data, "license"),
        description=_optional_string(data, "description") or "",
        homepage=_optional_string(data, "homepage"),
        tags=tuple(_string_list(data.get("tags"), field="tags")),
        compatibility=_object_or_none(data.get("compatibility"), field="compatibility"),
        artifacts=artifacts,
    )


def pack_manifest_to_dict(manifest: ExtensionPackManifest) -> dict[str, object]:
    """Return a deterministic JSON-compatible manifest dictionary."""

    return manifest.as_dict()


def validate_pack_manifest(path: Path) -> PackValidationResult:
    """Validate a local extension pack manifest and its reviewed artifacts."""

    manifest_path = Path(path)
    manifest = load_pack_manifest(manifest_path)
    base_dir = manifest_path.parent
    issues: list[PackValidationIssue] = []

    if manifest.schema_version != PACK_MANIFEST_SCHEMA_VERSION:
        issues.append(
            PackValidationIssue(
                code="unsupported_schema_version",
                message=(f"pack manifest schema_version must be {PACK_MANIFEST_SCHEMA_VERSION}"),
            )
        )

    seen_artifacts: set[tuple[str, str]] = set()
    for artifact in manifest.artifacts:
        key = (artifact.kind, artifact.name)
        if key in seen_artifacts:
            issues.append(
                PackValidationIssue(
                    code="duplicate_artifact",
                    message=f"duplicate artifact kind/name: {artifact.kind}/{artifact.name}",
                    artifact_name=artifact.name,
                    path=artifact.path,
                )
            )
        seen_artifacts.add(key)
        issues.extend(_validate_artifact(base_dir, artifact))

    return PackValidationResult(
        manifest=manifest,
        manifest_path=manifest_path,
        ok=not issues,
        issues=tuple(issues),
    )


def pack_artifact_index(manifest: ExtensionPackManifest) -> dict[str, list[dict[str, object]]]:
    """Group pack artifacts by kind for local catalog display."""

    grouped: dict[str, list[dict[str, object]]] = {}
    for artifact in sorted(manifest.artifacts, key=lambda item: (item.kind, item.name, item.path)):
        grouped.setdefault(artifact.kind, []).append(artifact.as_dict())
    return grouped


def _artifact_from_dict(value: object) -> PackArtifact:
    if not isinstance(value, dict):
        raise ActionLineageValidationError("pack artifact entries must be JSON objects")
    data = dict(value)
    metadata = _object_or_none(data.get("metadata"), field="metadata")
    return PackArtifact(
        kind=_required_string(data, "kind"),
        name=_required_string(data, "name"),
        path=_required_string(data, "path"),
        sha256=_optional_string(data, "sha256"),
        media_type=_optional_string(data, "media_type"),
        entrypoint=_optional_string(data, "entrypoint"),
        metadata=metadata,
    )


def _validate_artifact(base_dir: Path, artifact: PackArtifact) -> tuple[PackValidationIssue, ...]:
    issues: list[PackValidationIssue] = []
    if artifact.kind not in SUPPORTED_PACK_ARTIFACT_KINDS:
        issues.append(
            PackValidationIssue(
                code="unsupported_artifact_kind",
                message=f"unsupported artifact kind: {artifact.kind}",
                artifact_name=artifact.name,
                path=artifact.path,
            )
        )

    resolved = _safe_artifact_path(base_dir, artifact.path)
    if resolved is None:
        return (
            *issues,
            PackValidationIssue(
                code="unsafe_artifact_path",
                message="artifact path must be relative and stay inside the pack directory",
                artifact_name=artifact.name,
                path=artifact.path,
            ),
        )

    if not resolved.exists() or not resolved.is_file():
        issues.append(
            PackValidationIssue(
                code="artifact_missing",
                message="artifact file does not exist",
                artifact_name=artifact.name,
                path=artifact.path,
            )
        )
        return tuple(issues)

    if artifact.sha256 is not None:
        expected = _normalize_sha256(artifact.sha256)
        actual = _file_sha256(resolved)
        if expected is None:
            issues.append(
                PackValidationIssue(
                    code="invalid_sha256_format",
                    message="artifact sha256 must be sha256:<64 lowercase hex characters>",
                    artifact_name=artifact.name,
                    path=artifact.path,
                )
            )
        elif expected != actual:
            issues.append(
                PackValidationIssue(
                    code="sha256_mismatch",
                    message="artifact sha256 does not match local file bytes",
                    artifact_name=artifact.name,
                    path=artifact.path,
                )
            )

    return tuple(issues)


def _safe_artifact_path(base_dir: Path, path_value: str) -> Path | None:
    candidate = PurePosixPath(path_value)
    if candidate.is_absolute() or ".." in candidate.parts or path_value.strip() == "":
        return None
    resolved_base = base_dir.resolve()
    resolved_candidate = (resolved_base / Path(path_value)).resolve()
    try:
        resolved_candidate.relative_to(resolved_base)
    except ValueError:
        return None
    return resolved_candidate


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return f"sha256:{digest.hexdigest()}"


def _normalize_sha256(value: str) -> str | None:
    if not value.startswith("sha256:"):
        return None
    digest = value.removeprefix("sha256:")
    if len(digest) != 64 or not all(char in "0123456789abcdef" for char in digest):
        return None
    return value


def _required_string(data: dict[str, object], field: str) -> str:
    value = data.get(field)
    if not isinstance(value, str) or not value.strip():
        raise ActionLineageValidationError(
            f"pack manifest field must be a nonempty string: {field}"
        )
    return value


def _optional_string(data: dict[str, object], field: str) -> str | None:
    value = data.get(field)
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise ActionLineageValidationError(f"pack manifest field must be a string: {field}")
    return value


def _object_or_none(value: object, *, field: str) -> dict[str, object] | None:
    if value is None:
        return None
    if not isinstance(value, dict):
        raise ActionLineageValidationError(f"pack manifest field must be an object: {field}")
    return dict(value)


def _string_list(value: object, *, field: str) -> tuple[str, ...]:
    if value is None:
        return ()
    if not isinstance(value, list):
        raise ActionLineageValidationError(f"pack manifest field must be a string list: {field}")
    strings: list[str] = []
    for item in value:
        if not isinstance(item, str) or not item.strip():
            raise ActionLineageValidationError(
                f"pack manifest field must contain only nonempty strings: {field}"
            )
        strings.append(item)
    return tuple(strings)
