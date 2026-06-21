# Detection Engine and Lineage Lab

Lineage Lab consolidates evidence-quality mutation testing and detection robustness checks without forcing separate repositories.

## Detection engine boundary

The detection engine consumes normalized persisted events and emits alerts. It does not decide whether an action may execute; synchronous enforcement belongs to optional policy adapters.

Detections must distinguish:

- Requested action.
- Authorized action.
- Dispatched action.
- Acknowledged tool response.
- Observed side effect.
- Verified, unverified, timed-out, or conflicting outcome.

## Implemented sequence rule shape

The in-process rule model is intentionally bounded. It supports versioned
metadata, severity, tags, rationale, references, required evidence quality,
grouping, ordered or unordered stages, explicit time windows, duplicate
suppression, and deterministic alert export with event evidence references.

Supported field predicates are:

- Equality.
- `in` set membership.
- `exists` for explicit missing-field checks.
- `prefix` and `suffix` for bounded string matching.
- `regex` with a small pattern and input-size limit.
- `gt`, `gte`, `lt`, and `lte` for numeric and ISO timestamp comparisons.
- `not`, which does not match missing fields unless `exists: false` is used.

The built-in starter pack is exposed as `built_in_sequence_rules()` and covers:

- Restricted read followed by verified side-effect evidence.
- Descriptor drift before sensitive action.
- Acknowledged high-risk action that remains unobserved or timed out.
- Conflicting observer evidence.
- Policy denial or failure before a not-dispatched tool execution.

The rule engine consumes persisted normalized events and emits matches. It does
not perform synchronous enforcement or treat a tool acknowledgement as
side-effect proof.

## Rule-pack loading

`load_sequence_rules(path)` loads JSON rule packs from the core install and YAML
rule packs when `PyYAML` is present through the adapter extra. The loader
accepts either the direct Python model shape used by `sequence_rule_to_dict()`
or the package shape below. Validation errors identify the field that failed
without echoing rule payload values.

Direct JSON shape:

```json
{
  "rules": [
    {
      "name": "verified-file-read",
      "group_by": ["correlation.run_id"],
      "stages": [
        {
          "event_type": "tool.execution.acknowledged",
          "where": {"tool_identity.name": "safe_files.read"}
        },
        {
          "event_type": "side_effect.verified",
          "where": {"evidence_link.verification_status": "verified"}
        }
      ]
    }
  ]
}
```

YAML package shape:

```yaml
apiVersion: actionlineage.dev/v1alpha1
kind: SequenceDetection
metadata:
  name: restricted-read-followed-by-verified-untrusted-send
spec:
  groupBy:
    - correlation.run_id
  within: 2m
  ordered: true
  stages:
    - eventType: action.normalized
      where:
        action.type: data.read
        resource.sensitivity:
          in: [restricted, secret]
    - eventType: tool.execution.acknowledged
      where:
        tool_identity.name: safe_http.send
    - eventType: side_effect.verified
      where:
        evidence_link.verification_status: verified
  severity: high
  rationale: Detect a restricted-data flow only when side-effect evidence is verified.
```

Durations in package fields such as `within` may use seconds by default or
explicit `ms`, `s`, `m`, and `h` suffixes. Package fields such as `eventType`,
`groupBy`, `requiredEvidenceQuality`, `withinSeconds`, and `suppressionKey` map
to the snake_case Python model. The loader preserves the bounded expression
semantics listed above; unknown predicate operators are rejected rather than
silently creating dead rules.

## Rule debugging

Use `explain_sequence_rule(events, rule)` or the CLI to understand why a rule did
or did not match:

```bash
uv run actionlineage detection explain-sequence rules.json evidence.jsonl
```

The explanation reports each group key, stage name, stage event type, candidate
event IDs, and final match evidence. It intentionally does not print event
payloads, so analysts can debug ordering, grouping, and missing-stage problems
without creating a new evidence sink for sensitive fields.

## Rule review checklist

- Every rule has a stable name, owner-reviewed rationale, severity, and
  evidence-quality requirement when side-effect proof is claimed.
- Stages refer to requested, authorized, dispatched, acknowledged, observed,
  verified, unverified, timed-out, conflicting, or not-dispatched facts
  explicitly; a tool acknowledgement is never used as side-effect proof.
- Field predicates avoid broad regular expressions and include `exists` checks
  where missing data has security meaning.
- Positive, benign, ambiguous, duplicate, out-of-order, timeout, and performance
  fixtures cover the rule before it is treated as release-ready.
- Alerts cite the exact event evidence for every satisfied stage.

## Semantics-preserving mutations

Lineage Lab can now vary replay cases deterministically. Each mutation declares
the semantic property it claims to preserve or, for uncertainty mutations, the
expected outcome change it intentionally introduces.

Implemented strategies:

- Add benign distractor events.
- Duplicate one event as an arrival artifact.
- Reorder unrelated arrival order.
- Add bounded observed-time skew.
- Remove an optional acknowledgement field.
- Add path and URL normalization representation variants.
- Replace a verified outcome with unverified evidence when testing uncertainty.

Future strategies should cover casing variants, aliases, split payloads, and
larger benign distractor corpora.

## Scorecard

- Detection survival rate.
- Failed cases.
- False-positive and false-negative case names.
- Evidence completeness for expected-positive cases.
- Evaluation latency.
- Required-field fragility.

`minimize_counterexample()` removes irrelevant events while preserving a failing
result, and `write_minimized_counterexample()` writes a reviewed JSON fixture.
This is intentionally deterministic rather than a general-purpose fuzzer.

## Prerequisites

Do not add property-based fuzzing until:

- At least two real detections exist.
- Positive and benign fixtures are reviewed.
- Event compatibility behavior is documented.
- A deterministic replay API exists.

## Spin-out criteria

Consider a separate Lineage Lab repository when it can test multiple external agent telemetry formats or becomes useful to teams that do not run ActionLineage.
