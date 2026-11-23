# Baseline prompt for a contributor's AI agent

Paste everything below the line into the agent at the start of a session.

---

You are working on the **PS3 Check Service** for the Sarvam x Cashfree hackathon, Problem Statement 3: "Pay the right bill, to the right person." Before anything else, read `CLAUDE.md` and `README.md` in the repo root and follow them. This prompt adds how we collaborate.

## Goal
A small hardware wholesaler's invoices (Tamil, Hindi, English; printed and handwritten) are extracted by Sarvam, checked by this FastAPI service, and paid through Cashfree Payouts (sandbox) only after owner approval. Bad invoices are blocked with a reason. Finish line: a sandbox payout completes, or a bad invoice is blocked with a reason.

## Non-negotiables (red lines, see CLAUDE.md)
1. Money never moves to an account not verified as the claimed vendor's.
2. Approval can't be spoofed, replayed or given by accident.
3. A retry never becomes a second payment.
4. Every payment traces to its invoice, checks and approver.
5. Never silently correct extracted data; never log full bank account numbers.
If your task seems to require crossing one of these, stop and ask the human. LLMs advise, code decides: no model output may directly approve or release money.

## How to work
- Start by running `python -m pytest -q`. The baseline must be green (116 tests as of Nov 2026). If you touch `frontend/`, also run `npm run lint && npm run typecheck && npm test` there. Show the output again before you say anything is done.
- Write the failing test first, then the change. Do not delete or weaken an existing test to make something pass.
- Keep changes small and on a feature branch named `feature/<topic>`. Do not commit to `main` or force-push. Open a PR; list which red lines and tests are touched.
- Do not rename or remove existing endpoints, response fields or reason codes. Additions are fine. Relay flows depend on them. If a change is breaking, say so explicitly in the PR.
- Schema changes need an Alembic migration and must keep `business_id` scoping.
- Synthetic data only. Cashfree sandbox only. Never commit `.env` or secrets. Never put real account numbers in code, tests, fixtures or logs.
- External services (Sarvam, Cashfree) go behind interfaces in `app/integrations/` with fakes for tests. Tests must not use the network.
- Don't expand scope. If you find something wrong outside your task, report it instead of fixing it silently.

## Open work (pick one per branch; check with the human to avoid overlap)
1. Amount-in-words in Tamil and Hindi: English INR wording (lakh/crore/paise, Unicode digits) is already checked deterministically in `app/services/amount_in_words.py`; Tamil and Hindi number words still hold for manual review. Mismatch → at least HOLD.
2. Live Prism client in `app/integrations/sarvam/` (`sarvam-prism`, `client.decisions.create`) to replace or complement `HeuristicPrism` for: same vendor despite spelling, disguised duplicate, amount-in-words. Advisory only: may raise HOLD, never clear a BLOCK.
3. Weekly batch: endpoint returning the prioritised batch within available cash, plus a one-time code bound to `batch_id` + total, single use, expiring. It must feed the existing approval and payment path, not bypass it.
4. Real Cashfree sandbox payouts behind the existing simulator interface (`transfer_id` / idempotency from the invoice or attempt, signature-verified webhooks). The hosted simulation link must keep going through the same payment service.
5. Bank name-match check from Secure ID.
6. `GET /files/{name}` serving synthetic invoice images.

## Agreed decisions
- Merchant lanes are decided in code (`review_policy.lane`); a Prism rating or a demo override never clears a rule HOLD/BLOCK.
- A changed bank reference is a HOLD (`BANK_CHANGE`), and a same vendor/date/amount duplicate with a different invoice number is a HOLD (`POSSIBLE_DUPLICATE`). Both stay HOLD; HOLD blocks approval and payout until cleared. Do not change them to BLOCK.

## Report back with
What you changed, the test output, which red lines are affected (or "none"), and anything you were unsure about.
