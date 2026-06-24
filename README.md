# ActionLineage

**Know what the agent did, and show what changed.**

ActionLineage is an alpha-stage, vendor-neutral evidence and detection plane for
tool-using agents. It correlates agent intent, delegated identity, tool
execution, and independently observed side effects into investigation-ready
local evidence.

The central rule is simple: a successful tool response is an acknowledgement,
not proof of a side effect. ActionLineage records requested, authorized,
dispatched, acknowledged, observed, verified, unverified, timed-out,
conflicting, and not-dispatched outcomes as separate facts.

## Current Maturity

This repository is a public alpha. Core evidence recording is usable for local
evaluation and fixture-backed integration work, but service deployments,
external adapters, cloud observers, GHCR containers, package-index ownership
transfer, and additional package-manager channels are preview, planned, or
external-validation surfaces until they are externally validated.

| Surface | Maturity | Evidence |
| --- | --- | --- |
| Event envelope, redaction, local journal, SQLite projection | Alpha-supported | Unit, compatibility, projection, and security tests |
| Deterministic verified/unverified/conflicting/not-dispatched demo | Alpha-supported | `make demo`, demo tests, contract validation |
| Case export, graph export, grounded summary, static console | Alpha-supported | Projection and console tests |
| Lineage Contracts, sequence detections, Lineage Lab | Local-proof | Contract, detection, and replay tests |
| Agent Validation Lab | Local-proof | Development-only eval group, scenario fixtures, no-model CI lanes |
| MCP, policy, OpenTelemetry, service, Postgres, cloud/Kubernetes fixtures | Preview | Optional extras and local fixture tests |
| GitHub release artifacts and attestations | Alpha-supported / External-validation-required | `v0.1.0a5` GitHub Release is published with 13 release assets; `0.1.0a6` is the next prepared hardening release |
| PyPI/TestPyPI package publication | Alpha-supported | PyPI latest is `0.1.0a5`; `0.1.0a6` is prepared but not published until owner approval |
| GHCR container publication | Preview / external-validation-required | Anonymous GHCR registry and GitHub package checks did not expose a public image on 2026-06-23; release workflow prepares digest capture, signing, and attestations after publication |
| Homebrew tap, external audits, production history | Planned or external-validation-required | External validation has not been completed; Homebrew remains planned |

Full claim mapping lives in
[docs/QUALITY_SCORECARD.md](docs/QUALITY_SCORECARD.md).

## Five-Minute PyPI Evaluation

Prerequisites:

- Python 3.12, 3.13, or 3.14
- `uv`

Run the public-alpha package from PyPI after the owner-approved `0.1.0a6`
publication. Because `0.1.0a6` is a prerelease, `uvx` needs an explicit
prerelease flag:

```bash
uvx --prerelease allow --from actionlineage==0.1.0a6 actionlineage version
uvx --prerelease allow --from actionlineage==0.1.0a6 actionlineage demo run --output-dir /tmp/actionlineage-demo
uvx --prerelease allow --from actionlineage==0.1.0a6 actionlineage journal verify /tmp/actionlineage-demo/evidence.jsonl
```

The demo requires no model API key, cloud account, or external service. The
PyPI path needs internet access to install the package; the demo itself is
deterministic and local after installation.

The demo writes artifacts under `/tmp/actionlineage-demo/`:

- `evidence.jsonl`: canonical append-only local journal.
- `projection.sqlite`: rebuildable query projection.
- `timeline.json`: compact event-order summary.
- `incident.json`: machine-readable incident export.

If you cloned the repository for development, install the full local test
environment and run the same demo through the checkout:

```bash
uv sync --locked --all-extras
make demo
```

Repository demo artifacts are written under `build/actionlineage-demo/`.
To generate a deterministic SVG overview from those demo artifacts, run:

```bash
make demo-map
```

That writes `build/actionlineage-demo/demo-evidence-map.svg` and
`build/actionlineage-demo/demo-evidence-map.json`. The SVG is an onboarding aid
derived from `incident.json`; the canonical evidence remains `evidence.jsonl`.

Inspect repository-generated evidence:

```bash
uv run actionlineage journal verify build/actionlineage-demo/evidence.jsonl

uv run actionlineage projection timeline \
  build/actionlineage-demo/projection.sqlite \
  --journal-path build/actionlineage-demo/evidence.jsonl \
  --trace-id trace_demo_evidence_plane

uv run actionlineage projection summarize \
  build/actionlineage-demo/projection.sqlite \
  --journal-path build/actionlineage-demo/evidence.jsonl \
  --trace-id trace_demo_evidence_plane

uv run actionlineage projection export-case \
  build/actionlineage-demo/projection.sqlite \
  build/actionlineage-demo/case \
  --journal-path build/actionlineage-demo/evidence.jsonl \
  --trace-id trace_demo_evidence_plane

uv run actionlineage projection export-console \
  build/actionlineage-demo/projection.sqlite \
  build/actionlineage-demo/console.html \
  --journal-path build/actionlineage-demo/evidence.jsonl \
  --trace-id trace_demo_evidence_plane

uv run python scripts/generate_demo_evidence_map.py \
  --demo-dir build/actionlineage-demo \
  --check

uv run actionlineage contract validate \
  contracts/examples/outbound-http.json \
  build/actionlineage-demo/evidence.jsonl
```

