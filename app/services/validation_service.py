from decimal import Decimal, ROUND_HALF_UP

from app.models import Business, Vendor
from app.schemas.invoice import ExtractedInvoice
from app.schemas.validation import Check
from app.services.amount_in_words import parse_minor

CENT = Decimal("0.01")
TAXES = ("cgst", "sgst", "igst")
REQUIRED = (
    "invoice_number", "invoice_date", "acceptance_date", "currency", "gstin", "legal_name",
    "bank_reference", "lines", "subtotal", "cgst_rate", "sgst_rate", "igst_rate",
    "cgst", "sgst", "igst", "tax_total", "grand_total",
)


def rounded(value: Decimal) -> Decimal:
    return value.quantize(CENT, rounding=ROUND_HALF_UP)


def minor(value: Decimal) -> int:
    return int(value * 100)


def arithmetic(data: ExtractedInvoice, tolerance: Decimal) -> list[Check]:
    expected = {}
    if data.lines:
        expected["subtotal"] = sum(rounded(line.quantity * line.unit_price) for line in data.lines)
    if data.subtotal is not None:
        for field in TAXES:
            rate = getattr(data, f"{field}_rate")
            if rate is not None:
                expected[field] = rounded(data.subtotal * rate / 100)
    taxes = [getattr(data, name) for name in TAXES]
    if all(tax is not None for tax in taxes):
        expected["tax_total"] = sum(taxes)
    if data.subtotal is not None and data.tax_total is not None:
        expected["grand_total"] = data.subtotal + data.tax_total

    checks = []
    for field, calculated in expected.items():
        actual = getattr(data, field)
        if actual is None:
            continue
        correct = abs(actual - calculated) <= tolerance
        checks.append(Check(code=f"ARITHMETIC_{field.upper()}", status="PASS" if correct else "BLOCK",
                            detail=f"Expected {calculated:.2f} within {tolerance:.2f}.", fields=[field]))
    if data.igst_rate and (data.cgst_rate or data.sgst_rate):
        checks.append(Check(code="MIXED_GST", status="BLOCK", detail="IGST cannot be combined with CGST or SGST."))
    if data.grand_total == 0:
        checks.append(Check(code="ZERO_TOTAL", status="BLOCK", detail="Payment amount must be positive."))
    if data.total_in_words is not None and data.grand_total is not None:
        checks.append(check_amount_in_words(data))
    return checks


def check_amount_in_words(data: ExtractedInvoice) -> Check:
    fields = ["total_in_words", "grand_total"]
    try:
        if data.currency != "INR":
            raise ValueError("Currency is unsupported")
        stated_minor = parse_minor(data.total_in_words)
    except ValueError:
        return Check(code="AMOUNT_IN_WORDS_UNRECOGNIZED", status="HOLD",
                     detail="The written amount needs manual verification.", fields=fields)
    if stated_minor != minor(data.grand_total):
        return Check(code="AMOUNT_IN_WORDS_MISMATCH", status="BLOCK",
                     detail="The written amount differs from the numeric total.", fields=fields)
    return Check(code="AMOUNT_IN_WORDS_MATCH", status="PASS",
                 detail="The written amount matches the numeric total.", fields=fields)


def completeness(business: Business, vendor: Vendor | None, data: ExtractedInvoice) -> list[Check]:
    required = list(REQUIRED)
    if vendor and vendor.classification in {"Micro", "Small"}:
        required.append("written_agreement")
    missing = [field for field in required if getattr(data, field) is None]
    checks = [Check(code="MISSING_FIELDS" if missing else "COMPLETE", status="HOLD" if missing else "PASS",
                    detail="Mandatory fields are missing." if missing else "Mandatory fields are present.", fields=missing)]
    if data.confidence is not None:
        critical = required + (["total_in_words"] if data.total_in_words is not None else [])
        low = sorted(field for field in critical if field in data.confidence and data.confidence[field] < Decimal(
            business.field_confidence_thresholds.get(field, business.confidence_threshold)
        ))
        checks.append(Check(code="LOW_CONFIDENCE" if low else "EXTRACTION_CONFIDENCE",
                            status="HOLD" if low else "PASS",
                            detail="Critical fields require review." if low else "Reported critical confidence meets policy.",
                            fields=low))
    return checks


def cash_check(business: Business, currency: str | None, amount: int | None) -> list[Check]:
    if currency is None or amount is None:
        return []
    if currency != business.currency:
        return [Check(code="CURRENCY_UNSUPPORTED", status="HOLD", detail="No cash balance is configured for this currency.")]
    if amount > business.cash_minor:
        return [Check(code="INSUFFICIENT_CASH", status="HOLD", detail="Amount exceeds available cash.")]
    return [Check(code="CASH_AVAILABLE", status="PASS", detail="Amount is within available cash.")]
