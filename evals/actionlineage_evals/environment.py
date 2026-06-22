"""Disposable environment controllers for Agent Validation Lab scenarios."""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from actionlineage.domain import deterministic_json_bytes
from actionlineage_evals.models import JsonMap


class EnvironmentController(Protocol):
    """Common lifecycle interface for eval environments."""

    def start(self) -> JsonMap:
        """Start or describe the environment and return provenance."""

    def stop(self) -> JsonMap:
        """Tear down the environment and return teardown provenance."""


@dataclass(slots=True)
class FixtureEnvironmentController:
    """Deterministic in-process environment used by no-model replay tests."""

    run_dir: Path

    def start(self) -> JsonMap:
        self.run_dir.mkdir(parents=True, exist_ok=True)
        return {
            "controller": "fixture",
            "deterministic": True,
            "run_dir": str(self.run_dir),
        }

    def stop(self) -> JsonMap:
        return {"controller": "fixture", "teardown": "not_required"}


@dataclass(slots=True)
class DockerComposeEnvironmentController:
    """Docker Compose lifecycle controller for local or scheduled evals."""

    run_id: str
    compose_file: Path
    artifact_root: Path
    project_prefix: str = "actionlineage-eval"
    preserve_on_failure: bool = False
    _project_name: str | None = None

    @property
    def project_name(self) -> str:
        if self._project_name is None:
            safe_run_id = "".join(ch if ch.isalnum() else "-" for ch in self.run_id.lower())
            self._project_name = f"{self.project_prefix}-{safe_run_id}"[:63].rstrip("-")
        return self._project_name

    def start(self) -> JsonMap:
        self.artifact_root.mkdir(parents=True, exist_ok=True)
        compose_file = self.compose_file.resolve()
        provenance: JsonMap = {
            "compose_config_digest": self.compose_config_digest(),
            "compose_file": str(compose_file),
            "controller": "docker_compose",
            "docker_compose_version": _command_output(("docker", "compose", "version")),
            "docker_version": _command_output(("docker", "--version")),
            "project_name": self.project_name,
        }
        _run(
            (
                "docker",
                "compose",
                "-f",
                str(compose_file),
                "-p",
                self.project_name,
                "up",
                "-d",
                "--wait",
            ),
            cwd=compose_file.parent,
        )
        provenance["images"] = self.image_digests()
        return provenance

    def stop(self) -> JsonMap:
        compose_file = self.compose_file.resolve()
        logs_dir = self.artifact_root / "docker-logs"
        logs_dir.mkdir(parents=True, exist_ok=True)
        log_result = _run(
            (
                "docker",
                "compose",
                "-f",
                str(compose_file),
                "-p",
                self.project_name,
                "logs",
                "--no-color",
            ),
            cwd=compose_file.parent,
            check=False,
        )
        (logs_dir / "compose.log").write_text(log_result.stdout, encoding="utf-8")
        if self.preserve_on_failure:
            return {
                "controller": "docker_compose",
                "logs": str(logs_dir / "compose.log"),
                "teardown": "preserved",
            }
        _run(
            (
                "docker",
                "compose",
                "-f",
                str(compose_file),
                "-p",
                self.project_name,
                "down",
                "--volumes",
                "--remove-orphans",
            ),
            cwd=compose_file.parent,
            check=False,
        )
        return {
            "controller": "docker_compose",
            "logs": str(logs_dir / "compose.log"),
            "teardown": "down_volumes_remove_orphans",
        }

    def compose_config_digest(self) -> str:
        compose_file = self.compose_file.resolve()
        rendered = _run(
            (
                "docker",
                "compose",
                "-f",
                str(compose_file),
                "-p",
                self.project_name,
                "config",
            ),
            cwd=compose_file.parent,
        ).stdout.encode("utf-8")
        return f"sha256:{hashlib.sha256(rendered).hexdigest()}"

    def image_digests(self) -> list[JsonMap]:
        compose_file = self.compose_file.resolve()
        image_lines = _run(
            (
                "docker",
                "compose",
                "-f",
                str(compose_file),
                "-p",
                self.project_name,
                "images",
                "--format",
                "json",
            ),
            cwd=compose_file.parent,
            check=False,
        ).stdout.splitlines()
        images: list[JsonMap] = []
        for line in image_lines:
            try:
                raw: Any = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(raw, dict):
                images.append({str(key): str(value) for key, value in raw.items()})
        if images:
            return images
        declared_images = _run(
            (
                "docker",
                "compose",
                "-f",
                str(compose_file),
                "-p",
                self.project_name,
                "config",
                "--images",
            ),
            cwd=compose_file.parent,
            check=False,
        ).stdout.splitlines()
        for image in sorted({line.strip() for line in declared_images if line.strip()}):
            inspected = _run(
                ("docker", "image", "inspect", image, "--format", "json"),
                cwd=compose_file.parent,
                check=False,
            )
            if inspected.returncode != 0:
                images.append({"image": image, "inspect_error": inspected.stderr.strip()})
                continue
            try:
                raw_items: Any = json.loads(inspected.stdout)
            except json.JSONDecodeError:
                images.append({"image": image, "inspect_error": "invalid inspect JSON"})
                continue
            if not isinstance(raw_items, list) or not raw_items:
                images.append({"image": image, "inspect_error": "no inspect data"})
                continue
            first = raw_items[0]
            if not isinstance(first, dict):
                images.append({"image": image, "inspect_error": "invalid inspect entry"})
                continue
            repo_digests = first.get("RepoDigests")
            images.append(
                {
                    "image": image,
                    "id": str(first.get("Id", "")),
                    "repo_digests": [str(item) for item in repo_digests]
                    if isinstance(repo_digests, list)
                    else [],
                }
            )
        return images


def build_environment_controller(
    *,
    use_docker: bool,
    run_id: str,
    run_dir: Path,
    compose_file: Path,
    preserve_on_failure: bool = False,
) -> EnvironmentController:
    """Select fixture or Docker lifecycle control."""

    if use_docker:
        if shutil.which("docker") is None:
            raise RuntimeError("docker is required for Docker eval environment")
        return DockerComposeEnvironmentController(
            run_id=run_id,
            compose_file=compose_file,
            artifact_root=run_dir,
            preserve_on_failure=preserve_on_failure,
        )
    return FixtureEnvironmentController(run_dir=run_dir)


def write_environment_report(path: Path, *, start: JsonMap, stop: JsonMap) -> None:
    """Persist environment provenance deterministically."""

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(deterministic_json_bytes({"start": start, "stop": stop}))
    path.write_text(path.read_text(encoding="utf-8") + "\n", encoding="utf-8")


def _run(
    args: tuple[str, ...],
    *,
    cwd: Path,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        args,
        cwd=cwd,
        check=check,
        capture_output=True,
        text=True,
    )


def _command_output(args: tuple[str, ...]) -> str:
    return subprocess.run(args, check=True, capture_output=True, text=True).stdout.strip()
