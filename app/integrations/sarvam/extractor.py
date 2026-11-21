"""Invoice extraction adapters.

`DemoExtractor` is the offline stand-in: it reads the extraction embedded in a synthetic demo PDF.
A live Sarvam Document Intelligence adapter plugs in behind the same `Extractor` protocol.
Any PDF without a readable payload comes back as a failed extraction, which lands on hold for a person.
"""
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
    for item in (raw.get("items") or [])[:200]:
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
