"""Minimal ordered sequence detection engine."""

from __future__ import annotations

import importlib
import json
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, cast

from actionlineage.domain import EventEnvelope, event_to_dict
from actionlineage.domain.events import event_type_value


@dataclass(frozen=True, slots=True)
class SequenceStage:
    """One ordered event stage in a detection rule."""

    event_type: str
    where: dict[str, object]
    name: str | None = None


@dataclass(frozen=True, slots=True)
class SequenceRule:
    """Versioned sequence detection rule."""

    name: str
    stages: tuple[SequenceStage, ...]
    rule_id: str | None = None
    version: str = "1"
    severity: str = "medium"
    tags: tuple[str, ...] = ()
    rationale: str = ""
    references: tuple[str, ...] = ()
    required_evidence_quality: tuple[str, ...] = ()
    group_by: tuple[str, ...] = ("correlation.run_id",)
    ordered: bool = True
    within_seconds: float | None = None
    deduplicate: bool = True
    suppression_seconds: float | None = None
    suppression_key: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class DetectionMatch:
    """One matched sequence."""

    rule_name: str
    event_ids: tuple[str, ...]
    group_key: tuple[str, ...]
    rule_id: str | None = None
    severity: str = "medium"

    def as_dict(self) -> dict[str, object]:
        return {
            "evidence": [
                {"event_id": event_id, "stage_index": index}
                for index, event_id in enumerate(self.event_ids)
            ],
            "rule_id": self.rule_id,
            "rule_name": self.rule_name,
            "severity": self.severity,
            "event_ids": list(self.event_ids),
            "group_key": list(self.group_key),
        }


@dataclass(frozen=True, slots=True)
class StageExplanation:
    """Candidate summary for one rule stage within one group."""

    stage_index: int
    event_type: str
    candidate_event_ids: tuple[str, ...]
    stage_name: str | None = None

    def as_dict(self) -> dict[str, object]:
        """Return a JSON-compatible explanation."""

        return {
            "candidate_count": len(self.candidate_event_ids),
            "candidate_event_ids": list(self.candidate_event_ids),
            "event_type": self.event_type,
            "stage_index": self.stage_index,
            "stage_name": self.stage_name,
        }


@dataclass(frozen=True, slots=True)
class GroupExplanation:
    """Rule-stage candidate summary for one grouped event stream."""

    group_key: tuple[str, ...]
    event_count: int
    stages: tuple[StageExplanation, ...]

    def as_dict(self) -> dict[str, object]:
        """Return a JSON-compatible explanation."""

        return {
            "event_count": self.event_count,
            "group_key": list(self.group_key),
            "stages": [stage.as_dict() for stage in self.stages],
        }


@dataclass(frozen=True, slots=True)
class RuleExplanation:
    """Explain why a sequence rule did or did not match."""

    rule_name: str
    rule_id: str | None
    total_events: int
    matches: tuple[DetectionMatch, ...]
    groups: tuple[GroupExplanation, ...]

    def as_dict(self) -> dict[str, object]:
        """Return a JSON-compatible explanation."""

        return {
            "groups": [group.as_dict() for group in self.groups],
            "matched": bool(self.matches),
            "matches": [match.as_dict() for match in self.matches],
            "rule_id": self.rule_id,
            "rule_name": self.rule_name,
            "total_events": self.total_events,
        }


class DetectionRuleLoadError(ValueError):
    """Raised when a rule pack cannot be loaded safely."""


def load_sequence_rules(path: Path) -> tuple[SequenceRule, ...]:
    """Load a JSON or YAML sequence rule pack."""

    path = Path(path)
    data = _load_rule_data(path)
    return tuple(sequence_rule_from_dict(item) for item in _rule_objects_from_data(data))