Open `build/actionlineage-demo/console.html` in a browser to review the static
timeline, event details, graph, verification matrix, and case context.

The stricter `contracts/examples/restricted-exfiltration.json` contract is a
design example for detection coverage; it is not the five-minute demo contract.

## What The Demo Shows

The default scenario emits a deterministic local journal that includes:

- a recorded human intent and agent run;
- a verified file-read side effect corroborated by a local filesystem observer;
- an acknowledged HTTP send that remains unverified because acknowledgement is
  not side-effect evidence;
- a conflicting receiver observation represented as
  `side_effect.conflict_detected`;
- a policy-denied shell-like request represented as
  `tool.execution.not_dispatched` with `downstream_forwarded=false`.

## Evidence Lifecycle

| State | Meaning |
| --- | --- |
| `agent.intent.recorded` | A human, service, scheduler, or agent initiated a run. |
| `tool.execution.requested` | An agent or adapter requested a tool invocation. |
| `tool.execution.authorized` | An optional policy or approval path allowed the request. |
| `tool.execution.dispatched` | The request crossed the tool boundary. |
| `tool.execution.acknowledged` | The tool or adapter returned a response. |
| `side_effect.observed` | A named observer recorded resource or environment evidence. |
| `side_effect.verified` | Corroborating evidence supports the subject event. |
| `side_effect.unverified` | Evidence is insufficient or only self-reported. |
| `side_effect.timed_out` | Observation or verification did not complete in time. |
| `side_effect.conflict_detected` | Evidence sources disagree and both sides are retained. |
| `tool.execution.not_dispatched` | A request was blocked, denied, or not sent downstream. |

Verification requires independent or explicitly identified corroborating
evidence. Missing observations are reported as missing observations only.

## Architecture

```mermaid
flowchart LR
    Client["Agent / client"] --> Adapter["Optional adapter"]
    Adapter --> Journal["Append-only local journal"]
    Adapter --> Tool["Tool runtime"]
    Tool --> Adapter
    Observer["Observer adapters"] --> Journal
    Verifier["Verification helpers"] --> Journal
    Journal --> Projection["Rebuildable projection"]
    Projection --> Timeline["Timeline, export, console"]
    Journal --> Contracts["Lineage Contracts"]
    Journal --> Lab["Lineage Lab"]
    Journal --> Exporters["Optional exporters"]
```

Core packages do not import MCP, OpenTelemetry, model-provider SDKs, FastAPI, or
cloud SDKs. Those surfaces live behind optional adapter or service boundaries.

## Agent Validation Lab

The Agent Validation Lab is a development-only evaluation surface for testing
tool-using agents against ActionLineage evidence requirements. It lives under
`evals/`, is not packaged as an ActionLineage runtime dependency, and does not
change the `v1alpha1` event schema.

It provides scenario fixtures, no-model replay, scorer output, provenance,
artifact audits, Docker-backed local receiver scenarios, and optional scheduled
live-model lanes for maintainers. Pull-request validation remains secret-free
and no model response is treated as authoritative product evidence.

Run the deterministic no-model lab locally from a repository checkout:

```bash
PYTHONPATH=evals uv run --group eval python -m actionlineage_evals validate-scenarios
PYTHONPATH=evals uv run --group eval python -m actionlineage_evals coverage --strict
PYTHONPATH=evals uv run --group eval python -m actionlineage_evals run \
  --scenario-path evals/scenarios \
  --artifact-root build/evals/local \
  --mode scripted \
  --model-adapter scripted
PYTHONPATH=evals uv run --group eval python -m actionlineage_evals summarize \
  build/evals/local \
  --format markdown
```

See [evals/README.md](evals/README.md),
[docs/AGENT_VALIDATION_EVIDENCE.md](docs/AGENT_VALIDATION_EVIDENCE.md),
[docs/AGENT_VALIDATION_ARCHITECTURE.md](docs/AGENT_VALIDATION_ARCHITECTURE.md),
[docs/AGENT_VALIDATION_THREAT_MODEL.md](docs/AGENT_VALIDATION_THREAT_MODEL.md),
and [docs/AGENT_VALIDATION_PLAN.md](docs/AGENT_VALIDATION_PLAN.md).

## How This Differs

