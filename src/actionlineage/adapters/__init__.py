"""Optional protocol, policy, and telemetry adapters."""

from actionlineage.adapters.frameworks import (
    FrameworkAcknowledgementStatus,
    FrameworkKind,
    FrameworkToolDescriptor,
    FrameworkToolInvocation,
    framework_descriptor_hash,
    framework_descriptor_payload,
    framework_lifecycle_records,
    framework_tool_identity,
)
from actionlineage.adapters.policy import (
    ApprovalArtifact,
    ApprovalReplayCache,
    ApprovalStatus,
    ApprovalValidationResult,
    PolicyDecision,
    PolicyDecisionOutcome,
    PolicyFailureMode,
    RiskClass,
)

__all__ = [
    "ApprovalArtifact",
    "ApprovalReplayCache",
    "ApprovalStatus",
    "ApprovalValidationResult",
    "FrameworkAcknowledgementStatus",
    "FrameworkKind",
    "FrameworkToolDescriptor",
    "FrameworkToolInvocation",
    "PolicyDecision",
    "PolicyDecisionOutcome",
    "PolicyFailureMode",
    "RiskClass",
    "framework_descriptor_hash",
    "framework_descriptor_payload",
    "framework_lifecycle_records",
    "framework_tool_identity",
]
