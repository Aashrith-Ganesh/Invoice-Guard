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

Live Sarvam adapters, Cashfree payouts and signature verification, and Relay deployment are future integration work. The local bank operator records demo verification only. Correcting non-bank extraction errors or adjudicating potential duplicates requires an out-of-band review.
