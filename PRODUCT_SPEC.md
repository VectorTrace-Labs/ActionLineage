# Product Specification

## 1. Scope

This specification defines the first public release of ActionLineage as a vendor-neutral evidence and detection plane for tool-using agents.

## 2. Terminology

- **Run**: one bounded agent execution initiated by a human, service, or scheduler.
- **Intent**: the initiating request or goal that caused an agent run.
- **Principal**: a human, service, agent, model, workload, or delegated identity.
- **Tool descriptor**: a transport-provided or locally configured tool definition, including name, description, schemas, annotations, and metadata.
- **Tool execution**: one requested invocation of a tool with a normalized argument set.
- **Acknowledgement**: a tool or adapter response indicating the request completed or failed from that component's perspective.
- **Observation**: independently recorded evidence that a resource or environment state changed or was inspected.
- **Verification**: an explicit evidence link that corroborates, contradicts, limits, or qualifies a subject event.
- **Action**: a normalized security-relevant operation or side effect.
- **Resource**: the target or source involved in an action, such as a file, URL, process, account, cloud object, or message.
- **Policy decision**: an optional adapter decision to allow, deny, require approval, or observe without enforcement.
- **Lineage event**: an immutable, versioned record in the causal chain.
- **Contract**: machine-readable requirements for fields, relationships, latency, integrity, and expected detections.
- **Scenario**: a deterministic event-producing workflow with ground truth.

## 3. Functional requirements

### FR-001: Typed event model

The system shall produce versioned events with stable IDs, timestamps, source component, event type, principal, trace/run correlation, causal parent, data classification, payload, and integrity metadata.

### FR-002: Evidence lifecycle

The system shall represent requested, authorized, dispatched, acknowledged, observed, verified, unverified, timed-out, conflicting, and unknown outcomes as separate states. A successful tool response shall not be treated as proof that a side effect occurred.

### FR-003: Evidence links

Verification events shall identify the subject event, corroborating evidence event, relationship, observer identity, corroboration type, confidence, status, and limitations. Verification requires independent or explicitly identified corroborating evidence.

### FR-004: Tool identity

Tool identity shall include a stable descriptor hash when descriptor data is available. Descriptor hashing is transport-neutral; MCP descriptors are one optional adapter source.

### FR-005: Optional policy interface

Adapters may evaluate policy before dispatch. Policy decisions shall be explicit, versioned, attributable, and recorded. A denied call shall not be forwarded by an enforcing adapter, and policy failure shall never be silently converted to allow.

### FR-006: Redaction

The system shall apply structured redaction before persistence, export, tracing, logging, or error serialization. Raw authorization headers, bearer tokens, API keys, private keys, passwords, and configured sensitive fields shall not be stored by default.

### FR-007: Journal

The system shall write events to an append-only local journal. Each persisted event shall include the previous event hash and its own canonical event hash. Verification shall detect mutation, insertion, deletion, and reordering when trusted anchors make those changes observable.

The documentation must state that a local hash chain is not sufficient to resist an attacker who can rewrite both the journal and its root anchor.

### FR-008: Query and export

The CLI/API shall return a chronologically ordered lineage timeline by trace ID or run ID and support a machine-readable incident export. Timeline output shall expose verification status and evidence-link identifiers when present.

### FR-009: Deterministic demo

The repository shall include a deterministic local demo that records intent, tool execution states, delegated identity, independent observations, and verification outcomes. The demo must work without a model API key, cloud account, or internet access.

### FR-010: Optional telemetry adapters

Telemetry exporters such as OpenTelemetry may mirror evidence events, but they are not canonical evidence stores. Exporter failure must not erase or replace local journal records.

## 4. Lineage Contracts

Contracts shall validate:

- Required event types and verification states.
- Required fields and evidence-link relationships.
- Required causal parents.
- Required journal integrity.
- Maximum ingest latency in fixture/replay tests.
- Required detection or response coverage for named threat cases.

Contract validation shall run in CI against event fixtures and demo outputs.

## 5. Detection engine and Lineage Lab

The detection engine shall support ordered, bounded-time sequence rules over normalized events.

Lineage Lab shall:

- Replay deterministic scenarios.
- Apply semantics-preserving event mutations.
- Measure rule survival rate, evidence completeness, latency, and false positives against benign fixtures.
- Save minimized counterexamples with reproducible seeds.

## 6. Nonfunctional requirements

- Python 3.13 or newer.
- Strong typing at public interfaces.
- Deterministic serialization and tests.
- No required external service for the default demo.
- A fresh clone can be set up using `uv` and documented commands.
- Public APIs are documented and versioned.
- Security-sensitive behavior is covered by positive and negative tests.
- Logs are structured and do not duplicate secrets removed from events.
- Core packages do not import optional adapter dependencies.

## 7. Release gate

A milestone is not complete until:

- Acceptance tests pass.
- Threat model changes are documented.
- New dependencies are justified or placed behind extras.
- Public behavior is documented.
- Failure and rollback behavior is tested.
- No test bypass or weakened security invariant was introduced merely to make CI pass.

## 8. Public release status

Current release status and future work are maintained in `docs/ROADMAP.md`.
Executable release gates are maintained in `ACCEPTANCE_TESTS.md` and
`docs/RELEASE_CHECKLIST.md`.
