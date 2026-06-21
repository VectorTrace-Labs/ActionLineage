"""Sequence detections over normalized lineage events."""

from actionlineage.detection.rules import built_in_sequence_rules
from actionlineage.detection.sequence import (
    DetectionMatch,
    DetectionRuleLoadError,
    GroupExplanation,
    RuleExplanation,
    SequenceRule,
    SequenceStage,
    StageExplanation,
    evaluate_sequence_rule,
    explain_sequence_rule,
    load_sequence_rules,
    sequence_rule_from_dict,
    sequence_rule_to_dict,
)

__all__ = [
    "DetectionMatch",
    "DetectionRuleLoadError",
    "GroupExplanation",
    "RuleExplanation",
    "SequenceRule",
    "SequenceStage",
    "StageExplanation",
    "built_in_sequence_rules",
    "evaluate_sequence_rule",
    "explain_sequence_rule",
    "load_sequence_rules",
    "sequence_rule_from_dict",
    "sequence_rule_to_dict",
]
