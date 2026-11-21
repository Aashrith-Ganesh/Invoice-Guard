"""Invoice extraction adapters.

`DemoExtractor` is the offline stand-in: it reads the extraction embedded in a synthetic demo PDF.
A live Sarvam Document Intelligence adapter plugs in behind the same `Extractor` protocol.
Any PDF without a readable payload comes back as a failed extraction, which lands on hold for a person.
"""
import asyncio

from app.core.exceptions import reject
from app.integrations.sarvam.documents import fetch_extraction, sarvam_request, submit_extraction
from app.integrations.sarvam.invoice_mapping import InvoiceContext, map_invoice
from app.integrations.sarvam.demo_pdf import read_payload
from app.integrations.sarvam.types import Extraction

_TEXT_LIMIT = 300


def _text(value: object) -> str:
    return str(value)[:_TEXT_LIMIT] if value is not None else ""


def clean_display(raw: object) -> dict:
    """Keep only known, size-limited display fields from an untrusted extraction."""
    if not isinstance(raw, dict):
        return {}
    items = []
    raw_items = raw.get("items")
    for item in raw_items[:200] if isinstance(raw_items, list) else []:
        if isinstance(item, dict):
            items.append({key: _text(item.get(key)) for key in ("description", "quantity", "unit_price", "amount")})
    return {
        "trade_name": _text(raw.get("trade_name")),
        "vendor_address": _text(raw.get("vendor_address")),
        "language": _text(raw.get("language") or "en")[:5],
        "handwritten": raw.get("handwritten") is True,
        "amount_in_words": _text(raw.get("amount_in_words")),
        "items": items,
    }


class DemoExtractor:
    name = "demo"

    def extract(self, content: bytes, filename: str) -> Extraction:
        payload = read_payload(content)
        if payload is None or not isinstance(payload.get("invoice"), dict):
            return Extraction(provider=self.name, invoice=None,
                              error="No machine-readable invoice found in this PDF.")
        return Extraction(provider=self.name, invoice=payload["invoice"], display=clean_display(payload.get("display")))


async def extract_live(content: bytes, context: InvoiceContext) -> Extraction:
    # Wait outside any database transaction. The separate job API supports asynchronous polling.
    try:
        async with asyncio.timeout(45):
            job_id, _ = await submit_extraction(content, request=sarvam_request)
            status, result = await fetch_extraction(job_id, request=sarvam_request)
            while status in {"pending", "running"}:
                await asyncio.sleep(1)
                status, result = await fetch_extraction(job_id, request=sarvam_request)
    except TimeoutError:
        raise reject(504, "EXTRACTION_TIMEOUT", "Sarvam extraction timed out.") from None
    if status != "completed" or result is None:
        return Extraction("sarvam-vision", None, error="The extraction did not complete.", provider_result=result)
    mapped = map_invoice(result, context)
    fields = result["result"]
    display = clean_display({"items": fields.get("line_items"), "amount_in_words": mapped.total_in_words})
    return Extraction("sarvam-vision", mapped.model_dump(mode="json", exclude_none=True), display,
                      provider_result=result)