def sequence_rule_from_dict(data: object) -> SequenceRule:
    """Convert a mapping into a validated sequence rule."""

    if not isinstance(data, dict):
        raise DetectionRuleLoadError("sequence rule must be an object")
    rule_data = _canonical_rule_mapping(cast(dict[object, object], data))
    stages_data = rule_data.get("stages")
    if not isinstance(stages_data, list) or not stages_data:
        raise DetectionRuleLoadError("sequence rule must include at least one stage")
    return SequenceRule(
        rule_id=_optional_string(rule_data, "rule_id"),
        name=_required_string(rule_data, "name"),
        version=_optional_string(rule_data, "version") or "1",
        severity=_optional_string(rule_data, "severity") or "medium",
        tags=_string_tuple(rule_data.get("tags"), field="tags"),
        rationale=_optional_text(rule_data, "rationale") or "",
        references=_string_tuple(rule_data.get("references"), field="references"),
        required_evidence_quality=_string_tuple(
            rule_data.get("required_evidence_quality"),
            field="required_evidence_quality",
        ),
        group_by=_string_tuple(rule_data.get("group_by"), field="group_by")
        or ("correlation.run_id",),
        ordered=_bool_value(rule_data.get("ordered"), default=True, field="ordered"),
        within_seconds=_optional_float(rule_data.get("within_seconds"), field="within_seconds"),
        deduplicate=_bool_value(rule_data.get("deduplicate"), default=True, field="deduplicate"),
        suppression_seconds=_optional_float(
            rule_data.get("suppression_seconds"),
            field="suppression_seconds",
        ),
        suppression_key=_string_tuple(rule_data.get("suppression_key"), field="suppression_key"),
        stages=tuple(_sequence_stage_from_dict(stage) for stage in stages_data),
    )


def sequence_rule_to_dict(rule: SequenceRule) -> dict[str, object]:
    """Return a JSON/YAML-compatible sequence rule object."""

    return {
        "rule_id": rule.rule_id,
        "name": rule.name,
        "version": rule.version,
        "severity": rule.severity,
        "tags": list(rule.tags),
        "rationale": rule.rationale,
        "references": list(rule.references),
        "required_evidence_quality": list(rule.required_evidence_quality),
        "group_by": list(rule.group_by),
        "ordered": rule.ordered,
        "within_seconds": rule.within_seconds,
        "deduplicate": rule.deduplicate,
        "suppression_seconds": rule.suppression_seconds,
        "suppression_key": list(rule.suppression_key),
        "stages": [
            {
                "name": stage.name,
                "event_type": stage.event_type,
                "where": stage.where,
            }
            for stage in rule.stages
        ],
    }


def evaluate_sequence_rule(
    events: tuple[EventEnvelope, ...],
    rule: SequenceRule,
) -> tuple[DetectionMatch, ...]:
    """Evaluate an ordered sequence rule over normalized events."""

    if not rule.stages:
        return ()

    matches: list[DetectionMatch] = []
    for group_key, group_events in _group_events(events, rule.group_by).items():
        ordered_events = tuple(
            sorted(
                group_events,
                key=lambda event: (
                    event.occurred_at,
                    event.causality.sequence,
                    event.event_id,
                ),
            )
        )
        matched_sequences = (
            _match_ordered(ordered_events, rule.stages, within_seconds=rule.within_seconds)
            if rule.ordered
            else _match_unordered(ordered_events, rule.stages, within_seconds=rule.within_seconds)
        )
        for matched_events in _suppress_and_dedupe(
            matched_sequences=matched_sequences,
            rule=rule,
            group_key=group_key,
        ):
            matches.append(
                DetectionMatch(
                    rule_id=rule.rule_id,
                    rule_name=rule.name,
                    severity=rule.severity,
                    event_ids=tuple(event.event_id for event in matched_events),
                    group_key=group_key,
                )
            )
    return tuple(matches)


def explain_sequence_rule(
    events: tuple[EventEnvelope, ...],
    rule: SequenceRule,
) -> RuleExplanation:
    """Explain sequence-rule candidates without echoing event payloads."""

    matches = evaluate_sequence_rule(events, rule)
    groups: list[GroupExplanation] = []
    for group_key, group_events in sorted(_group_events(events, rule.group_by).items()):
        ordered_events = tuple(
            sorted(
                group_events,
                key=lambda event: (
                    event.occurred_at,
                    event.causality.sequence,
                    event.event_id,
                ),
            )
        )
        stage_explanations = tuple(
            StageExplanation(
                stage_index=index,
                stage_name=stage.name,
                event_type=stage.event_type,
                candidate_event_ids=tuple(
                    event.event_id for event in ordered_events if _event_matches_stage(event, stage)
                ),
            )
            for index, stage in enumerate(rule.stages)
        )
        groups.append(
            GroupExplanation(
                group_key=group_key,
                event_count=len(ordered_events),
                stages=stage_explanations,
            )
        )

    return RuleExplanation(
        rule_name=rule.name,
        rule_id=rule.rule_id,
        total_events=len(events),
        matches=matches,
        groups=tuple(groups),
    )


