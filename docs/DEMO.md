# PS3 demo runbook

Follow [local setup](../README.md#run-locally) from the repository root. Use a
fresh synthetic database with a seeded balance of ₹1,00,000 and leave
`CHECK_DOCUMENT_EXTRACTOR=demo` for a rehearsal that needs no provider access.
Open `http://127.0.0.1:8000/app/` and connect with the owner key from your
local `.env`.

## Walkthrough

1. Choose **Try a sample** and select **Annapoorna Wedding Caterers**. The
   synthetic invoice should land in **Processed** when the seeded cash is
   available. Open its checks to show the verified supplier, tax calculations,
   and invoice total.
2. Open **Payment link** on that invoice's card. Review the amount and payment
   terms, confirm owner approval, and choose **Create simulation link**. Copy
   or open the complete generated URL, including everything after `#`.
3. On the hosted page, point out the invoice reference, vendor, amount, expiry
   and simulation label. Click **Simulate Payment**. Refresh or reopen the
   page to show the persisted success and reference. A repeated settlement
   request returns the same payment.
4. Upload the original sample again to show duplicate detection. Use
   **Golden Frame Wedding Photography** to show why an independently verified
   bank account matters. Use **Shagun Mehendi & Dhol** to show owner review
   when the deterministic checks pass and the review rating is below threshold.
5. Explain the two kinds of review. Owners can verify a bill with passing rule
   checks that is held for its rating. Missing-data demo actions can move an
   eligible bill into the processed column for display, while its underlying
   checks still block payment. **Return to review** restores the visible hold.

In a synthetic workspace, the owner can clear old bills and payment records
using **Clear all bills**. The action preserves the current available balance
and vendor records. Use **Adjust balance** to restore ₹1,00,000 for the next
rehearsal. Demo mode enables the reset and demo processing controls. For a
synthetic workspace using live extraction, the corresponding opt-ins are
`CHECK_ENABLE_DEMO_BILL_RESET` and `CHECK_ENABLE_DEMO_PROCESSING`.

## Run the hosted simulator on port 8001

Set `CHECK_HOSTED_PAYMENT_ORIGIN=http://127.0.0.1:8001` in the repository's
local `.env`, restart the merchant server, then start the hosted listener from
the same repository root:

```sh
.venv/bin/uvicorn app.hosted_payment:app --host 127.0.0.1 --port 8001
```

Generate a new link from the dashboard after changing the setting. Opening
`/app/pay.html` alone gives an invalid-link message because the page needs its
token. Both listeners share the database and simulator secret. For remote
viewers, use a reachable [HTTPS deployment](DEPLOYMENT.md#separate-hosted-payment-listener).

## What each integration does

| Component | Role in PS3 |
| --- | --- |
| Sarvam | With a server-side key and `CHECK_DOCUMENT_EXTRACTOR=sarvam`, the dashboard submits PDFs to Sarvam Document AI. The separate Sarvam API routes also expose extraction, chat and translation. Automated tests mock provider responses. |
| FastAPI Check Service | Validates supplier identity, independently verified bank references, arithmetic, cash and duplicates. Owner confirmation binds payment to the validated invoice, amount and account. |
| Cashfree Relay | The separate `POST /api/agents/sarvam/invoices/{job_id}/validate` endpoint can notify an explicitly configured Relay webhook after validation. Authenticated discovery and test workspace access for the hosted Relay MCP remain unverified. |
| Hosted payment page | Uses the local payment simulator. It collects no banking or card data and sends no requests to a payment gateway. |
| Project MCP | A local stdio server for tenant-scoped reads and validation preview. See [MCP architecture](architecture/mcp-architecture.md). |

## Verify a release

Run from the repository root with the Python environment active:

```sh
alembic heads
alembic check
python -m pytest -q
(cd frontend && npm ci && npm run lint && npm run typecheck && npm test && npm run build)
```

Against a freshly seeded running service, `python -m scripts.demo` runs the
API-level validation and signed settlement scenarios. The hosted-link tests
also cover approval gating, expiry, a restricted listener and idempotent replay.
