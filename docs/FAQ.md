# FAQ

## Is ActionLineage an MCP firewall?

No. MCP interception can be an adapter, but ActionLineage public alpha is a
vendor-neutral evidence and detection plane.

## Does a successful tool response prove the side effect happened?

No. It records acknowledgement from the tool or adapter. Verification requires
independent or explicitly identified corroborating evidence.

## What is canonical evidence?

The append-only local journal. Projections, reports, telemetry exports, service
responses, and static console files are views or mirrors.

## Does ActionLineage require a model provider?

No. The default demo and tests run without a model API key, cloud account, or
internet access.

## Can policy enforcement block tools?

Optional adapters can enforce policy. Core evidence recording does not require
enforcement, and policy failure must never be silently converted to allow.

## How should missing observations be described?

Say no observation was recorded. Do not infer that the side effect did not
occur.

## Which install extra should I use?

Start with the core package. Use `dev` for development checks, `adapters` for
MCP/telemetry integration work, and `service` for the optional API service.
`console` and `cloud` are reserved extension points for future optional
packages.
