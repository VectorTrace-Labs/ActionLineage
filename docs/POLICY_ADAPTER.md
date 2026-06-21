# Policy Adapter Semantics

Policy enforcement is optional. When present, policy adapters translate decisions
into evidence rather than changing the domain event model.

## Outcomes

- `allow`: dispatch is permitted.
- `deny`: dispatch is not permitted.
- `require_approval`: dispatch requires a valid approval artifact.
- `dry_run`: dispatch is permitted and the policy result remains evidence.
- `error`: dispatch depends on explicit failure behavior.

## Failure Behavior

- `fail_closed`: do not dispatch.
- `fail_open`: dispatch may proceed, but degraded evidence must be emitted.

Fail-open is not equivalent to allow. Investigation exports and contracts should
treat degraded evidence as a limitation.

## Approvals

Approval artifacts bind:

- Subject event ID.
- Scope.
- Expiry.
- Nonce.
- Approver.
- Optional policy decision event ID.

Adapter runtimes reject reused nonces. Approval artifacts authorize dispatch
only for the matching subject, scope, and time window.

## Evidence Claims

A policy decision can explain why a tool call was or was not dispatched. It does
not prove that a side effect occurred. Side-effect verification still requires
independent or explicitly identified corroborating evidence.
