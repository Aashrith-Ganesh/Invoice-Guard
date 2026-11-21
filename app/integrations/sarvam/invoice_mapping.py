"""Map Sarvam's invoice transcription into the deterministic validation contract."""

import re
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.schemas.invoice import ExtractedInvoice
from app.schemas.vendor import BankReference


class InvoiceContext(BaseModel):
    """Business facts supplied independently of the document extraction."""

    model_config = ConfigDict(extra="forbid")

    acceptance_date: date | None = None
    written_agreement: Annotated[bool, Field(strict=True)] | None = None
    confirmed_bank_reference: BankReference | None = None


SOURCE_FIELDS = {
    "invoice_number": ("invoice_number",),
    "invoice_date": ("invoice_date",),
    "gstin": ("supplier_gstin", "gstin"),
    "legal_name": ("supplier_legal_name", "vendor_name"),
    "currency": ("currency",),
    "subtotal": ("subtotal",),
    "cgst_rate": ("cgst_rate",),
    "cgst": ("cgst",),
    "sgst_rate": ("sgst_rate",),
    "sgst": ("sgst",),
    "igst_rate": ("igst_rate",),
    "igst": ("igst",),
    "tax_total": ("tax_total", "tax"),
    "grand_total": ("grand_total", "total"),
    "total_in_words": ("total_in_words", "amount_in_words"),
}


def text_value(value: object) -> str | None:
    return (value.strip() or None) if isinstance(value, str) else None


def confidence_value(annotation: object) -> Decimal | None:
    value = annotation.get("confidence") if isinstance(annotation, dict) else None
    if isinstance(value, bool) or not isinstance(value, (str, int, float, Decimal)):
        return None
    try:
        score = Decimal(str(value))
    except InvalidOperation:
        return None
    return score if score.is_finite() and 0 <= score <= 1 else None


def map_invoice(payload: dict, context: InvoiceContext, *, document_sha256: str | None = None) -> ExtractedInvoice:
    fields = payload["result"]
    annotations = payload.get("annotations")
    annotations = annotations if isinstance(annotations, dict) else {}
    mapped = {
        "acceptance_date": context.acceptance_date,
        "written_agreement": context.written_agreement,
        "document_sha256": document_sha256,
    }
    scores = {}
    for destination, sources in SOURCE_FIELDS.items():
        # An explicit empty canonical field stays missing, even alongside a legacy alias.
        source = next((name for name in sources if name in fields), sources[0])
        value = text_value(fields.get(source))
        annotation = annotations.get(source)
        score = confidence_value(annotation)
        if annotation is not None and score is None:
            value = None
        if destination == "total_in_words" and value is None and fields.get(source) not in (None, ""):
            value = ""
        mapped[destination] = value
        if score is not None and value is not None:
            scores[destination] = score

    printed_date = mapped["invoice_date"]
    if printed_date is not None and not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", printed_date):
        mapped["invoice_date"] = None
    currency = mapped["currency"]
    if currency is not None:
        mapped["currency"] = "INR" if currency.casefold() in {"₹", "rs", "rs.", "inr"} else currency.upper()

    observed_bank = fields.get("bank_reference")
    bank_annotation = annotations.get("bank_reference")
    bank_score = confidence_value(bank_annotation)
    if observed_bank in (None, "") or (
        isinstance(observed_bank, str)
        and observed_bank.strip() == context.confirmed_bank_reference
        and (bank_annotation is None or bank_score is not None)
    ):
        mapped["bank_reference"] = context.confirmed_bank_reference
        if observed_bank and bank_score is not None:
            scores["bank_reference"] = bank_score

    items = fields.get("line_items")
    line_annotations = annotations.get("line_items")
    if isinstance(items, list) and 0 < len(items) <= 500 and all(isinstance(line, dict) for line in items):
        mapped["lines"] = [{key: text_value(line.get(key)) for key in ("quantity", "unit_price")} for line in items]
        if isinstance(line_annotations, list):
            leaves = [
                row[key] for row in line_annotations if isinstance(row, dict)
                for key in ("quantity", "unit_price") if key in row
            ]
            line_scores = [confidence_value(leaf) for leaf in leaves]
            if any(score is None for score in line_scores):
                mapped.pop("lines")
            elif line_scores:
                scores["lines"] = min(line_scores)

    mapped["confidence"] = scores or None
    try:
        return ExtractedInvoice.model_validate(mapped)
    except ValidationError as exc:
        # Preserve an invalid line as a missing line set, never a shortened invoice.
        # Keep the provider's unmodified evidence in the document job record.
        for invalid in {error["loc"][0] for error in exc.errors(include_input=False)}:
            if invalid == "total_in_words":
                mapped[invalid] = ""  # An invalid supplied written amount requires review.
            else:
                mapped.pop(invalid)
        return ExtractedInvoice.model_validate(mapped)
