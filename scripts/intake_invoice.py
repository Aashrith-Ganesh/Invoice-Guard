"""Demo driver for invoice intake: upload -> Sarvam extraction -> deterministic validation -> Relay.

    python scripts/intake_invoice.py tests/fixtures/invoice_pass_002.png --confirm-bank-reference demo:vendor-3:current
    python scripts/intake_invoice.py tests/fixtures/invoice_math_003.png
    python scripts/intake_invoice.py tests/fixtures/invoice_test_001.png

Talks to a running Check Service (see README). The service, not this script, calls Sarvam and posts the
decision to the Relay "Invoice Intake" webhook when RELAY_INTAKE_WEBHOOK_URL is set in the server's .env.
Reads CHECK_DEMO_OWNER_KEY (owner bearer) and optional CHECK_API_BASE_URL from .env.
Exit codes: 0 = decision returned, 1 = API refused or extraction did not complete, 2 = config or network error.
"""
import argparse
import os
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx
from dotenv import load_dotenv

IST = timezone(timedelta(hours=5, minutes=30))
UPLOAD = "/api/agents/sarvam/invoices"
TERMINAL = {"completed", "partially_completed", "failed", "rejected"}
SHOWN_FIELDS = ("invoice_number", "invoice_date", "supplier_legal_name", "supplier_gstin",
                "subtotal", "tax_total", "grand_total", "total_in_words")


def fail(message: str, code: int = 2) -> None:
    print(f"ERROR: {message}", file=sys.stderr)
    sys.exit(code)


def api_error(response: httpx.Response) -> str:
    try:
        error = response.json().get("error", {})
        return f"HTTP {response.status_code} {error.get('code', '')}: {error.get('message', '')}".strip()
    except (ValueError, AttributeError):
        return f"HTTP {response.status_code}"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("file", type=Path, help="Invoice PDF, PNG or JPEG (synthetic only)")
    parser.add_argument("--acceptance-date", default=datetime.now(IST).date().isoformat(),
                        help="Date the goods were accepted, YYYY-MM-DD (default: today, IST)")
    parser.add_argument("--written-agreement", choices=("yes", "no"),
                        help="Whether a written payment agreement exists (required for Micro/Small vendors)")
    parser.add_argument("--confirm-bank-reference",
                        help="Owner-confirmed opaque bank reference, e.g. demo:vendor-3:current")
    parser.add_argument("--max-wait", type=float, default=300, help="Seconds to wait for extraction (default 300)")
    parser.add_argument("--poll", type=float, default=5, help="Seconds between status checks (default 5)")
    args = parser.parse_args()

    load_dotenv(Path(__file__).resolve().parent.parent / ".env")
    token = os.getenv("CHECK_DEMO_OWNER_KEY", "").strip()
    if not token:
        fail("CHECK_DEMO_OWNER_KEY is not set in .env (see README 'Run locally').")
    if not args.file.is_file():
        fail(f"File not found: {args.file}")
    base_url = os.getenv("CHECK_API_BASE_URL", "http://127.0.0.1:8000").rstrip("/")

    try:
        with httpx.Client(base_url=base_url, headers={"Authorization": f"Bearer {token}"}, timeout=60) as api:
            with args.file.open("rb") as document:
                submitted = api.post(UPLOAD, files={"file": (args.file.name, document)})
            if submitted.status_code != 202:
                fail(f"Upload refused: {api_error(submitted)}", 1)
            job_id = submitted.json()["job_id"]
            print(f"Uploaded {args.file.name}; Sarvam job {job_id}")

            deadline = time.monotonic() + args.max_wait
            while True:
                status_response = api.get(f"{UPLOAD}/{job_id}")
                if status_response.status_code != 200:
                    fail(f"Status check failed: {api_error(status_response)}", 1)
                job = status_response.json()
                print(f"  extraction: {job['status']}")
                if job["status"] in TERMINAL:
                    break
                if time.monotonic() > deadline:
                    fail(f"Extraction still {job['status']} after {args.max_wait:.0f}s; re-run later with the job ID.", 1)
                time.sleep(args.poll)
            if job["status"] != "completed":
                fail(f"Extraction ended as {job['status']}; nothing was validated.", 1)

            print("Extracted (as transcribed by Sarvam):")
            invoice = job.get("invoice") or {}
            for field in SHOWN_FIELDS:
                print(f"  {field}: {invoice.get(field, '')!r}")

            context = {"acceptance_date": args.acceptance_date}
            if args.written_agreement:
                context["written_agreement"] = args.written_agreement == "yes"
            if args.confirm_bank_reference:
                context["confirmed_bank_reference"] = args.confirm_bank_reference
            validated = api.post(f"{UPLOAD}/{job_id}/validate", json=context)
            if validated.status_code != 200:
                fail(f"Validation refused: {api_error(validated)}", 1)
    except httpx.HTTPError as exc:
        fail(f"Could not reach the Check Service at {base_url}: {type(exc).__name__}")

    decision = validated.json()
    print(f"\nDecision for invoice {decision['invoice_id']}: {decision['overall_status']}")
    for reason, code in zip(decision["failure_reasons"], decision["risk_indicators"]):
        print(f"  - {code}: {reason}")
    print(f"  payout permitted: {decision['payout_permitted']}; "
          f"owner approval required: {decision['requires_owner_approval']}")
    print(f"Relay notified: {validated.headers.get('X-Relay-Notified', 'unknown')}")


if __name__ == "__main__":
    main()
