# External Review Guide

Last reviewed: 2026-06-22.

This guide helps an outside engineer evaluate ActionLineage public alpha without
private maintainer guidance. It is a review aid, not evidence that an external
audit, production deployment, or independent validation has occurred.

## Five-Minute Install Path

Prerequisites:

- Python 3.12 or newer.
- `uv`.
- Internet access for the first package install.

Run the published public-alpha package:

```bash
uvx --prerelease allow --from actionlineage==0.1.0a3 actionlineage version
uvx --prerelease allow --from actionlineage==0.1.0a3 actionlineage demo run --output-dir actionlineage-review-demo
uvx --prerelease allow --from actionlineage==0.1.0a3 actionlineage journal verify actionlineage-review-demo/evidence.jsonl
```

Expected results:

- `actionlineage version` prints `0.1.0a3`.
- `demo run` creates `evidence.jsonl`, `projection.sqlite`, `timeline.json`,
  and `incident.json`.
- `journal verify` reports a verified local journal hash chain.

The demo itself is deterministic and credential-free after installation. It
does not need a model API key, cloud account, live MCP server, or internet
access.

From a repository checkout, reviewers can run the same first-time-user path
through one JSON-reporting smoke command:

```bash
uv run python scripts/smoke_public_quickstart.py \
  --command "uv run actionlineage" \
  --output-dir build/review-quickstart-smoke
```

## Flagship Repository Demo

From a repository checkout:

```bash
uv sync --locked --all-extras
make demo
make demo-map
uv run actionlineage journal verify build/actionlineage-demo/evidence.jsonl
uv run actionlineage contract validate \
  contracts/examples/outbound-http.json \
  build/actionlineage-demo/evidence.jsonl
```

The generated SVG and JSON map under `build/actionlineage-demo/` are visual
review aids derived from `incident.json`. The canonical evidence remains
`build/actionlineage-demo/evidence.jsonl`.

## Semantics To Challenge

Use the demo and fixtures to check whether ActionLineage keeps these facts
distinct:

- A tool acknowledgement is not proof of a side effect.
- Missing observations are not proof that an effect did not happen.
- Conflicting evidence preserves both claims and their provenance.
- Denied or blocked requests are recorded as not dispatched and are not sent
  downstream.
- Verification names the corroborating evidence source and its limitations.

Good review findings include places where docs, exports, or UI wording blur
those distinctions.

## Reproducibility Paths

Use `docs/EVALUATION_REPRODUCTION.md` for exact command bundles covering:

- public-package quickstart;
- repository demo and generated evidence map;
- deterministic no-model Agent Validation Lab;
- release proof gates that can run without credentials.

When a maintainer provides a local release-candidate bundle, start with
`build/release-candidate/REVIEW_INDEX.md` if present. It is generated from the
candidate manifest, which is generated from local artifact bytes and evidence
summaries, and it verifies listed artifact hashes. If the bundle includes
`release-consistency-*.json` reports, the index also summarizes PASS/FAIL/UNKNOWN
counts and non-passing checks. It is still local proof rather than a hosted
release, signed attestation, or independent review.

Use `docs/AGENT_VALIDATION_EVIDENCE.md` plus
`docs/evidence/agent-validation-baseline.md` and
`docs/evidence/agent-validation-baseline.json` for the current generated
no-model baseline and known Agent Validation gaps.

## What Data Is Safe To Share

Share synthetic or minimized data only:

- command lines and tool versions;
- generated demo artifacts from local test runs;
- minimized failing fixtures with secrets removed;
- redacted logs or tracebacks.

Do not share live credentials, bearer tokens, private keys, session cookies,
authorization headers, customer data, proprietary prompts, or unredacted
production journals in public issues.

## How To Report Feedback

Use the structured issue templates:

- Evaluation feedback: reproducibility failures, unclear semantics, drift in
  generated proof, or disagreement with an expected result.
- Security design review: non-sensitive design concerns, threat-model gaps, or
  boundary questions.
- Integration proposal: adapter, observer, exporter, policy, or platform-fit
  proposals.

For sensitive vulnerabilities, follow `SECURITY.md` and report privately.

## Useful First Contributions

These are good first issue candidates for a maintainer to create manually when
ready. They are not automatically opened by this document.

- Extend the minimized ambiguous-correlation fixture with one additional
  observer or adapter example.
- Add one documentation link-check target that runs without network credentials.
- Add a small compatibility fixture for a future-but-preserved event type.
- Improve troubleshooting text for one failed quickstart prerequisite.
- Add a synthetic static-console hostile-input fixture with no real secrets.

## Announcement Draft

Title: Acknowledgement is not verification

Outline:

1. Agents can report that a tool call returned, but that is not the same as
   proving a side effect occurred.
2. ActionLineage records intent, identity, tool execution, observed effects,
   verification links, and explicit uncertainty in a local journal.
3. The public alpha is for local evaluation and fixture-backed integrations,
   with service and cloud surfaces labeled preview.
4. The five-minute demo and no-model Agent Validation baseline are reproducible
   without credentials.
5. Feedback requested: semantics, redaction boundaries, journal recovery,
   adapter fit, and ambiguous evidence cases.

Do not publish an announcement that claims external audit, external adoption,
production use, independent review, or community validation until real evidence
exists.
