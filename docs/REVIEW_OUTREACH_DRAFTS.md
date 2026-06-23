# Review Outreach Drafts

Last reviewed: 2026-06-23.

This document prepares reusable public-alpha outreach copy for maintainer
review. It is not a publication record, external validation, adoption evidence,
or approval to announce. Owner approval is still required before posting,
publishing, or sending any announcement.

## Publication Preconditions

Before using any draft text:

- confirm the intended version remains `0.1.0a6` and alpha-scoped;
- run the release gate summary in `docs/QUALITY_SCORECARD.md`;
- review `docs/OWNER_PUBLICATION_CHECKLIST.md`;
- confirm `docs/DECISIONS_REQUIRED.md` owner gates for public announcements;
- do not claim external audit, external adoption, production use, independent
  review, or community validation;
- do not claim tamper-proof behavior, forensic completeness, or universal
  security.

## Release And Evaluation Announcement Draft

Title: Acknowledgement is not verification

Suggested short post:

ActionLineage public alpha is available for local evaluation as a
vendor-neutral evidence and detection plane for tool-using agents. Its core
claim is deliberately narrow: a successful tool response is acknowledgement,
not proof that the side effect happened.

The alpha records intent, delegated identity, tool execution, independent
observations, verification links, and explicit uncertainty in a canonical local
journal. The deterministic demo shows verified, unverified, conflicting, and
not-dispatched outcomes without requiring a model API key, cloud account, live
MCP server, or internet access after installation.

Try the package smoke path:

```bash
uvx --prerelease allow --from actionlineage==0.1.0a6 actionlineage version
uvx --prerelease allow --from actionlineage==0.1.0a6 actionlineage demo run --output-dir actionlineage-demo
uvx --prerelease allow --from actionlineage==0.1.0a6 actionlineage journal verify actionlineage-demo/evidence.jsonl
```

Reviewers can challenge the evidence semantics, redaction boundaries, journal
recovery behavior, generated visual proof, and ambiguous-correlation handling.
The best feedback is reproducible: exact command, environment, expected result,
actual result, and a minimized synthetic artifact when possible.

Known boundaries are intentional. Service mode, cloud observers, deployment
assets, and integration adapters remain preview or externally validated
surfaces unless the maturity docs say otherwise. No external audit, production
deployment, independent review, or community validation is claimed.

Pointers:

- `docs/EXTERNAL_REVIEW_GUIDE.md`
- `docs/EVALUATION_REPRODUCTION.md`
- `docs/KNOWN_LIMITATIONS.md`
- `docs/QUALITY_SCORECARD.md`
- `docs/TROUBLESHOOTING.md`

## Technical Article Outline

Working title: Acknowledgement is not verification: evidence semantics for
tool-using agents

Audience:

- detection and response engineers;
- security platform engineers;
- agent platform engineers;
- product security engineers reviewing tool-use boundaries.

Thesis:

Tool return values are component acknowledgements. Investigation-ready evidence
requires a causal chain that distinguishes requested, authorized, dispatched,
acknowledged, observed, verified, unverified, timed-out, conflicting, unknown,
and not-dispatched outcomes.

Outline:

1. The failure mode: agent tools can return success without proving the world
   changed as intended.
2. The core distinction: acknowledgement from a tool boundary versus
   independently observed or explicitly corroborated side effects.
3. The ActionLineage event model: intent, principal, descriptor hash, tool
   execution states, observations, and evidence links.
4. Verification limits: named observer, confidence, relationship, status, and
   limitations instead of universal proof.
5. Ambiguity handling: simultaneous actions, duplicate observations, and
   conflicting evidence should remain explicit rather than forced into false
   certainty.
6. Local evidence integrity: append-only journals and hash-chain verification
   are local tamper-evidence tools, not forensic completeness claims.
7. Reproducible review: run the five-minute demo, inspect the generated
   evidence map, validate the contract, and compare no-model Agent Validation
   baseline artifacts.
8. What to challenge next: redaction boundaries, observer trust assumptions,
   adapter fit, recovery workflows, and preview-surface maturity labels.

Required supporting evidence before publication:

- current package version and Python support from `pyproject.toml`;
- successful public package smoke or release-candidate artifact smoke;
- current demo evidence map generated from deterministic artifacts;
- current no-model Agent Validation baseline;
- current release-consistency or owner-gated publication status;
- explicit limitation links adjacent to capability claims.

Do not include:

- customer or proprietary prompts;
- unredacted production journals;
- live credentials or authorization material;
- screenshots or diagrams not derived from actual project output;
- claims that missing observations prove a side effect did not occur.
