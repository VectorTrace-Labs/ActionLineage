# Troubleshooting First-Time Evaluation

Last reviewed: 2026-06-23.

This guide is for public-alpha evaluators running the package, demo, or local
release proof for the first time. It does not change the supported surface in
`docs/MATURITY.md`; it points to the narrow, currently tested paths.

## Fast Diagnostic Snapshot

Start with:

```bash
actionlineage doctor
actionlineage version
python --version
```

From a source checkout, use:

```bash
uv run actionlineage doctor
uv run actionlineage version
uv run python --version
```

Include this output when reporting an evaluation failure. Do not include
credentials, authorization headers, customer data, proprietary prompts, or
unredacted production journals.

## Prerelease Installation

`0.1.0a6` is the corrective release-prep prerelease. After it is published,
tools that resolve package versions may require an explicit prerelease opt-in.
If `0.1.0a6` cannot be resolved, the owner publication gate is not complete yet;
use the repository checkout path or the latest public `0.1.0a5` package instead.

Preferred public smoke path:

```bash
uvx --prerelease allow --from actionlineage==0.1.0a6 actionlineage version
uvx --prerelease allow --from actionlineage==0.1.0a6 actionlineage demo run --output-dir actionlineage-demo
uvx --prerelease allow --from actionlineage==0.1.0a6 actionlineage journal verify actionlineage-demo/evidence.jsonl
```

Equivalent `pipx` shape:

```bash
pipx run --pip-args="--pre" --spec actionlineage==0.1.0a6 actionlineage version
```

Equivalent `pip` shape for a disposable virtual environment:

```bash
python -m venv .venv-actionlineage
. .venv-actionlineage/bin/activate
python -m pip install --upgrade pip
python -m pip install --pre actionlineage==0.1.0a6
actionlineage version
```

On Windows PowerShell, activate the environment with:

```powershell
.\.venv-actionlineage\Scripts\Activate.ps1
```

If the resolver says no matching distribution exists, confirm that the Python
interpreter is 3.12 or newer and that prerelease resolution is enabled.

## Unsupported Python Versions

The public alpha supports Python 3.12 and newer. Python 3.11 and older are not
part of the current support claim.

Useful checks:

```bash
python --version
python -c "import sys; print(sys.executable)"
```

For `uvx`, choose a supported interpreter explicitly when needed:

```bash
uvx --python 3.12 --prerelease allow --from actionlineage==0.1.0a6 actionlineage version
```

## uv, pipx, And pip Behavior

- Use `uvx --prerelease allow --from actionlineage==0.1.0a6 actionlineage ...`
  when you want a one-command public package evaluation.
- Use `pipx run --spec actionlineage==0.1.0a6 actionlineage ...` when your
  normal Python CLI workflow is `pipx`; add `--pip-args="--pre"` if resolution
  refuses prereleases.
- Use `pip install --pre actionlineage==0.1.0a6` only inside a disposable
  virtual environment.
- Use `uv sync --locked --all-extras` only from a repository checkout.

The PyPI install path needs internet access to fetch packages. The default demo
does not need a model API key, cloud account, live MCP server, or external
service after installation.

## Optional Extras

Core public evaluation does not require optional extras. The following source
checkout commands install extra dependency groups for local development or
preview surfaces:

```bash
uv sync --locked
uv sync --locked --extra adapters
uv sync --locked --extra service
uv sync --locked --all-extras
uv sync --locked --all-extras --group eval
```

Keep maturity labels in mind:

- `adapters`: preview MCP/OpenTelemetry/export integration surfaces.
- `service`: preview FastAPI/JWT service mode, not production deployment
  support.
- `eval`: development-only Agent Validation Lab dependencies.

Do not treat installing an extra as evidence that the surface is production
ready.

## Demo Failures

The main public demo path is:

```bash
actionlineage demo run --output-dir actionlineage-demo
actionlineage journal verify actionlineage-demo/evidence.jsonl
actionlineage contract validate contracts/examples/outbound-http.json actionlineage-demo/evidence.jsonl
```

If `contract validate` cannot find `contracts/examples/outbound-http.json`, you
are probably running from an installed package rather than a source checkout.
For installed-package smoke tests, run version, demo, and journal verification
first; contract validation is covered by repository and built-artifact smoke
lanes where the contract file is present.

If the demo command fails:

- run `actionlineage doctor`;
- retry with a fresh output directory;
- avoid paths inside read-only directories;
- avoid reusing a case export directory that already contains bundle files;
- keep generated artifacts under `build/`, `dist/`, or a temporary evaluation
  directory.

## Path And Browser Issues

README examples use `/tmp/...` for concise POSIX commands. On Windows or locked
down environments, use a local relative directory instead:

```bash
actionlineage demo run --output-dir actionlineage-demo
actionlineage projection export-console actionlineage-demo/projection.sqlite actionlineage-demo/console.html --trace-id trace_demo_evidence_plane
```

The static console is an HTML file. If double-clicking does not open it, open
the file from your browser's file picker. The console does not load remote
resources by default; browser extensions or local file restrictions can still
affect display.

## Offline Versus Online

Online requirements:

- installing from PyPI, TestPyPI, or another package index;
- fetching dependencies for a fresh source checkout;
- live-model Agent Validation lanes, when maintainers explicitly configure
  credentials.

Offline-capable after dependencies are installed:

- `actionlineage demo run`;
- `actionlineage journal verify`;
- projection timeline, case export, graph export, and static console export;
- no-model Agent Validation scripted scenarios from a prepared checkout.

## Release Proof And Review Index Issues

Local release proof commands write generated artifacts under `build/`, `dist/`,
or a temporary directory. Do not edit generated proof files by hand, and do not
treat a local troubleshooting run as publication or external-validation
evidence.

If `scripts/check_release_consistency.py --dist-dir ... --output ...` fails in
offline mode:

- confirm the wheel and sdist were rebuilt from the current checkout;
- inspect `release-consistency-offline.json` for `FAIL` or `UNKNOWN` checks;
- fix local version, changelog, README install pins, metadata, or distribution
  contents before regenerating the manifest.

If an online release-consistency report fails:

- distinguish local package metadata from owner-gated public state;
- missing GitHub Release objects and stale PyPI/TestPyPI long descriptions are
  release/publication gates, not a reason to republish immutable artifacts from
  a local troubleshooting run;
- package-index JSON, GitHub JSON, and project URL `HEAD` checks use a bounded
  read-only `curl` fallback when local Python `urllib` cannot validate TLS, so
  remaining failures should be treated as public-state drift unless the report
  still marks the check `UNKNOWN`.

If `scripts/write_release_review_index.py` reports `HASH_MISMATCH`, `MISSING`,
or `malformed_release_consistency_report`:

- regenerate the release proof artifact directory from a clean `build/` path or
  temporary path;
- rerun `scripts/write_release_candidate_manifest.py`;
- rerun `scripts/write_release_review_index.py`;
- preserve the failing JSON/report for review if the mismatch is unexpected.

## Safe Failure Reports

When reporting a problem, include:

- exact commands and exit codes;
- `actionlineage doctor` and `actionlineage version` output;
- Python version and installation method;
- whether the run used PyPI, TestPyPI, source checkout, wheel, sdist, or
  container;
- a synthetic or minimized artifact bundle when possible.

Do not share live secrets, authorization headers, bearer tokens, API keys,
session cookies, customer data, proprietary prompts, or unredacted production
journals. Use the evaluation feedback template for public reports and
`SECURITY.md` for sensitive vulnerabilities.
