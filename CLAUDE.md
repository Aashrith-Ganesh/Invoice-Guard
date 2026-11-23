# CLAUDE.md

Working instructions for Claude Code in this repo. README.md is for humans (run steps, API table); don't duplicate it.

## What this is

Entry for the Sarvam x Cashfree hackathon, Problem Statement 3: "Pay the right bill, to the right person."
An agent reads multilingual invoices (Tamil, Hindi, English; printed and handwritten) for a small hardware wholesaler,
pays the right vendors the right amounts in the right order, and refuses to pay when something is off, explaining why
to the owner in Tamil.
**Finish line:** a sandbox payout completes, or a bad invoice is blocked with a reason.

## Ground rules

- Synthetic data only. Cashfree sandbox only. Secrets live in `.env` (never committed); keep `.env.example` current.
- **LLMs advise, code decides.** Every money decision is deterministic Python here. Sarvam/Prism output is a signal
  feeding a rule, never the verdict.
- Before claiming something works, run `python -m pytest -q` and show the output.
- Python 3.12, FastAPI, pydantic v2, SQLAlchemy 2 + Alembic, pytest. Dependencies are in `requirements.txt`.

## Architecture

The planned Cashfree Relay deployment lives in the Cashfree dashboard. Its four workflows call this service over HTTP:
1. **Invoice Intake:** upload → this service (Sarvam Extract → map → validate) → POST decision event (EN + Tamil summary, no bank data) to the Relay inbound webhook → router (BLOCK/HOLD → Tamil WhatsApp + Sheets; PASS → bank verification → Sheets). Relay's Sarvam File field cannot take a URL, so extraction runs here (`app/integrations/relay/intake.py`; tests fake it via the autouse `relay_events` fixture).
2. **Weekly Payment Run:** Friday schedule → priorities → Tamil voice call with batch summary + one-time code → WhatsApp fallback
3. **Approval → Payout:** called only after the approval is confirmed → payout (`idempotency_key` per attempt) → Sheets
4. **Payout Status:** payout webhooks → status update → router (failed/reversed → unpaid + alert, no auto-retry)

Google Sheet "PS3 Ledger" is the audit trail, one row per invoice.

### Layout (what exists)

```
app/api/v1/        invoices, approvals, payments, webhooks, documents (merchant app), payment_links, mcp_access
                   routers (thin; logic lives in services)
app/api/           agent_routes (/api/v1/agent-runs), document_routes (/api/agents/sarvam), dependencies (auth)
app/services/      validation, amount_in_words, duplicate, vendor, prioritisation, invoice, approval, payment,
                   payment_link (hosted simulation links), document (PDF upload), review_policy (lane rule), view,
                   plain_language, samples
app/models/        SQLAlchemy models; every table is business-scoped (business_id)
app/schemas/       pydantic request/response models
app/core/          config (env), security (token hash), exceptions (reject()), masking
app/integrations/  cashfree/simulator.py (local payouts); relay/intake.py (decision event to the Relay webhook);
                   sarvam/ = Document AI and chat HTTP clients, invoice mapping, plus the merchant app's offline
                   stand-ins (demo extractor, heuristic Prism) and Mayura translate (live with SARVAM_API_KEY)
app/agent_framework/, app/tools/   local agent runtime and tool registry (vendor lookup only)
app/mcp_server/    stdio MCP server (read-only tools + validation preview, `mcp` role)
app/hosted_payment.py  restricted ASGI listener serving only the hosted simulator page and its two routes
frontend/          merchant app + hosted page `pay.html` (vanilla JS, Vite build to frontend/dist, served at /app)
scripts/           seed, demo, verify_demo_bank, intake_invoice, make_test_invoice, send_test_invoice
tests/             conftest (api fixture, relay_events), test_invoices, test_payments, test_red_lines, test_documents,
                   test_payment_links, test_balance, test_clear_bills, test_full_stack, test_relay_intake,
                   test_sarvam, test_registry, test_mcp; fixtures/ (synthetic invoice PNGs)
migrations/        Alembic (single head)
```

### Endpoints and authentication

`POST invoices/validate`, `POST invoices/batch-validate`, `GET invoices/priorities`, `GET invoices/{id}`,
`POST invoices/{id}/revalidate`, `POST approvals` (owner), `POST approvals/confirm` (owner),
`POST payments/initiate`, `GET payments/{id}`, `POST webhooks/payout` (HMAC-signed), `GET /health`.
The payment and validation routes use `/api/v1`. Sarvam document upload, status, completed-job validation, and translation use `/api/agents/sarvam`. Local agent runs use `/api/v1/agent-runs`; the only registered model tool is a tenant-scoped vendor lookup.
Merchant app (`/api/v1`): `GET workspace`, `PATCH workspace/balance` (owner), `POST documents` (PDF), `GET documents`,
`POST documents/clear` (owner, demo reset), `GET documents/{id}`, `GET documents/{id}/file`,
`POST documents/{id}/review` (owner; verify|reject|skip_tax|process_demo|return_to_review), `POST documents/{id}/translate`,
`GET samples`, `GET samples/{name}`.
Hosted simulation links (`/api/v1`): `POST payments/links` (owner, needs a confirmed approval),
`POST simulated-payment/status`, `POST simulated-payment/simulate` (public, authorised by the link token).
MCP (`/api/v1`, `mcp` role): `GET mcp/access`, `POST mcp/invoice-preview` (non-persisting).