| Tooling category | Main focus | ActionLineage difference |
| --- | --- | --- |
| Distributed tracing | Request flow and latency | Adds evidence status, side-effect verification, and investigation exports |
| Agent gateway | Mediation or policy enforcement | Treats enforcement as optional adapter behavior |
| Guardrail | Preventing or blocking actions | Preserves evidence, uncertainty, and conflicts even when no block occurs |
| SIEM/logging | Event collection and search | Adds causal evidence links and telemetry contract validation |

## Python API Example

```python
from datetime import UTC, datetime
from pathlib import Path

from actionlineage import (
    Classification,
    Correlation,
    EvidenceNormalizer,
    EvidenceRecord,
    EvidenceSourceKind,
    EventType,
    FixedClock,
    FixedIdGenerator,
    LocalJournal,
    NormalizedAction,
    NormalizedResource,
    Principal,
    PrincipalType,
    ResourceType,
    Sensitivity,
    Source,
    ToolIdentity,
    import_evidence_batch,
    verify_journal,
)

journal_path = Path("build/example/evidence.jsonl")
journal = LocalJournal(journal_path)
normalizer = EvidenceNormalizer(
    correlation=Correlation(trace_id="trace_example", run_id="run_example"),
    source=Source(component="example_adapter", instance_id="local", version="0.1.0a6"),
    principal=Principal(principal_id="agent_example", principal_type=PrincipalType.AGENT),
    classification=Classification(sensitivity=Sensitivity.INTERNAL),
    clock=FixedClock(datetime(2026, 1, 1, tzinfo=UTC)),
    id_generator=FixedIdGenerator(("evt_example_001", "evt_example_002")),
)

intent = EvidenceRecord(
    idempotency_key="example-intent-001",
    source_kind=EvidenceSourceKind.LOCAL_FUNCTION,
    event_type=EventType.AGENT_INTENT_RECORDED,
    payload={"intent": {"summary": "Read a workspace report"}},
    sort_key="000",
)

action = EvidenceRecord.from_action(
    idempotency_key="example-action-001",
    source_kind=EvidenceSourceKind.LOCAL_FUNCTION,
    sort_key="001",
    action=NormalizedAction(
        action_type="read",
        tool_identity=ToolIdentity(
            name="safe_file_read",
            descriptor_hash="sha256:example_descriptor",
            adapter="local",
        ),
        resources=(
            NormalizedResource(
                resource_type=ResourceType.FILE,
                identifier="demo://workspace/report.txt",
            ),
        ),
    ),
)

result = import_evidence_batch([intent, action], normalizer=normalizer, journal=journal)
assert result.ok
assert verify_journal(journal_path).ok
```

See [docs/API_REFERENCE.md](docs/API_REFERENCE.md) for alpha-supported public
imports and preview API boundaries.

## CLI Highlights

```bash
uv run actionlineage version
uv run actionlineage demo run --output-dir build/actionlineage-demo
uv run actionlineage journal verify build/actionlineage-demo/evidence.jsonl
uv run actionlineage projection timeline build/actionlineage-demo/projection.sqlite --journal-path build/actionlineage-demo/evidence.jsonl --trace-id trace_demo_evidence_plane
uv run actionlineage projection explain-event build/actionlineage-demo/projection.sqlite evt_demo_11 --journal-path build/actionlineage-demo/evidence.jsonl
uv run actionlineage projection export-incident build/actionlineage-demo/projection.sqlite --journal-path build/actionlineage-demo/evidence.jsonl --trace-id trace_demo_evidence_plane
uv run actionlineage projection export-graph build/actionlineage-demo/projection.sqlite --journal-path build/actionlineage-demo/evidence.jsonl --trace-id trace_demo_evidence_plane
uv run actionlineage projection export-desktop-bundle build/actionlineage-demo/projection.sqlite build/actionlineage-demo/desktop --journal-path build/actionlineage-demo/evidence.jsonl --trace-id trace_demo_evidence_plane
uv run actionlineage contract validate contracts/examples/outbound-http.json build/actionlineage-demo/evidence.jsonl
```

See [docs/CLI_REFERENCE.md](docs/CLI_REFERENCE.md) for the full command
reference.

## Documentation Map

- [Maturity model](docs/MATURITY.md): supported, preview, planned, and external
  validation labels.
- [Quality scorecard](docs/QUALITY_SCORECARD.md): public claim-to-evidence map.
- [Agent Validation evidence](docs/AGENT_VALIDATION_EVIDENCE.md): deterministic
  no-model eval baseline and limitations.
- [External review guide](docs/EXTERNAL_REVIEW_GUIDE.md): five-minute review
  path, semantics to challenge, and safe feedback routes.
- [Good first issue candidates](docs/GOOD_FIRST_ISSUES.md):
  maintainer-ready issue drafts with bounded acceptance criteria.