def _load_rule_data(path: Path) -> object:
    suffix = path.suffix.lower()
    if suffix == ".json":
        return json.loads(path.read_text(encoding="utf-8"))
    if suffix in {".yaml", ".yml"}:
        try:
            yaml_module = importlib.import_module("yaml")
        except ImportError as exc:
            raise DetectionRuleLoadError(
                "install actionlineage[adapters] or PyYAML to load YAML rule packs"
            ) from exc
        safe_load = getattr(yaml_module, "safe_load", None)
        if not callable(safe_load):
            raise DetectionRuleLoadError("YAML loader does not expose safe_load")
        return safe_load(path.read_text(encoding="utf-8"))
    raise DetectionRuleLoadError("rule pack must be .json, .yaml, or .yml")


def _rule_objects_from_data(data: object) -> tuple[object, ...]:
    if isinstance(data, list):
        return tuple(data)
    if not isinstance(data, dict):
        raise DetectionRuleLoadError("rule pack must contain a rules array or rule object")
    rules_data = data.get("rules")
    if rules_data is None:
        return (data,)
    if isinstance(rules_data, dict):
        return (rules_data,)
    if isinstance(rules_data, list):
        return tuple(rules_data)
    raise DetectionRuleLoadError("rule pack rules field must be an array or object")


def _canonical_rule_mapping(data: dict[object, object]) -> dict[str, object]:
    if data.get("kind") == "SequenceDetection" or "spec" in data:
        return _package_rule_mapping(data)
    return _string_keyed_mapping(data, field="sequence rule")


def _package_rule_mapping(data: dict[object, object]) -> dict[str, object]:
    kind = data.get("kind")
    if kind != "SequenceDetection":
        raise DetectionRuleLoadError("rule package kind must be SequenceDetection")
    spec = data.get("spec")
    if not isinstance(spec, dict):
        raise DetectionRuleLoadError("rule package spec must be an object")
    metadata = data.get("metadata", {})
    if metadata is None:
        metadata = {}
    if not isinstance(metadata, dict):
        raise DetectionRuleLoadError("rule package metadata must be an object")
    spec_data = _string_keyed_mapping(cast(dict[object, object], spec), field="rule package spec")
    metadata_data = _string_keyed_mapping(
        cast(dict[object, object], metadata),
        field="rule package metadata",
    )
    stages = spec_data.get("stages")
    if not isinstance(stages, list):
        raise DetectionRuleLoadError("rule package spec.stages must be an array")
    return {
        "rule_id": _first_field(metadata_data, spec_data, "rule_id", "ruleId", "id"),
        "name": _first_field(metadata_data, spec_data, "name"),
        "version": _first_field(metadata_data, spec_data, "version"),
        "severity": _first_field(spec_data, "severity"),
        "tags": _first_field(spec_data, metadata_data, "tags"),
        "rationale": _first_field(spec_data, "rationale"),
        "references": _first_field(spec_data, "references"),
        "required_evidence_quality": _first_field(
            spec_data,
            "required_evidence_quality",
            "requiredEvidenceQuality",
        ),
        "group_by": _first_field(spec_data, "group_by", "groupBy"),
        "ordered": _first_field(spec_data, "ordered"),
        "within_seconds": _duration_seconds(
            _first_field(spec_data, "within_seconds", "withinSeconds", "within"),
            field="within",
        ),
        "deduplicate": _first_field(spec_data, "deduplicate"),
        "suppression_seconds": _duration_seconds(
            _first_field(spec_data, "suppression_seconds", "suppressionSeconds"),
            field="suppression_seconds",
        ),
        "suppression_key": _first_field(spec_data, "suppression_key", "suppressionKey"),
        "stages": [_package_stage_mapping(stage) for stage in stages],
    }


def _first_field(*items: object) -> object:
    mappings = [item for item in items if isinstance(item, dict)]
    names = [item for item in items if isinstance(item, str)]
    for mapping in mappings:
        for name in names:
            if name in mapping:
                return mapping[name]
    return None


