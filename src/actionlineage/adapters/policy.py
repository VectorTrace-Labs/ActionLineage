"""Optional policy adapter primitives.

Policy enforcement is an adapter concern. These value objects describe decisions
and approvals without coupling the evidence core to a policy engine.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum


class PolicyDecisionOutcome(StrEnum):
    """Policy outcomes understood by optional adapters."""

    ALLOW = "allow"
    DENY = "deny"
    REQUIRE_APPROVAL = "require_approval"
    DRY_RUN = "dry_run"
    ERROR = "error"


class PolicyFailureMode(StrEnum):
    """Fail behavior when policy evaluation degrades."""

    FAIL_OPEN = "fail_open"
    FAIL_CLOSED = "fail_closed"


class RiskClass(StrEnum):
    """Risk class used to choose fail behavior."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class ApprovalStatus(StrEnum):
    """Approval validation outcome."""

    ACCEPTED = "accepted"
    REJECTED = "rejected"


@dataclass(frozen=True, slots=True)
class PolicyDecision:
    """One attributable policy decision."""

    outcome: PolicyDecisionOutcome
    policy_id: str
    policy_version: str
    reason: str
    risk_class: RiskClass = RiskClass.MEDIUM
    evaluator_identity: str = "policy-adapter"
    decision_id: str | None = None

    def dispatch_allowed(
        self,
        *,
        failure_mode: PolicyFailureMode = PolicyFailureMode.FAIL_CLOSED,
        approval_accepted: bool = False,
    ) -> bool:
        """Return whether an adapter may dispatch after this decision."""

        if self.outcome in {PolicyDecisionOutcome.ALLOW, PolicyDecisionOutcome.DRY_RUN}:
            return True
        if self.outcome == PolicyDecisionOutcome.REQUIRE_APPROVAL:
            return approval_accepted
        if self.outcome == PolicyDecisionOutcome.ERROR:
            return failure_mode == PolicyFailureMode.FAIL_OPEN
        return False

    def as_payload(self) -> dict[str, object]:
        """Return a JSON-compatible policy payload."""

        return {
            "outcome": self.outcome.value,
            "policy_id": self.policy_id,
            "policy_version": self.policy_version,
            "reason": self.reason,
            "risk_class": self.risk_class.value,
            "evaluator_identity": self.evaluator_identity,
            "decision_id": self.decision_id,
        }


@dataclass(frozen=True, slots=True)
class ApprovalArtifact:
    """Replay-resistant approval evidence."""

    approval_id: str
    subject_event_id: str
    scope: str
    expires_at: datetime
    nonce: str
    approved_by: str
    decision_event_id: str | None = None

    def is_valid_for(self, *, now: datetime, subject_event_id: str, scope: str) -> bool:
        """Return whether this approval is valid for a request at a point in time."""

        now = now.astimezone(UTC)
        return (
            self.subject_event_id == subject_event_id
            and self.scope == scope
            and self.expires_at.astimezone(UTC) >= now
        )

    def as_payload(self) -> dict[str, object]:
        """Return a JSON-compatible approval payload."""

        return {
            "approval_id": self.approval_id,
            "subject_event_id": self.subject_event_id,
            "scope": self.scope,
            "expires_at": self.expires_at.astimezone(UTC).isoformat().replace("+00:00", "Z"),
            "nonce": self.nonce,
            "approved_by": self.approved_by,
            "decision_event_id": self.decision_event_id,
        }


@dataclass(frozen=True, slots=True)
class ApprovalValidationResult:
    """Result of validating an approval artifact."""

    status: ApprovalStatus
    reason: str
    approval_id: str | None = None

    @property
    def accepted(self) -> bool:
        return self.status == ApprovalStatus.ACCEPTED

    def as_payload(self) -> dict[str, object]:
        return {
            "status": self.status.value,
            "reason": self.reason,
            "approval_id": self.approval_id,
        }


@dataclass(slots=True)
class ApprovalReplayCache:
    """In-memory nonce cache for adapter tests and local runtimes."""

    used_nonces: set[str]

    @classmethod
    def empty(cls) -> ApprovalReplayCache:
        return cls(used_nonces=set())

    def claim(
        self,
        artifact: ApprovalArtifact,
        *,
        now: datetime,
        subject_event_id: str,
        scope: str,
    ) -> ApprovalValidationResult:
        """Validate and consume an approval nonce exactly once."""

        if artifact.nonce in self.used_nonces:
            return ApprovalValidationResult(
                status=ApprovalStatus.REJECTED,
                reason="approval nonce was already used",
                approval_id=artifact.approval_id,
            )
        if not artifact.is_valid_for(now=now, subject_event_id=subject_event_id, scope=scope):
            return ApprovalValidationResult(
                status=ApprovalStatus.REJECTED,
                reason="approval scope, subject, or expiry is invalid",
                approval_id=artifact.approval_id,
            )
        self.used_nonces.add(artifact.nonce)
        return ApprovalValidationResult(
            status=ApprovalStatus.ACCEPTED,
            reason="approval accepted",
            approval_id=artifact.approval_id,
        )