- [Evaluation reproduction](docs/EVALUATION_REPRODUCTION.md): exact commands
  for public-package, demo, Agent Validation, and local release proof.
- [Troubleshooting](docs/TROUBLESHOOTING.md): first-time install, demo, path,
  browser, offline/online, and release proof guidance.
- [Known limitations](docs/KNOWN_LIMITATIONS.md): public-alpha boundaries and
  external-validation gaps.
- [Architecture](ARCHITECTURE.md): component boundaries and runtime flow.
- [Threat model](THREAT_MODEL.md): assets, adversaries, trust boundaries, and
  claim language.
- [Acceptance tests](ACCEPTANCE_TESTS.md): executable release criteria.
- [Data model](docs/DATA_MODEL.md): event envelope and payload conventions.
- [Schema reference](docs/SCHEMA_REFERENCE.md): `v1alpha1` event schema.
- [Compatibility](docs/COMPATIBILITY.md): supported journal and schema policy.
- [Tutorial](docs/TUTORIAL.md): local demo walkthrough.
- [Investigation workflow](docs/INVESTIGATION.md): timelines, summaries, graph,
  and case bundles.
- [Console](docs/CONSOLE.md): static analyst UI and desktop bundle export.
- [Journal integrity](docs/JOURNAL_INTEGRITY.md): anchors, archive manifests,
  recovery, and limits.
- [Lineage Contracts](docs/LINEAGE_CONTRACTS.md): telemetry requirements as
  code.
- [Detection Lab](docs/DETECTION_LAB.md): replay, mutation, minimization, and
  scorecards.
- [Agent Validation Lab](evals/README.md): development-only agent evaluation,
  replay, scorer, Docker, and artifact-audit workflow.
- [Agent Validation architecture](docs/AGENT_VALIDATION_ARCHITECTURE.md):
  eval boundaries, adapters, artifacts, and CI lanes.
- [Agent Validation threat model](docs/AGENT_VALIDATION_THREAT_MODEL.md):
  development-lab trust boundaries and failure modes.
- [Observers](docs/OBSERVERS.md): local, fixture, cloud, Kubernetes, and external
  sensor evidence.
- [Integrations](docs/INTEGRATIONS.md): exporters and optional ecosystem
  adapters.
- [Operations](docs/OPERATIONS.md): service mode, health, storage, and deployment
  notes.
- [Release checklist](docs/RELEASE_CHECKLIST.md): public release gates.
- [Publishing](docs/PUBLISHING.md): GitHub release workflow, artifact
  attestations, and Trusted Publishing setup.
- [Package managers](docs/PACKAGE_MANAGERS.md): GHCR, PyPI, Homebrew,
  conda-forge, and deferred channel plan.
- [Review process](docs/REVIEW_PROCESS.md): required checks, advisory AI
  review, and solo-maintainer merge policy.

## Packages and Extras

The repository currently ships as one Python distribution with optional extras:

```bash
uv sync --locked                 # core
uv sync --locked --extra adapters
uv sync --locked --extra service
uv sync --locked --all-extras
```

Core dependencies are intentionally small: Pydantic and Typer. Optional extras
hold MCP, OpenTelemetry, SQLAlchemy, FastAPI, JWT, and related integration
dependencies.

`actionlineage` `0.1.0a6` is the next corrective public-alpha hardening version
prepared from this source tree. PyPI and the GitHub Release currently publish
`0.1.0a5`; the already published `0.1.0a5` PyPI long description cannot be
changed in place, so corrected package text appears with the next owner-approved
upload. The release workflow is prepared to publish preview GHCR images for
version tags, capture the OCI digest, and sign/attest that digest, while
Homebrew and additional package-manager channels remain gated on external setup
and validation. See
[docs/PACKAGE_MANAGERS.md](docs/PACKAGE_MANAGERS.md).

## Security Model In One Paragraph

ActionLineage is not a sandbox, model guardrail, DLP engine, or universal proof
system. It records redacted, structured, causally linked evidence and verifies
local journal consistency under documented trust assumptions. When a report says
an outcome is verified, it means the named evidence source corroborated it
within the stated limitations. When no observation exists, the system reports
that no observation was recorded.

## Development

```bash
uv sync --locked --all-extras
uv run ruff check .
uv run ruff format --check .
uv run mypy src
uv run pytest
uv run python scripts/check_claims_language.py .
uv run python scripts/secret_scan.py .
uv run pip-audit
```

Before release, also run:

```bash
uv run python scripts/generate_sbom.py --output build/actionlineage-sbom.json
uv run python scripts/generate_release_provenance.py \
  --dist-dir dist \
  --output build/actionlineage-release-provenance.json
uv build
```

## License

Apache License 2.0. See [LICENSE](LICENSE).