def _package_stage_mapping(data: object) -> dict[str, object]:
    if not isinstance(data, dict):
        raise DetectionRuleLoadError("rule package stage must be an object")
    stage_data = _string_keyed_mapping(
        cast(dict[object, object], data),
        field="rule package stage",
    )
    return {
        "name": stage_data.get("name"),
        "event_type": _first_field(stage_data, "event_type", "eventType"),
        "where": stage_data.get("where", {}),
    }


def _sequence_stage_from_dict(data: object) -> SequenceStage:
    if not isinstance(data, dict):
        raise DetectionRuleLoadError("sequence stage must be an object")
    stage_data = _string_keyed_mapping(cast(dict[object, object], data), field="sequence stage")
    where = _validated_where(stage_data.get("where", {}))
    return SequenceStage(
        name=_optional_string(stage_data, "name"),
        event_type=_required_string(stage_data, "event_type"),
        where=where,
    )


def _required_string(data: dict[str, object], field: str) -> str:
    value = data.get(field)
    if not isinstance(value, str) or not value:
        raise DetectionRuleLoadError(f"sequence rule field is required: {field}")
    return value


def _optional_string(data: dict[str, object], field: str) -> str | None:
    value = data.get(field)
    if value is None:
        return None
    if not isinstance(value, str) or not value:
        raise DetectionRuleLoadError(f"sequence rule field must be a non-empty string: {field}")
    return value


def _optional_text(data: dict[str, object], field: str) -> str | None:
    value = data.get(field)
    if value is None:
        return None
    if not isinstance(value, str):
        raise DetectionRuleLoadError(f"sequence rule field must be text: {field}")
    return value


def _string_tuple(value: object, *, field: str) -> tuple[str, ...]:
    if value is None:
        return ()
    if not isinstance(value, list) or not all(isinstance(item, str) and item for item in value):
        raise DetectionRuleLoadError(f"sequence rule field must be an array of strings: {field}")
    return tuple(value)


def _bool_value(value: object, *, default: bool, field: str) -> bool:
    if value is None:
        return default
    if not isinstance(value, bool):
        raise DetectionRuleLoadError(f"sequence rule field must be boolean: {field}")
    return value


def _optional_float(value: object, *, field: str) -> float | None:
    if value is None:
        return None
    if not isinstance(value, int | float) or isinstance(value, bool):
        raise DetectionRuleLoadError(f"sequence rule field must be numeric: {field}")
    return float(value)


def _duration_seconds(value: object, *, field: str) -> float | None:
    if value is None:
        return None
    if isinstance(value, int | float) and not isinstance(value, bool):
        return float(value)
    if not isinstance(value, str):
        raise DetectionRuleLoadError(f"sequence rule duration field is invalid: {field}")
    match = re.fullmatch(r"([0-9]+(?:\.[0-9]+)?)(ms|s|m|h)?", value.strip())
    if match is None:
        raise DetectionRuleLoadError(f"sequence rule duration field is invalid: {field}")
    amount = float(match.group(1))
    unit = match.group(2) or "s"
    multiplier = {"ms": 0.001, "s": 1.0, "m": 60.0, "h": 3600.0}[unit]
    return amount * multiplier


def _string_keyed_mapping(data: dict[object, object], *, field: str) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in data.items():
        if not isinstance(key, str) or not key:
            raise DetectionRuleLoadError(f"{field} keys must be non-empty strings")
        result[key] = value
    return result


def _validated_where(value: object) -> dict[str, object]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise DetectionRuleLoadError("sequence stage where must be an object")
    where = _string_keyed_mapping(cast(dict[object, object], value), field="sequence stage where")
    for expected in where.values():
        _validate_predicate(expected)
    return where


def _validate_predicate(expected: object) -> None:
    if not isinstance(expected, dict):
        return
    operators = _string_keyed_mapping(
        cast(dict[object, object], expected),
        field="sequence stage predicate",
    )
    allowed = {"in", "exists", "prefix", "suffix", "regex", "not", "gt", "gte", "lt", "lte"}
    for operator, value in operators.items():
        if operator not in allowed:
            raise DetectionRuleLoadError("sequence stage predicate has unsupported operator")
        if operator == "in" and not isinstance(value, list):
            raise DetectionRuleLoadError("sequence stage predicate in operator must use an array")
        if operator == "exists" and not isinstance(value, bool):
            raise DetectionRuleLoadError("sequence stage predicate exists operator must be boolean")
        if operator in {"prefix", "suffix", "regex"}:
            if not isinstance(value, str):
                raise DetectionRuleLoadError("sequence stage predicate string operator is invalid")
            if operator == "regex" and len(value) > 256:
                raise DetectionRuleLoadError("sequence stage predicate regex operator is too long")


