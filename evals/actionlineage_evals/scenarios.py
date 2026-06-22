"""Scenario DSL loading and validation."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml
from jsonschema.validators import validator_for

from actionlineage_evals.models import JsonMap, ScenarioDefinition

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SCENARIO_SCHEMA_PATH = PROJECT_ROOT / "evals" / "SCENARIO_SCHEMA.json"
CAPABILITY_COVERAGE_PATH = PROJECT_ROOT / "evals" / "CAPABILITY_COVERAGE.yaml"
SCENARIO_DIR = PROJECT_ROOT / "evals" / "scenarios"


class ScenarioValidationError(ValueError):
    """Raised when an eval scenario does not match the DSL."""


def load_schema(path: Path = SCENARIO_SCHEMA_PATH) -> JsonMap:
    """Load the JSON Schema document used by eval scenarios."""

    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ScenarioValidationError("scenario schema must be a JSON object")
    validator_cls = validator_for(data)
    validator_cls.check_schema(data)
    return data


def load_scenario(path: Path, *, schema: JsonMap | None = None) -> ScenarioDefinition:
    """Load and validate one scenario YAML or JSON document."""

    path = Path(path)
    raw = _load_mapping(path)
    active_schema = schema or load_schema()
    validator_cls = validator_for(active_schema)
    validator = validator_cls(active_schema)
    errors = sorted(validator.iter_errors(raw), key=lambda error: list(error.path))
    if errors:
        first = errors[0]
        location = ".".join(str(part) for part in first.path) or "<root>"
        raise ScenarioValidationError(f"{path}: {location}: {first.message}")
    return ScenarioDefinition(path=path, raw=raw)


def discover_scenarios(path: Path = SCENARIO_DIR) -> tuple[Path, ...]:
    """Return scenario files under a directory or a single file path."""

    path = Path(path)
    if path.is_file():
        return (path,)
    return tuple(sorted(path.glob("AVL-*.yaml")))


def load_scenarios(path: Path = SCENARIO_DIR) -> tuple[ScenarioDefinition, ...]:
    """Load all scenario files from a directory or one scenario file."""

    schema = load_schema()
    return tuple(load_scenario(item, schema=schema) for item in discover_scenarios(path))


def load_capability_coverage(path: Path = CAPABILITY_COVERAGE_PATH) -> JsonMap:
    """Load the semantic capability coverage registry."""

    raw = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ScenarioValidationError("capability coverage file must be a YAML object")
    return raw


def validate_capability_coverage(path: Path = CAPABILITY_COVERAGE_PATH) -> JsonMap:
    """Validate coverage references and return a machine-readable report."""

    coverage = load_capability_coverage(path)
    scenarios = coverage.get("scenarios")
    capabilities = coverage.get("capabilities")
    if not isinstance(scenarios, list) or not isinstance(capabilities, dict):
        raise ScenarioValidationError("coverage YAML must define scenarios and capabilities")

    scenario_ids = [str(item["id"]) for item in scenarios if isinstance(item, dict)]
    missing_capabilities: dict[str, list[str]] = {}
    capability_ids = set(capabilities)
    for scenario in scenarios:
        if not isinstance(scenario, dict):
            raise ScenarioValidationError("coverage scenario entries must be objects")
        covers = scenario.get("covers", ())
        if not isinstance(covers, list):
            raise ScenarioValidationError(f"{scenario.get('id')}: covers must be a list")
        missing = sorted(str(item) for item in covers if str(item) not in capability_ids)
        if missing:
            missing_capabilities[str(scenario["id"])] = missing

    return {
        "ok": not missing_capabilities,
        "scenario_ids": scenario_ids,
        "capability_count": len(capability_ids),
        "missing_capabilities": missing_capabilities,
    }


def _load_mapping(path: Path) -> JsonMap:
    if path.suffix.lower() == ".json":
        raw: Any = json.loads(path.read_text(encoding="utf-8"))
    elif path.suffix.lower() in {".yaml", ".yml"}:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    else:
        raise ScenarioValidationError(f"scenario file must be .yaml, .yml, or .json: {path}")
    if not isinstance(raw, dict):
        raise ScenarioValidationError(f"scenario file must contain an object: {path}")
    return raw
