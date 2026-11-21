# Accounts Payable Check Service

FastAPI service for the Cashfree × Sarvam Hackathon. It accepts structured extraction, evaluates invoice rules, records owner approval, and simulates payout attempts. The Sarvam Vision and Cashfree Relay hand-off is the JSON API. Payouts and payout events run entirely in the simulator.

## Run locally

From the project directory, with Python 3.12 or later:

```sh
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
cp -n .env.example .env
```

On a fresh setup, append independent, randomly generated credentials to `.env`:

```sh
python - <<'PY' >> .env
import json
import secrets

owner, service, webhook = (secrets.token_urlsafe(32) for _ in range(3))
keys = {
    owner: {"business_id": 1, "role": "owner", "subject": "demo-owner"},
    service: {"business_id": 1, "role": "service"},
}
print(f"CHECK_BEARER_KEYS='{json.dumps(keys)}'")
print(f"CHECK_DEMO_OWNER_KEY={owner}")
print(f"CHECK_SIMULATOR_SECRET={webhook}")
PY
chmod 600 .env
alembic upgrade head
python -m scripts.seed --cash 100000.00
uvicorn app.main:app --host 127.0.0.1 --port 8000
```

In a second terminal, run `.venv/bin/python -m scripts.demo` against the freshly seeded server. It exercises a valid invoice, a duplicate invoice, invalid arithmetic, a changed bank account, an unknown vendor, a written-amount mismatch and denied approval, and a repeated payment request followed by signed simulated settlement. Run `.venv/bin/python -m pytest -q` for the tests. The seeder creates one business, ten fictional vendors, and three account records per vendor.

## Merchant app

With the server running, open http://127.0.0.1:8000/ and paste `CHECK_DEMO_OWNER_KEY` from `.env`. Upload invoice PDFs
(or use **Try a sample**). Each upload is read, checked against the rules and rated by Prism. Invoices with passing rules
and a rating of 80 or more are **Processed** and ready for payment in Cashfree; everything else is **On hold** for a person
to verify or reject. Any invoice can be read in English, Tamil or Hindi offline, or any Sarvam language when
`SARVAM_API_KEY` is set. Offline, extraction reads a payload embedded in the synthetic sample PDFs and the Prism rating is a
heuristic stand-in. Real PDFs without that payload land on hold as unreadable until the live Sarvam adapter is added.

## API

Business and role come from the Bearer credential. `owner` can issue and confirm approvals, while `service` can validate, read, and initiate against an existing confirmed approval. Discover request and response definitions at local `/docs`.

| Method | Path | Result |
| --- | --- | --- |
| GET | `/health` | Process liveness |
| POST | `/api/v1/invoices/validate` | Invoice decision |
| POST | `/api/v1/invoices/batch-validate` | One status and decision or error per input array item |
| GET | `/api/v1/invoices/priorities` | Decisions ordered by eligible score, then invoice ID |
| GET | `/api/v1/invoices/{invoice_id}` | Current decision and approval eligibility |
| POST | `/api/v1/invoices/{invoice_id}/revalidate` | Recheck stored extraction against current verified bank and cash |
| POST | `/api/v1/approvals` | Owner challenge with 15-minute token and selected payment terms |
| POST | `/api/v1/approvals/confirm` | Consume a one-time token and record owner approval |
| POST | `/api/v1/payments/initiate` | Simulated attempt, or the existing record for an identical idempotent request |
| GET | `/api/v1/payments/{payment_id}` | Current simulated attempt |
| POST | `/api/v1/webhooks/payout` | Apply a signed simulator event |

Validation decisions use HTTP 200 for PASS, HOLD, and BLOCK. Structurally malformed requests use 422, invalid credentials use 401, authorization failures use 403, missing tenant-scoped resources use 404, and invalid state transitions use 409. Batch requests accept up to 100 items and commit each valid item independently.