def _match_ordered(
    events: tuple[EventEnvelope, ...],
    stages: tuple[SequenceStage, ...],
    *,
    within_seconds: float | None,
) -> tuple[tuple[EventEnvelope, ...], ...]:
    matches: list[tuple[EventEnvelope, ...]] = []
    start_index = 0
    while start_index < len(events):
        matched: list[EventEnvelope] = []
        stage_index = 0
        last_index: int | None = None
        for index in range(start_index, len(events)):
            event = events[index]
            stage = stages[stage_index]
            if _event_matches_stage(event, stage):
                matched.append(event)
                stage_index += 1
                if stage_index == len(stages):
                    last_index = index
                    break
        if last_index is None:
            break
        if _within_window(matched, within_seconds):
            matches.append(tuple(matched))
        start_index = last_index + 1
    return tuple(matches)


def _match_unordered(
    events: tuple[EventEnvelope, ...],
    stages: tuple[SequenceStage, ...],
    *,
    within_seconds: float | None,
) -> tuple[tuple[EventEnvelope, ...], ...]:
    matched_events: list[EventEnvelope] = []
    remaining_events = list(events)
    for stage in stages:
        for event in tuple(remaining_events):
            if _event_matches_stage(event, stage):
                matched_events.append(event)
                remaining_events.remove(event)
                break
        else:
            return ()
    if not _within_window(matched_events, within_seconds):
        return ()
    return (tuple(matched_events),)


def _suppress_and_dedupe(
    *,
    matched_sequences: tuple[tuple[EventEnvelope, ...], ...],
    rule: SequenceRule,
    group_key: tuple[str, ...],
) -> tuple[tuple[EventEnvelope, ...], ...]:
    seen_event_sets: set[tuple[str, ...]] = set()
    last_emitted_by_key: dict[tuple[str, ...], datetime] = {}
    emitted: list[tuple[EventEnvelope, ...]] = []
    for matched_events in matched_sequences:
        event_ids = tuple(event.event_id for event in matched_events)
        if rule.deduplicate and event_ids in seen_event_sets:
            continue
        seen_event_sets.add(event_ids)
        suppression_key = _suppression_key(rule, group_key, matched_events)
        first_occurred_at = min(event.occurred_at for event in matched_events)
        last_emitted_at = last_emitted_by_key.get(suppression_key)
        if (
            rule.suppression_seconds is not None
            and last_emitted_at is not None
            and _seconds_between(last_emitted_at, first_occurred_at) <= rule.suppression_seconds
        ):
            continue
        last_emitted_by_key[suppression_key] = first_occurred_at
        emitted.append(matched_events)
    return tuple(emitted)


def _suppression_key(
    rule: SequenceRule,
    group_key: tuple[str, ...],
    matched_events: tuple[EventEnvelope, ...],
) -> tuple[str, ...]:
    if not rule.suppression_key:
        return group_key
    if not matched_events:
        return group_key
    event_object = event_to_dict(matched_events[0])
    return tuple(str(_path_value(event_object, path) or "") for path in rule.suppression_key)


def _event_matches_stage(event: EventEnvelope, stage: SequenceStage) -> bool:
    if event_type_value(event.event_type) != stage.event_type:
        return False
    event_object = event_to_dict(event)
    for path, expected in stage.where.items():
        actual = _path_value(event_object, path)
        if not _matches_expected(actual, expected):
            return False
    return True


def _group_events(
    events: tuple[EventEnvelope, ...],
    group_by: tuple[str, ...],
) -> dict[tuple[str, ...], tuple[EventEnvelope, ...]]:
    grouped: dict[tuple[str, ...], list[EventEnvelope]] = {}
    for event in events:
        event_object = event_to_dict(event)
        key = tuple(str(_path_value(event_object, path) or "") for path in group_by)
        grouped.setdefault(key, []).append(event)
    return {key: tuple(value) for key, value in grouped.items()}