Validation returns HTTP 200 with PASS/HOLD/BLOCK; 422 malformed, 401/403 auth, 404 scoped miss, 409 bad transition.

## Decisions (agreed by the team)

- A changed bank reference (`BANK_CHANGE`) is a **HOLD**, not a BLOCK. A same vendor/date/amount invoice with a different number (`POSSIBLE_DUPLICATE`) is a **HOLD**. HOLD still prevents approval and payout until an independent verification or revalidation clears it. Do not change these to BLOCK.

- **Merchant flow (Nov 2026):** vendors no longer use the platform; the merchant uploads the invoice PDF. Lanes are
  decided in code by `review_policy.lane`: **Processed** = rule checks PASS and (Prism rating >= 80 or a person verified it);
  **On hold** otherwise. A rating can't clear a rule HOLD/BLOCK, and "verify" is refused unless rules pass. An on-hold or
  rejected document blocks approval (`REVIEW_REQUIRED` / `INVOICE_REJECTED` in `approval_service.require_eligible`).
  The demo overrides `skip_tax`/`process_demo` (owner, only when demo processing is enabled) move a card for display but
  never clear the rule checks, so payment stays blocked; `return_to_review` undoes them.
- **Hosted payment (Nov 2026):** "Payment link" on a processed card → owner approval → a hosted simulation link
  (`pay.html#token`) that expires with the approval. "Simulate Payment" rechecks approval and eligibility and records one
  simulated payment through the normal payment service. No real gateway, no payment details collected.

## Red lines

Enforced in code **and** covered by tests. Never weaken, bypass or "temporarily" disable one. If a task needs to, stop and ask.

1. Money never moves to an account not verified as the claimed vendor's (`vendor_service.verify_vendor`, `approval_service.require_eligible`).
2. Approval can't be spoofed, replayed or given by accident: hashed single-use token, 15 min expiry, bound to the owner, invoice, amount, currency, verified bank account and validation run.
3. A retry never becomes a second payment: unique `idempotency_key`, unique `approval_id` per payment, no payout while an attempt exists unless the owner explicitly re-approves after FAILED/REVERSED.
4. Every payment traces to its invoice, checks (`invoice_validations`), approval and `audit_log`.
5. Never silently correct extracted data (`invoices.extracted` stores the submitted JSON). Never log full account numbers (`app/core/masking.py`; bank references are opaque `ref:`/`demo:` strings).

Test map: RL1 `test_invoices`/`test_payments`/`test_red_lines`; RL2 `test_payments`; RL3 `test_payments`; RL4/RL5 `test_red_lines`.

## Known gaps vs the original spec (open work, in priority order)

1. **Amount in words:** English INR wording with lakh/crore/paise and Unicode decimal digits is validated deterministically. Tamil and Hindi number words still require manual review.
2. **Prism signals:** Sarvam chat, translation and extraction adapters exist. Same-vendor-despite-spelling, disguised duplicate, amount-in-words via `client.decisions.create` (model `sarvam-prism`, `sarvamai>=0.1.43`). Prism may raise a HOLD, never clear a BLOCK.
3. **Weekly batch + one-time code:** no batch endpoint, no code bound to `batch_id` + total. Today approval is per invoice.
4. **Real Cashfree sandbox payouts:** payouts are simulated (`integrations/cashfree/simulator.py`). Replace behind the same interface; keep sandbox-only.
5. **Remaining spec gaps:** no bank name-match check from Secure ID; Udyam deadline logic exists but there is no "stop at available cash" batch selection.
6. `GET /files/{name}` for synthetic invoice images is not built.
7. The service emits English `failure_reasons` and stable `risk_indicators`. The Sarvam translation adapter can translate display text independently of validation.

## Conventions

- Rules and calculations are pure where possible; services take a `Session`, routers stay thin. Raise `reject(status, code, message)` for API errors.
- Reason codes (`risk_indicators`) are stable machine strings; the human text may change.
- Money is integer minor units (`amount_minor`); inputs are decimal strings.
- External calls (Sarvam, Cashfree) go behind a small interface in `app/integrations/` so tests use fakes. Tests never hit the network.
- Test first for any rule or red-line change. Add a fixture/case for every new rule (the demo traps: duplicate, changed bank, wrong arithmetic, mismatched name, low-confidence handwriting).
- Schema changes need an Alembic migration.
- Run locally: see README.md. Tests: `python -m pytest -q`.
- Coordination: see `docs/COLLEAGUE_AI_PROMPT.md` for the baseline prompt used by the other contributor's agent.
