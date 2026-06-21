"""Built-in starter detection rules."""

from __future__ import annotations

from actionlineage.detection.sequence import SequenceRule, SequenceStage


def built_in_sequence_rules() -> tuple[SequenceRule, ...]:
    """Return reviewed starter rules for evidence-plane demos and smoke tests."""

    return (
        SequenceRule(
            rule_id="AL-DET-001",
            name="restricted-read-followed-by-verified-untrusted-send",
            version="1",
            severity="high",
            tags=("exfiltration", "verified-side-effect"),
            rationale="Restricted reads followed by verified untrusted sends need review.",
            required_evidence_quality=("verified",),
            stages=(
                SequenceStage(
                    event_type="action.normalized",
                    where={"action.resources.0.attributes.sensitivity": "restricted"},
                    name="restricted-read",
                ),
                SequenceStage(
                    event_type="side_effect.verified",
                    where={"evidence_link.verification_status": "verified"},
                    name="verified-send",
                ),
            ),
        ),
        SequenceRule(
            rule_id="AL-DET-002",
            name="descriptor-drift-before-sensitive-action",
            version="1",
            severity="medium",
            tags=("descriptor-drift", "tool-identity"),
            rationale="Descriptor drift before sensitive actions can invalidate prior review.",
            stages=(
                SequenceStage(event_type="agent.tool.schema_changed", where={}),
                SequenceStage(event_type="action.normalized", where={}),
            ),
        ),
        SequenceRule(
            rule_id="AL-DET-003",
            name="acknowledged-high-risk-action-not-observed",
            version="1",
            severity="medium",
            tags=("unverified", "side-effect"),
            rationale="Acknowledged high-risk actions without observations remain unverified.",
            stages=(
                SequenceStage(
                    event_type="tool.execution.acknowledged",
                    where={
                        "tool_identity.name": "safe_http.send",
                        "acknowledgement.status": {"in": ["success", "succeeded"]},
                    },
                ),
                SequenceStage(
                    event_type="side_effect.unverified",
                    where={
                        "evidence_link.verification_status": {"in": ["unverified", "timed_out"]}
                    },
                ),
            ),
        ),
        SequenceRule(
            rule_id="AL-DET-004",
            name="conflicting-observer-evidence",
            version="1",
            severity="high",
            tags=("conflict", "observer"),
            rationale="Conflicting side-effect evidence should be triaged explicitly.",
            stages=(SequenceStage(event_type="side_effect.conflict_detected", where={}),),
        ),
        SequenceRule(
            rule_id="AL-DET-005",
            name="policy-failure-before-dispatch",
            version="1",
            severity="high",
            tags=("policy", "dispatch"),
            rationale="Policy failures before dispatch require explicit fail behavior.",
            stages=(
                SequenceStage(
                    event_type="policy.decision",
                    where={"outcome": {"in": ["deny", "error"]}},
                ),
                SequenceStage(
                    event_type="tool.execution.not_dispatched",
                    where={"not_dispatched.downstream_forwarded": False},
                ),
            ),
        ),
    )