Send monetary values and percentages as decimal strings. Send zero values for unused taxes. This MVP assumes one tax rate per component over the invoice subtotal, rounds each line extension and tax component half-up to two decimals, and has one two-decimal cash currency per business. The default arithmetic tolerance is one minor unit. For a full extraction example, see `synthetic_invoice()` in `scripts/demo.py`. Use opaque bank references with the `ref:` prefix outside demonstrations. Preserve the extracted JSON without including raw bank account numbers or credentials. Send the optional `total_in_words` field to compare it exactly against `grand_total`. English INR wording supports lakh, crore, and paise. Ungrouped decimal numerals can use Unicode decimal digits. A recognised contradiction blocks. Unsupported, ambiguous, or empty wording holds for review. Omitting the field preserves the existing extraction contract. Confidence is optional. When supplied, reported critical fields are checked against the configured threshold and overrides.

Invoice numbers are NFKC-normalized, case-folded, and stripped of separators. A matching identity with conflicting secondary evidence is held. A matching document digest or matching identity without contradictory evidence is blocked. Matching vendor, date, amount, and currency with a distinct invoice number is held for review. Duplicate-identity submissions return the canonical ID and preserve their own audit and validation records. A GET on that ID returns the canonical invoice decision.

The business record stores deadline settings, rounding tolerance, default and per-field confidence thresholds, and four relative priority weights. Vendor priority is set on the vendor record. The synthetic demo uses 15 days from acceptance for Micro and Small vendors, or 45 days with a written agreement. Medium and Non-MSME vendors use the configurable standard period of 30 days. These are hackathon assumptions. The score weights urgency, overdue risk, MSME classification, and vendor business priority at 50/25/15/10 by default. Each component is scaled to 0–100. Bank, cash, and duplicate checks remain eligibility gates regardless of score. Revalidate an invoice held for insufficient cash after funding becomes available.

## Bank changes and payment recovery

For the synthetic demo, an independent operator can record a trusted primary account change using the local administration command:

```sh
python -m scripts.verify_demo_bank --business-id 1 --vendor-id 1 \
  --reference demo:vendor-1:alternate --attest-demo-verification
```

A previously held invoice carrying that reference can then be revalidated. An authenticated owner can also revalidate a previously submitted invoice with a body of `{"bank_reference":"demo:vendor-1:alternate"}`. The original extraction is preserved. Both paths check the current verified primary account and require fresh approval after a bank change.

Set a unique `subject` for each owner in `CHECK_BEARER_KEYS` to identify them in the approval record. Legacy key entries without a subject use a one-way credential fingerprint. A challenge can only be confirmed by its issuing owner identity. New approvals record the precise canonical validation run. Any revalidation replaces that run and requires fresh approval. After migration, unspent approvals created under the old schema also require fresh approval. Historical payment and idempotency records remain available.

An approval challenge reports `PENDING_APPROVAL` and confirmation reports `APPROVED`. Payment attempts begin at `INITIATED`. The first initiation reserves cash and returns 201. An identical replay returns 200 and the current payment record. The same key with different terms is rejected. The payment reference identifies a simulated attempt through settlement.

Simulator event JSON contains `external_reference` and `status`. Set `X-Simulator-Signature` to the hex HMAC-SHA256 of the exact raw body using `CHECK_SIMULATOR_SECRET`. This protocol is specific to the local simulator. A signed event moves INITIATED to SUCCESS, FAILED, or UNKNOWN. UNKNOWN retains reserved cash and allows reconciliation to SUCCESS or FAILED. SUCCESS can move to REVERSED. FAILED and REVERSED release reserved cash once. To start another attempt after FAILED or after investigating REVERSED, the owner must issue and confirm a fresh approval with the last `previous_payment_id` and a `reason`. Initiation then requires a new idempotency key.

Live Sarvam credentials and execution, Cashfree payouts and provider signature verification, and Relay deployment still require external verification. The local bank operator records demo verification only. Correcting non-bank extraction errors or adjudicating potential duplicates requires an out-of-band review.

## Sarvam agent

Set `SARVAM_API_KEY` in the server environment, install requirements and run
`alembic upgrade head` before starting the API. All agent routes require the
existing business bearer credential. Use synthetic documents and text only.

