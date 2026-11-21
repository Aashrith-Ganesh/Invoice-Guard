import argparse
import json
from datetime import UTC, datetime, timedelta
from hmac import digest
from os import environ
from uuid import uuid4

from dotenv import load_dotenv
import httpx


def synthetic_invoice() -> dict:
    today = datetime.now(UTC).date()
    return {
        "invoice_number": f"FICTIONAL-{uuid4().hex[:12]}",
        "invoice_date": (today - timedelta(days=12)).isoformat(),
        "acceptance_date": (today - timedelta(days=11)).isoformat(),
        "written_agreement": False,
        "currency": "INR",
        "gstin": "99ZZZZZ0000Z0Z0",
        "legal_name": "Fictional Vendor 1",
        "bank_reference": "demo:vendor-1:current",
        "lines": [{"quantity": "2", "unit_price": "50.00"}],
        "subtotal": "100.00",
        "cgst_rate": "9",
        "sgst_rate": "9",
        "igst_rate": "0",
        "cgst": "9.00",
        "sgst": "9.00",
        "igst": "0.00",
        "tax_total": "18.00",
        "grand_total": "118.00",
        "total_in_words": "Rupees one hundred and eighteen only",
    }


def run_demo(base_url: str, owner_key: str, simulator_secret: str) -> None:
    owner_headers = {"Authorization": f"Bearer {owner_key}"}
    with httpx.Client(base_url=f"{base_url.rstrip('/')}/api/v1") as client:
        def post(path: str, **data):
            return client.post(path, json=data, headers=owner_headers).raise_for_status().json()

        def validate(data: dict, label: str, expected: str, risk: str | None = None) -> dict:
            result = post("/invoices/validate", **data)
            if result["overall_status"] != expected or (risk and risk not in result["risk_indicators"]):
                raise RuntimeError(f"{label} returned {result['overall_status']} {result['risk_indicators']}")
            print(f"{label} -> {result['overall_status']} {', '.join(result['risk_indicators'])}".rstrip())
            return result

        invoice = synthetic_invoice()
        original = validate(invoice, "Original valid invoice", "PASS")
        validate(invoice, "Duplicate invoice", "BLOCK", "CONFIRMED_DUPLICATE")
        validate(synthetic_invoice() | {"grand_total": "116.00", "total_in_words": None},
                 "Incorrect arithmetic", "BLOCK", "ARITHMETIC_GRAND_TOTAL")
        validate(synthetic_invoice() | {
            "bank_reference": "demo:vendor-1:alternate",
            "invoice_date": (datetime.now(UTC).date() - timedelta(days=13)).isoformat(),
        }, "Changed bank", "HOLD", "BANK_CHANGE")
        rejected = validate(synthetic_invoice() | {
            "total_in_words": "Rupees one hundred and seventeen only",
            "invoice_date": (datetime.now(UTC).date() - timedelta(days=14)).isoformat(),
        }, "Amount in words mismatch", "BLOCK", "AMOUNT_IN_WORDS_MISMATCH")
        denial = client.post("/approvals", json={"invoice_id": rejected["invoice_id"]}, headers=owner_headers)
        if denial.status_code != 409 or denial.json()["error"]["code"] != "INVOICE_INELIGIBLE":
            raise RuntimeError("The blocked invoice must be ineligible for approval")
        print("Blocked invoice approval -> 409 INVOICE_INELIGIBLE")
        validate(synthetic_invoice() | {"gstin": "99YYYYY0000Y0Z0"},
                 "Unknown vendor", "BLOCK", "UNKNOWN_VENDOR")

        invoice_id = original["invoice_id"]
        challenge = post("/approvals", invoice_id=invoice_id)
        approval = post("/approvals/confirm", token=challenge["token"])
        request = {"invoice_id": invoice_id, "approval_id": approval["approval_id"],
                   "idempotency_key": uuid4().hex}
        first = post("/payments/initiate", **request)
        repeated = post("/payments/initiate", **request)
        if first != repeated or repeated["status"] != "INITIATED":
            raise RuntimeError("Repeated payout should return the original simulated attempt")
        payment_id = repeated["payment_id"]
        print(f"Duplicate payment request -> same INITIATED payment {payment_id}")

        payload = json.dumps({"external_reference": first["external_reference"], "status": "SUCCESS"}).encode()
        signature = digest(simulator_secret.encode(), payload, "sha256").hex()
        settled = client.post("/webhooks/payout", content=payload, headers={
            "Content-Type": "application/json", "X-Simulator-Signature": signature,
        }).raise_for_status().json()
        persisted = client.get(f"/payments/{payment_id}", headers=owner_headers).raise_for_status().json()
        if settled != persisted or settled["status"] != "SUCCESS":
            raise RuntimeError("The signed simulator event must settle the persisted attempt")
        print(f"Signed simulator event -> payment {payment_id} SUCCESS")


if __name__ == "__main__":
    load_dotenv()
    parser = argparse.ArgumentParser(description="Exercise the fictional demo against a freshly seeded service.")
    parser.add_argument("--url", default="http://127.0.0.1:8000")
    args = parser.parse_args()
    run_demo(args.url, environ["CHECK_DEMO_OWNER_KEY"], environ["CHECK_SIMULATOR_SECRET"])
