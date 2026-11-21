"""Three synthetic wedding-vendor invoices for the demo, rendered as PDFs with today's dates.

All vendors are the fictional ones from `scripts/seed.py`. Upload `clean-printed` twice for the duplicate trap.
"""
from datetime import UTC, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal

from app.integrations.sarvam.demo_pdf import render
from app.schemas.document import Sample

CENT = Decimal("0.01")


def _vendor(number: int) -> dict:
    return {"gstin": f"99ZZZZZ{number - 1:04d}Z0Z0", "legal_name": f"Fictional Vendor {number}",
            "bank_reference": f"demo:vendor-{number}:current"}


def _invoice(number: int, invoice_no: str, items: list[tuple[str, str, str]], *, days_ago: int = 3,
             gst: str = "9", total_override: str | None = None, display: dict | None = None, **extra) -> dict:
    today = datetime.now(UTC).date()
    lines, display_items, subtotal = [], [], Decimal(0)
    for description, quantity, price in items:
        amount = (Decimal(quantity) * Decimal(price)).quantize(CENT, ROUND_HALF_UP)
        subtotal += amount
        lines.append({"quantity": quantity, "unit_price": price})
        display_items.append({"description": description, "quantity": quantity, "unit_price": price,
                              "amount": f"{amount:.2f}"})
    tax = (subtotal * Decimal(gst) / 100).quantize(CENT, ROUND_HALF_UP)
    invoice = _vendor(number) | {
        "invoice_number": invoice_no,
        "invoice_date": (today - timedelta(days=days_ago)).isoformat(),
        "acceptance_date": (today - timedelta(days=days_ago - 1)).isoformat(),
        "written_agreement": False, "currency": "INR", "lines": lines,
        "subtotal": f"{subtotal:.2f}", "cgst_rate": gst, "sgst_rate": gst, "igst_rate": "0",
        "cgst": f"{tax:.2f}", "sgst": f"{tax:.2f}", "igst": "0.00", "tax_total": f"{tax * 2:.2f}",
        "grand_total": total_override or f"{subtotal + tax * 2:.2f}",
        "confidence": {field: "0.99" for field in ("invoice_number", "invoice_date", "gstin", "legal_name",
                                                   "bank_reference", "subtotal", "tax_total", "grand_total")},
    } | extra
    return {"version": 1, "invoice": invoice, "display": {"items": display_items, "language": "en"} | (display or {})}


def _catalog() -> dict[str, tuple[Sample, dict]]:
    stamp = datetime.now(UTC).strftime("%m%d")
    samples = [
        (Sample(name="clean-printed", title="Annapoorna Wedding Caterers", expected="PROCESSED",
                description="Printed English GST invoice for the reception lunch. Everything matches. Upload it twice to see the duplicate trap."),
         _invoice(2, f"AWC/{stamp}/118", [("Wedding lunch, veg thali per plate", "180", "380.00"),
                                          ("Filter coffee and sweets counter", "1", "12000.00")],
                  display={"trade_name": "Annapoorna Wedding Caterers", "vendor_address": "12 Mylapore Tank St, Chennai 600004"})),
        (Sample(name="handwritten-hindi", title="Shagun Mehendi & Dhol", expected="ON_HOLD",
                description="Handwritten Hindi bill. Rules pass but Prism rates it below 80, so a person must verify."),
         _invoice(4, f"SMD {stamp}/31", [("Bridal mehendi artist", "1", "15000.00"),
                                         ("Guest mehendi, per hand", "80", "150.00"), ("Dhol and nadaswaram team", "1", "22000.00")],
                  display={"trade_name": "Shagun Mehendi & Dhol", "language": "hi", "handwritten": True,
                           "language_note": "Original language: Hindi"},
                  confidence={"invoice_number": "0.88", "invoice_date": "0.91", "gstin": "0.97", "legal_name": "0.93",
                              "bank_reference": "0.96", "subtotal": "0.87", "tax_total": "0.89", "grand_total": "0.86"})),
        (Sample(name="changed-bank", title="Golden Frame Wedding Photography", expected="ON_HOLD",
                description="Bank account differs from the verified one. Held until the account is independently verified."),
         _invoice(5, f"GFP/{stamp}/552", [("Candid photography, 2 days", "1", "75000.00")],
                  bank_reference="demo:vendor-5:alternate",
                  display={"trade_name": "Golden Frame Wedding Photography", "vendor_address": "Anna Nagar, Chennai"})),
    ]
    return {sample.name: (sample, payload) for sample, payload in samples}


def catalog() -> list[Sample]:
    return [sample for sample, _ in _catalog().values()]


def sample_pdf(name: str) -> bytes | None:
    entry = _catalog().get(name)
    return render(entry[1]) if entry else None
