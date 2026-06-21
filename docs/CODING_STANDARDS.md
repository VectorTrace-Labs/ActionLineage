# Coding Standards

## Design

- Keep domain logic independent from transport and storage frameworks.
- Prefer protocols/interfaces at component boundaries.
- Make security decisions explicit values, not booleans hidden in control flow.
- Preserve original occurrence time and recorder observation time separately.
- Make nondeterminism injectable: clock, ID generator, randomness, and I/O.
- Treat serialization as a public compatibility boundary.

## Error handling

- Define domain-specific exceptions.
- Include safe context; never include secrets in exception messages.
- Distinguish invalid input, policy denial, unavailable dependency, timeout, and internal defect.
- Do not swallow exceptions after recording a generic success outcome.

## Logging

- Use structured logs.
- Correlate by run, trace, and event ID.
- Log event IDs and digests instead of raw sensitive payloads.
- Test log output for canary-secret leakage.

## Tests

- Unit tests for deterministic domain behavior.
- Integration tests for MCP, journal, API, and policy boundaries.
- Security regression tests for redaction, denial, replay, and tampering.
- Property-based tests only where invariants are clearly defined.
- Golden fixtures must be small, reviewed, and versioned.

## Commit discipline

- One coherent behavior per commit when practical.
- Use imperative, descriptive messages.
- Do not mix dependency upgrades with unrelated behavior.
- Keep generated files out of review unless they are intentional release artifacts.
