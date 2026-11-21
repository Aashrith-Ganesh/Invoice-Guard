# Deploy the PS3 merchant application

Use synthetic data and the payment simulator.

## Same-origin deployment

1. From the repository root, create a Python 3.12+ environment and install
   `requirements.txt`. Copy `.env.example` to `.env` and supply independent
   owner, service, and simulator credentials as shown in the README.
2. Put the SQLite file on persistent storage using `CHECK_DATABASE_URL`. Back
   up the database and run `alembic upgrade head` followed by `alembic check`.
   Run `python -m scripts.seed --cash 100000.00` once on an empty demo database.
3. Use Node.js 20.19+ or 22.12+ and run `npm ci && npm run build` in
   `frontend/`. Include the generated `frontend/dist/` and the shared
   Sarvam schema at `docs/relay/sarvam_invoice_schema.json` in the deployment.
4. Start `uvicorn app.main:app --host 127.0.0.1 --port 8000` from the root.
   Terminate HTTPS at the reverse proxy and forward `/app/`, `/api/`, and the
   desired health endpoint to FastAPI. Keep the proxy upload limit large enough
   for the app’s 10 MiB PDF limit and multipart overhead. Allow at least 60
   seconds for the live document upload endpoint.
5. Verify `GET /health`, `GET /app/`, and an authenticated
   `GET /api/v1/workspace`. Owner approval and simulator settlement retain
   separate secrets. The UI never generates a settlement signature.

## Split-origin deployment

Serve the built files from `/app/` on the frontend HTTPS origin. Set
`VITE_API_BASE_URL` to the public HTTPS API origin before building. Set the
backend's `CHECK_CORS_ORIGINS` to the exact frontend origin. CORS accepts
Authorization and Content-Type headers from the configured origins. Vite
variables are public build settings. Supply all credentials through backend
environment variables or an operator-managed secret store.

## Extraction and integrations

`CHECK_DOCUMENT_EXTRACTOR=demo` reads only the structured synthetic demo format.
For live PDF extraction set `CHECK_DOCUMENT_EXTRACTOR=sarvam` and set
`SARVAM_API_KEY` on the server. Configure a verified sandbox Relay webhook
separately if needed. The separate Sarvam agent intake API can deliver decisions
to Relay. The merchant app uses its own document workflow and the payment
simulator.

The [local MCP server](architecture/mcp-architecture.md) uses stdio. The
Cashfree-hosted Relay MCP has separate merchant OAuth and has yet to be verified
with authenticated discovery.
