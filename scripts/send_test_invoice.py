"""Send one synthetic invoice-upload event to the Cashfree Relay "Invoice Intake" inbound webhook.

Purpose: let Relay capture a sample payload for the trigger. Sandbox only; the payload is synthetic.

    python scripts/send_test_invoice.py [--file-url URL]

Reads RELAY_INTAKE_WEBHOOK_URL from .env. The webhook path is a secret, so it is masked in output.
Exit codes: 0 = 2xx response, 1 = non-2xx response, 2 = config or network error.
"""
import argparse
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlsplit

import httpx
from dotenv import load_dotenv

ENV_VAR = "RELAY_INTAKE_WEBHOOK_URL"
TIMEOUT_SECONDS = 15.0
IST = timezone(timedelta(hours=5, minutes=30))
DEFAULT_FILE_URL = "https://example.com/files/invoice_test_001.png"


def build_payload(file_url: str) -> dict:
    return {
        "invoice_id": "INV-TEST-001",
        "vendor_id": "VEND-007",
        "uploaded_by": "accountant",
        "uploaded_at": datetime.now(IST).isoformat(timespec="seconds"),
        "file_name": "invoice_test_001.png",
        "file_url": file_url,
        "mime_type": "image/png",
    }


def mask_url(url: str) -> str:
    parts = urlsplit(url)
    head, _, token = parts.path.rpartition("/")
    if len(token) > 10:
        token = f"{token[:6]}...{token[-4:]}"
    return f"{parts.scheme}://{parts.netloc}{head}/{token}"


def fail(message: str) -> None:
    print(f"ERROR: {message}", file=sys.stderr)
    sys.exit(2)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--file-url", default=DEFAULT_FILE_URL, help=f"file_url to send (default: {DEFAULT_FILE_URL})")
    args = parser.parse_args()

    load_dotenv(Path(__file__).resolve().parent.parent / ".env")
    url = os.getenv(ENV_VAR, "").strip()
    if not url:
        fail(f"{ENV_VAR} is not set. Add it to .env (see .env.example).")
    if urlsplit(url).scheme != "https":
        fail(f"{ENV_VAR} must be an https URL.")

    payload = build_payload(args.file_url)
    print(f"POST {mask_url(url)}")
    print(json.dumps(payload, indent=2))
    print()

    try:
        response = httpx.post(url, json=payload, timeout=TIMEOUT_SECONDS)
    except httpx.TimeoutException:
        fail(f"No response within {TIMEOUT_SECONDS:.0f}s.")
    except httpx.HTTPError as exc:
        fail(f"Request failed: {type(exc).__name__}: {exc}")

    print(f"Status: {response.status_code} {response.reason_phrase}")
    print("Headers:")
    for name, value in response.headers.items():
        print(f"  {name}: {value}")
    print("Body:")
    try:
        print(json.dumps(response.json(), indent=2, ensure_ascii=False))
    except ValueError:
        print(response.text if response.text else "(empty)")

    if not response.is_success:
        print(f"\nERROR: Relay returned HTTP {response.status_code}.", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
