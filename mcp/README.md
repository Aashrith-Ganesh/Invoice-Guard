# PS3 Check Service MCP

The executable server lives in `app/mcp_server`. Install the project
requirements, migrate and start the API, and provision an MCP credential for
the seeded tenant. See the [architecture and setup](../docs/architecture/mcp-architecture.md)
and the [Codex configuration example](codex-config.example.toml).

The server uses stdio. A compatible client launches it with
`python -m app.mcp_server.server` from the repository root. Standard output
carries MCP protocol messages.

Run `python -m pytest tests/test_mcp.py -q` for the MCP test suite. It uses an
ephemeral loopback API, synthetic tenants, and the payout simulator.
