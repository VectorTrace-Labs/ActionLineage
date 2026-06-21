# Lineage Contracts

Lineage Contracts define telemetry and evidence requirements as code.

## Purpose

A contract states what evidence must exist for a system or action to be supportable by detection and response. It is not runtime authorization and it is not a replacement for the event schema.

## Implemented contract dimensions

- Required event types.
- Required fields and nonempty values.
- Required causal relationships.
- Required evidence-link relationships.
- Required tool descriptor identity when descriptor data is available.
- Required verification status.
- Required journal integrity.
- Maximum event-observation latency in replay tests.
- Named threat cases that must have detection or response coverage.

The core parser accepts JSON Lineage Contract files using only the Python
standard library. YAML examples remain useful for design review, but JSON is the
portable public-alpha validation boundary unless an ADR promotes YAML support
into core.

## JSON example

```json
{
  "apiVersion": "actionlineage.dev/contract/v1",
  "kind": "LineageContract",
  "metadata": {
    "name": "outbound-http-evidence"
  },
  "spec": {
    "requirements": {
      "events": [
        {
          "type": "tool.execution.requested",
          "requiredFields": [
            "correlation.trace_id",
            "causality.parent_event_id",
            "payload.tool_identity.name",
            "payload.tool_identity.descriptor_hash"
          ]
        },
        {
          "type": "tool.execution.acknowledged",
          "requiredFields": ["payload.acknowledgement.status"]
        },
        {
          "type": "side_effect.verified",
          "requiredFields": [
            "payload.evidence_link.subject_event_id",
            "payload.evidence_link.evidence_event_id",
            "payload.evidence_link.verification_status"
          ]
        }
      ],
      "relationships": [
        {
          "child": "tool.execution.acknowledged",
          "parent": "tool.execution.dispatched"
        }
      ],
      "evidenceLinks": [
        {
          "eventType": "side_effect.verified",
          "subjectEventType": "tool.execution.acknowledged",
          "evidenceEventType": "side_effect.observed",
          "verificationStatus": "verified",
          "corroborationTypes": ["independent_observer", "fixture_oracle"]
        }
      ],
      "latency": [
        {
          "startEventType": "tool.execution.dispatched",
          "endEventType": "tool.execution.acknowledged",
          "maxSeconds": 5
        }
      ],
      "descriptors": [
        {
          "eventType": "tool.execution.requested"
        }
      ],
      "detections": [
        {
          "ruleId": "AL-DET-003",
          "required": true,
          "requiredEventTypes": ["side_effect.unverified"],
          "requiredVerificationStatuses": ["unverified"]
        }
      ],
      "verification": {
        "allowedStatuses": ["observed", "verified", "unverified", "timed_out", "conflicting"],
        "requiredStatus": "verified"
      },
      "integrity": {
        "hashChainRequired": true
      }
    }
  }
}
```

## Validator output

The validator reports:

- Contract and version.
- Exact event or field that failed.
- Whether the failure makes attribution, detection, containment, verification, or audit impossible.
- A remediation hint.
- Machine-readable JSON for CI annotations.

## CLI

```bash
uv run actionlineage contract init contracts/local.json --name local-evidence
uv run actionlineage contract explain contracts/local.json
uv run actionlineage contract validate contracts/local.json build/actionlineage-demo/evidence.jsonl
uv run actionlineage contract test contracts/local.json build/actionlineage-demo/evidence.jsonl --format annotations
```

`validate` prints a result and exits successfully even when the contract fails.
`test` is intended for CI and exits nonzero when violations are present.

Built-in sequence detections are evaluated by default for detection coverage
requirements. Use `--no-built-in-detections` when validating only telemetry shape
and evidence quality.

## Failure semantics

Contracts validate whether the evidence is sufficient for a named control or
detection. They do not authorize tool execution. A passing contract does not
prove a side effect happened; it means the required telemetry and corroboration
records exist and match the contract.

Absence of an observation is reported as missing telemetry or missing evidence,
not as proof that no side effect occurred.

## Spin-out criteria

Publish Lineage Contracts separately only when a user wants to validate non-ActionLineage telemetry or the contract language gains an independent ecosystem.