def _matches_expected(actual: object, expected: object) -> bool:
    if isinstance(expected, dict):
        allowed = expected.get("in")
        if isinstance(allowed, list):
            return actual in allowed
        exists = expected.get("exists")
        if isinstance(exists, bool):
            return (actual is not None) is exists
        prefix = expected.get("prefix")
        if isinstance(prefix, str):
            return isinstance(actual, str) and actual.startswith(prefix)
        suffix = expected.get("suffix")
        if isinstance(suffix, str):
            return isinstance(actual, str) and actual.endswith(suffix)
        pattern = expected.get("regex")
        if isinstance(pattern, str):
            return _safe_regex_match(actual, pattern)
        not_expected = expected.get("not")
        if "not" in expected:
            if actual is None:
                return False
            return not _matches_expected(actual, not_expected)
        for operator, comparator in (("gt", _gt), ("gte", _gte), ("lt", _lt), ("lte", _lte)):
            threshold = expected.get(operator)
            if threshold is not None:
                return comparator(actual, threshold)
        return False
    return actual == expected


def _path_value(event_object: dict[str, Any], path: str) -> object:
    value = _get_path(event_object, path)
    if value is not None:
        return value
    return _get_path(event_object, f"payload.{path}")


def _get_path(value: object, path: str) -> object:
    current = value
    for part in path.split("."):
        if isinstance(current, dict):
            current = current.get(part)
            continue
        if isinstance(current, list) and part.isdecimal():
            index = int(part)
            if index >= len(current):
                return None
            current = current[index]
            continue
        else:
            return None
    return current


def _safe_regex_match(actual: object, pattern: str) -> bool:
    if not isinstance(actual, str) or len(pattern) > 256 or len(actual) > 4096:
        return False
    try:
        return re.search(pattern, actual) is not None
    except re.error:
        return False


def _within_window(events: list[EventEnvelope], within_seconds: float | None) -> bool:
    if within_seconds is None or len(events) < 2:
        return True
    occurred_at_values = [event.occurred_at for event in events]
    return _seconds_between(min(occurred_at_values), max(occurred_at_values)) <= within_seconds


def _seconds_between(start: datetime, end: datetime) -> float:
    return (end - start).total_seconds()


def _number(value: object) -> float | None:
    if isinstance(value, int | float):
        return float(value)
    return None


def _datetime_value(value: object) -> datetime | None:
    if not isinstance(value, str):
        return None
    normalized = value.removesuffix("Z") + "+00:00" if value.endswith("Z") else value
    try:
        return datetime.fromisoformat(normalized)
    except ValueError:
        return None


def _compare(actual: object, expected: object, operator: str) -> bool:
    actual_number = _number(actual)
    expected_number = _number(expected)
    if actual_number is not None and expected_number is not None:
        return _compare_numbers(actual_number, expected_number, operator)
    actual_datetime = _datetime_value(actual)
    expected_datetime = _datetime_value(expected)
    if actual_datetime is not None and expected_datetime is not None:
        return _compare_datetimes(actual_datetime, expected_datetime, operator)
    return False


def _compare_numbers(actual: float, expected: float, operator: str) -> bool:
    if operator == "gt":
        return actual > expected
    if operator == "gte":
        return actual >= expected
    if operator == "lt":
        return actual < expected
    if operator == "lte":
        return actual <= expected
    raise ValueError(f"unsupported comparison operator: {operator}")


def _compare_datetimes(actual: datetime, expected: datetime, operator: str) -> bool:
    if operator == "gt":
        return actual > expected
    if operator == "gte":
        return actual >= expected
    if operator == "lt":
        return actual < expected
    if operator == "lte":
        return actual <= expected
    raise ValueError(f"unsupported comparison operator: {operator}")


def _gt(actual: object, expected: object) -> bool:
    return _compare(actual, expected, "gt")


def _gte(actual: object, expected: object) -> bool:
    return _compare(actual, expected, "gte")


def _lt(actual: object, expected: object) -> bool:
    return _compare(actual, expected, "lt")


def _lte(actual: object, expected: object) -> bool:
    return _compare(actual, expected, "lte")