List agents with `GET /api/v1/agent-runs`. POST to the same path with
`{"agent_id":"vendor_agent","input":{"type":"text","content":"Look up vendor 1"}}`.
The vendor tool reads the authenticated business's vendor records. Chat output
is advisory. Payment validation, approval and initiation use the existing APIs.

Upload a synthetic PDF, PNG or JPEG as multipart field `file` to `POST /api/agents/sarvam/invoices`.
Poll `GET /api/agents/sarvam/invoices/{job_id}` with a credential for the same business.
Inspect the source and completed extraction before submitting a validation decision.
A partial job can be inspected and must be completed before validation.

Call `POST /api/agents/sarvam/invoices/{job_id}/validate` with the independently
recorded `acceptance_date` and `written_agreement`. After checking the destination
independently, the authenticated owner can include `confirmed_bank_reference`.
The mapper rejects a conflicting observed reference by leaving banking evidence
unset. The existing validator still checks the chosen reference against the
vendor's current verified primary account. Owner payment approval is a separate
step. The job keeps the original provider result and annotations for audit, the
invoice retains its mapped input, and the audit event links the records.

Use the common [extraction schema](docs/relay/sarvam_invoice_schema.json) for
Relay. It transcribes supplier identity, line items, totals and individual GST
components, with opaque banking references. Supply explicit zero tax amounts and
rates when documented. Empty tax components and ambiguous dates remain missing
and can hold the invoice. Only unambiguous ISO invoice dates are mapped. Confidence
uses the provider's 0–1 scale, with the lowest applicable quantity or unit-price
score used for line items.

For display translation, POST `text`, `source_language` and `target_language`
to `/api/agents/sarvam/translate`. The frontend helpers accept a fetch function
from the host app for authenticated requests. Keep the provider key server-side.

### Invoice intake demo (Relay)

Relay's Sarvam "Extract Document Data" step cannot take a file URL, so extraction runs here and Relay
only routes the result. After `/validate` commits a decision, the service POSTs one flat event to the
Relay "Invoice Intake" inbound webhook when `RELAY_INTAKE_WEBHOOK_URL` is set:
`event`, `job_id`, `invoice_id`, `invoice_number`, `vendor_name`, `amount`, `currency`,
`overall_status`, `payout_permitted`, `requires_owner_approval`, `risk_indicators`, `failure_reasons`,
`summary_en` and `summary_ta` (Sarvam translation, blank if unavailable). It carries no bank details.
Delivery is best-effort: it never changes the decision, the response header `X-Relay-Notified` reports
it, and an audit event `relay_intake_notified` records it. In Relay: Inbound Webhook → Router on
`overall_status` → WhatsApp (`summary_ta`) and Sheets.

With the API running and `SARVAM_API_KEY` set, drive one invoice end to end with
`python scripts/intake_invoice.py FILE` (uses `CHECK_DEMO_OWNER_KEY`). The fixtures in `tests/fixtures`
are rendered by `scripts/make_test_invoice.py` (needs Pillow):

| Fixture | Command | Expected |
| --- | --- | --- |
| `invoice_pass_002.png` | `... invoice_pass_002.png --confirm-bank-reference demo:vendor-3:current` | PASS, owner approval required |
| `invoice_math_003.png` | `... invoice_math_003.png --confirm-bank-reference demo:vendor-3:current` | BLOCK `ARITHMETIC_SUBTOTAL` |
| `invoice_test_001.png` | `... invoice_test_001.png` | BLOCK `UNKNOWN_VENDOR` (supplier not in the register) |

Running the same invoice twice exercises duplicate detection. `scripts/send_test_invoice.py` posts a
file-URL event and is kept for the earlier Relay trigger rehearsal. See the [integration report](docs/PS3_INTEGRATION.md).

## PS3 MCP server

The local stdio MCP server exposes tenant-scoped invoice and simulated payment
reads plus a non-persisting validation preview. It uses a dedicated `mcp` bearer
role. See the [architecture and setup](docs/architecture/mcp-architecture.md) and
[Codex example](mcp/codex-config.example.toml).
