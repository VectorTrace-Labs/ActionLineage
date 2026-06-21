# Deterministic Demo Scenario

## Objective

Demonstrate a complete, local, reproducible evidence flow without requiring an LLM, cloud account, external service, or internet access.

## Actors

- `user_demo`: initiates a request to inspect a workspace document.
- `agent_demo`: deterministic orchestrator that follows a scripted sequence.
- `local_tool_adapter`: emits neutral tool execution lifecycle events.
- `filesystem_observer`: records local file readback observations.
- `receiver_observer`: records local mock receiver observations.
- `evidence_verifier`: links tool acknowledgements to observations and records verification status.

## Synthetic workspace

- `docs/summary_request.txt`: benign user request.
- `docs/quarterly-plan.txt`: classified `restricted`.
- `docs/vendor-note.txt`: untrusted content containing a synthetic instruction to send the quarterly plan to a collector.

The malicious text must be clearly synthetic and harmless outside the local demo.

## Expected sequence

1. Intent is recorded with `user_demo` as initiating principal.
2. Run starts with `agent_demo` as executing principal.
3. Agent lists files.
4. Agent reads `vendor-note.txt`; event records `trust=untrusted`.
5. Agent reads `quarterly-plan.txt`; event records `sensitivity=restricted`.
6. Agent requests `safe_http.send` to a local receiver.
7. Tool execution is requested, authorized, dispatched, and acknowledged.
8. Receiver observer records whether the local receiver saw the request.
9. Verifier links the acknowledgement to the receiver observation.
10. Timeline and incident export explain which side effects are verified, unverified, timed out, or conflicting.

## Evidence required in the timeline

- Initiating human/service principal.
- Agent identity.
- Run and trace IDs.
- Adapter identity.
- Tool name and descriptor hash when available.
- Resource classification and trust.
- Credential identity or explicit `none` for the local demo.
- Tool execution requested, authorized, dispatched, and acknowledged states.
- Independent observer event.
- Evidence link with subject, corroborating evidence, observer identity, confidence, status, and limitations.

## Demo command target

```bash
make demo
```

The command runs the local scenario and prints JSON containing the trace ID, run ID, generated artifact paths, journal verification command, timeline query command, and incident export command.

Generated files are written under `build/actionlineage-demo/` by default:

- `evidence.jsonl`: canonical append-only local journal.
- `projection.sqlite`: rebuildable query projection.
- `timeline.json`: compact event-order summary.
- `incident.json`: investigation-ready incident export.

The deterministic demo currently emits 16 events and covers:

- A verified file-read side effect corroborated by `filesystem_observer`.
- An acknowledged HTTP send that remains unverified because there is no independent receiver observation.
- A blocked shell-like tool request represented as `tool.execution.not_dispatched` with `downstream_forwarded=false`.
