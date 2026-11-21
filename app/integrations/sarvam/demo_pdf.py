"""Synthetic demo invoice PDFs.

A demo PDF is a normal, viewable PDF plus one comment line carrying the extraction Sarvam would return
for it (`%PS3-DEMO-EXTRACTION <base64 json>`). PDF viewers ignore comments. The demo extractor reads that
line so the whole flow runs offline; the real Sarvam adapter reads the rendered page instead.
"""
import base64
import json
import re

MARKER = b"%PS3-DEMO-EXTRACTION "
_PAYLOAD = re.compile(rb"%PS3-DEMO-EXTRACTION ([A-Za-z0-9+/=]{1,2000000})")
MAX_PAYLOAD_CHARS = 2_000_000


def read_payload(content: bytes) -> dict | None:
    match = _PAYLOAD.search(content[:4_000_000])
    if not match:
        return None
    try:
        payload = json.loads(base64.b64decode(match.group(1), validate=True))
    except (ValueError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def _escape(text: str) -> str:
    safe = text.encode("latin-1", "replace").decode("latin-1")
    return safe.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


class _Page:
    def __init__(self) -> None:
        self.ops: list[str] = []

    def text(self, x: float, y: float, value: str, size: float = 10, font: str = "F1", gray: float = 0.1) -> None:
        self.ops.append(f"{gray} g BT /{font} {size} Tf {x:.1f} {y:.1f} Td ({_escape(value)}) Tj ET")

    def right(self, x: float, y: float, value: str, size: float = 10, font: str = "F1") -> None:
        width = len(value) * size * (0.56 if font == "F2" else 0.5)
        self.text(x - width, y, value, size, font)

    def rect(self, x: float, y: float, w: float, h: float, fill: float | None = None) -> None:
        if fill is not None:
            self.ops.append(f"{fill} g {x} {y} {w} {h} re f")
        else:
            self.ops.append(f"0.75 G 0.6 w {x} {y} {w} {h} re S")

    def line(self, x1: float, y1: float, x2: float, y2: float, gray: float = 0.75) -> None:
        self.ops.append(f"{gray} G 0.6 w {x1} {y1} m {x2} {y2} l S")


def _money(value: str) -> str:
    whole, _, cents = f"{float(value):.2f}".partition(".")
    if len(whole) > 3:  # Indian grouping: 12,34,567
        head, tail = whole[:-3], whole[-3:]
        head = ",".join(re.findall(r"\d{1,2}(?=(?:\d{2})*$)", head))
        whole = f"{head},{tail}"
    return f"Rs. {whole}.{cents}"


def render(payload: dict) -> bytes:
    invoice, display = payload.get("invoice") or {}, payload.get("display") or {}
    hand = bool(display.get("handwritten"))
    body, bold = ("F3", "F3") if hand else ("F1", "F2")
    page = _Page()
    page.rect(0, 0, 595, 842, fill=0.995 if not hand else 0.97)
    if not hand:
        page.rect(40, 742, 515, 64, fill=0.93)
    page.text(52, 782, display.get("trade_name") or invoice.get("legal_name") or "Vendor", 18, bold)
    page.text(52, 764, f"{invoice.get('legal_name', '')}  |  GSTIN {invoice.get('gstin', '-')}", 9, body, 0.3)
    page.text(52, 750, display.get("vendor_address", ""), 9, body, 0.3)
    page.right(543, 782, "TAX INVOICE" if not hand else "BILL", 14, bold)
    page.right(543, 764, f"No. {invoice.get('invoice_number', '-')}", 10, body)
    page.right(543, 750, f"Date {invoice.get('invoice_date', '-')}", 10, body)

    page.text(52, 712, "Bill to", 9, bold, 0.4)
    page.text(52, 698, "Fictional Weddings & Events, Chennai", 10, body)
    if display.get("language_note"):
        page.right(543, 712, display["language_note"], 9, body)

    y = 660
    page.rect(40, y - 6, 515, 22, fill=0.9 if not hand else 0.94)
    for x, label in ((52, "#"), (74, "Description")):
        page.text(x, y, label, 9, bold)
    for x, label in ((380, "Qty"), (460, "Rate"), (543, "Amount")):
        page.right(x, y, label, 9, bold)
    y -= 26
    for number, item in enumerate(display.get("items") or [], start=1):
        page.text(52, y, str(number), 10, body)
        page.text(74, y, item.get("description", ""), 10, body)
        page.right(380, y, str(item.get("quantity", "")), 10, body)
        page.right(460, y, _money(item.get("unit_price", "0")), 10, body)
        page.right(543, y, _money(item.get("amount", "0")), 10, body)
        page.line(40, y - 8, 555, y - 8, 0.88)
        y -= 24

    y -= 10
    rows = [("Subtotal", invoice.get("subtotal"))]
    for tax in ("cgst", "sgst", "igst"):
        if invoice.get(tax) not in (None, "0", "0.00"):
            rows.append((f"{tax.upper()} @ {invoice.get(tax + '_rate')}%", invoice.get(tax)))
    for label, value in rows:
        page.text(360, y, label, 10, body, 0.3)
        page.right(543, y, _money(value or "0"), 10, body)
        y -= 18
    page.rect(350, y - 8, 205, 26, fill=0.9 if not hand else 0.94)
    page.text(360, y, "Total payable", 11, bold)
    page.right(543, y, _money(invoice.get("grand_total") or "0"), 11, bold)
    y -= 34
    if display.get("amount_in_words"):
        page.text(52, y, f"In words: {display['amount_in_words']}", 9, body, 0.3)
        y -= 18

    page.text(52, 150, "Pay to", 9, bold, 0.4)
    page.text(52, 136, f"Bank reference: {invoice.get('bank_reference', '-')}", 10, body)
    page.line(380, 120, 543, 120, 0.5)
    page.right(543, 106, "Authorised signatory", 9, body)
    page.text(52, 60, "SYNTHETIC DEMO DOCUMENT - fictional vendor, not a real invoice.", 8, "F1", 0.55)

    stream = "\n".join(page.ops).encode("latin-1")
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Contents 4 0 R "
        b"/Resources << /Font << /F1 5 0 R /F2 6 0 R /F3 7 0 R >> >> >>",
        b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold /Encoding /WinAnsiEncoding >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Times-Italic /Encoding /WinAnsiEncoding >>",
    ]
    encoded = base64.b64encode(json.dumps(payload, ensure_ascii=False).encode()).decode()
    out = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n" + MARKER + encoded.encode() + b"\n")
    offsets = []
    for number, body_bytes in enumerate(objects, start=1):
        offsets.append(len(out))
        out += b"%d 0 obj\n" % number + body_bytes + b"\nendobj\n"
    xref = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objects) + 1)
    out += b"".join(b"%010d 00000 n \n" % offset for offset in offsets)
    out += b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (len(objects) + 1, xref)
    return bytes(out)
