# PS3 integration into main

The integration combines Check Service commit `af96eb8`, Sarvam feature commit
`91450f7`, and Relay rehearsal commit `beae3e1`. The previous remote main tip
was `ee9338e`.

## Decisions

- `CLAUDE.md` retains the deterministic written-amount check, owner and validation
  run binding, and the agreed HOLD decisions. It also documents the implemented
  Sarvam routes, tenant-scoped local tools, and planned Relay workflow.
- `.env.example` retains both sets of configuration. The Sarvam clients use
  HTTPX and the documented REST endpoints. No additional provider SDK is needed.
- Merge revision `5f2c9b0a7e41` preserves both original migration histories.
  `61a7b39e25c0` adds a document digest and an original-extraction snapshot and
  is the sole head.
- The shared Relay and Sarvam extraction schema retains supplier/buyer separation
  and the full GST breakdown. The input contract excludes raw bank details and
  requests only printed opaque references. Bank confirmation requires an
  authenticated owner and the existing vendor verification checks still run.
- Completed extraction goes through the existing invoice evaluator. It receives
  exact decimal strings, independently supplied business facts, and flat
  confidence values. Missing tax details and ambiguous dates stay unset. The
  document job stores the provider payload without changing it. The invoice
  retains the mapped request and links to the job through an audit event.
- The Relay sender requires an explicit isolated-test confirmation. Webhook URLs,
  response headers, response bodies, and exception text are excluded from output.
- Chat and translation remain advisory. The local tool registry exposes only
  vendor lookup. Initiation, retry controls and settlement stay on the existing
  owner-gated simulator path.

## External verification pending

Live Sarvam extraction, authenticated Relay access and a verified Relay draft
environment, and a Cashfree Sandbox payout remain external verification steps.
The integration tests use mocked Sarvam responses. The payout demo uses a local
simulator and its separate signed settlement protocol.

## Project MCP

The repository includes a stdio MCP server for tenant-scoped invoice and simulated
payment reads and non-persisting validation. See the [MCP architecture](architecture/mcp-architecture.md)
and [Codex example](../mcp/codex-config.example.toml). The hosted Cashfree MCP and
its merchant OAuth remain separate.

## Merchant frontend

The original vanilla JavaScript merchant app is built with npm and Vite.
Development uses an API proxy and the production bundle is served by FastAPI.
The UI uses the document, review, translation, owner approval and simulator
status endpoints, with a memory-only browser session. The merchant extraction
mode can use the shared Sarvam REST job client. See [deployment](DEPLOYMENT.md).
