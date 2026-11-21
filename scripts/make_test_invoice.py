"""Render the synthetic English test invoices in tests/fixtures/.

    python scripts/make_test_invoice.py

Needs Pillow (dev-only, not in requirements.txt). All names, GSTINs and bank details are fake.
Amounts are integer paise; each variant asserts its arithmetic before drawing.

    invoice_test_001.png   Unregistered supplier (GSTIN not in the seeded register)    -> BLOCK
    invoice_pass_002.png   Seeded "Fictional Vendor 3", consistent, under seeded cash  -> PASS with owner-confirmed bank
    invoice_math_003.png   Same vendor; printed subtotal != sum of lines (planted)     -> BLOCK ARITHMETIC_SUBTOTAL
"""
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

FIXTURES = Path(__file__).resolve().parent.parent / "tests" / "fixtures"
W, H = 1240, 1754  # A4 at 150 dpi
MARGIN = 80
INK, GREY, RULE = (20, 20, 20), (120, 120, 120), (190, 190, 190)
GST_HALF_RATE = 9  # CGST 9% + SGST 9% (intra-state)

# (description, HSN, qty, unit, rate in paise)
HARDWARE_40 = [("GI Pipe 25mm x 6m, medium class", "7306", 40, "Nos", 115000),
               ("PVC Elbow 25mm", "3917", 200, "Nos", 2250),
               ("Cement OPC 53 grade, 50 kg bag", "2523", 100, "Bags", 39500)]
HARDWARE_20 = [("GI Pipe 25mm x 6m, medium class", "7306", 20, "Nos", 115000),
               ("PVC Elbow 25mm", "3917", 100, "Nos", 2500),
               ("Cement OPC 53 grade, 50 kg bag", "2523", 40, "Bags", 40000)]
VENDOR_3 = ["Fictional Vendor 3", "7 Sample Lane, Demo Nagar", "Chennai 600000, Tamil Nadu",
            "GSTIN: 99ZZZZZ0002Z0Z0", "Phone: +91 00000 00000"]
PAYABLES_CO = ["Fictional Payables Co.", "45 Placeholder Road, Test Town", "Chennai 600000, Tamil Nadu",
               "GSTIN: 33PQRST5678K1Z2"]
VENDOR_3_BANK = [("Account Name", "Fictional Vendor 3"), ("Bank", "Example Bank (TEST), Demo Nagar Branch"),
                 ("Account No", "000098765432"), ("IFSC", "TEST0000003")]


@dataclass(frozen=True)
class Variant:
    file: str
    vendor: list[str]
    buyer: list[str]
    meta: list[tuple[str, str]]
    items: list[tuple[str, str, int, str, int]]
    bank: list[tuple[str, str]]
    total_in_words: str
    expected_total: int  # paise; guards the hand-written amount in words
    printed_subtotal: int | None = None  # set only to plant an arithmetic error
    itemised_tax: bool = False  # also print IGST @ 0% and a Total Tax line


VARIANTS = [
    Variant(
        file="invoice_test_001.png",
        vendor=["Sample Hardware Traders (TEST)", "12 Example Street, Demo Nagar", "Chennai 600000, Tamil Nadu",
                "GSTIN: 33ABCDE1234F1Z5", "Phone: +91 00000 00000"],
        buyer=["Demo Hardware Wholesale (TEST)", "45 Placeholder Road, Test Town", "Chennai 600000, Tamil Nadu",
               "GSTIN: 33PQRST5678K1Z2"],
        meta=[("Invoice No", "INV-TEST-001"), ("Invoice Date", "18-11-2026"), ("Due Date", "18-12-2026"),
              ("Place of Supply", "Tamil Nadu (33)")],
        items=HARDWARE_40,
        bank=[("Account Name", "Sample Hardware Traders"), ("Bank", "Example Bank (TEST), Demo Nagar Branch"),
              ("Account No", "000012345678"), ("IFSC", "TEST0000001")],
        total_in_words="Rupees One Lakh Six Thousand Two Hundred Only",
        expected_total=10620000,
    ),
    Variant(
        file="invoice_pass_002.png",
        vendor=VENDOR_3, buyer=PAYABLES_CO,
        meta=[("Invoice No", "INV-DEMO-002"), ("Invoice Date", "19-11-2026"), ("Due Date", "19-12-2026"),
              ("Place of Supply", "Tamil Nadu (33)")],
        items=HARDWARE_20, bank=VENDOR_3_BANK,
        total_in_words="Rupees Forty Eight Thousand Nine Hundred Seventy Only",
        expected_total=4897000, itemised_tax=True,
    ),
    Variant(
        file="invoice_math_003.png",
        vendor=VENDOR_3, buyer=PAYABLES_CO,
        meta=[("Invoice No", "INV-DEMO-003"), ("Invoice Date", "20-11-2026"), ("Due Date", "20-12-2026"),
              ("Place of Supply", "Tamil Nadu (33)")],
        items=HARDWARE_20, bank=VENDOR_3_BANK,
        total_in_words="Rupees Fifty Three Thousand One Hundred Only",
        expected_total=5310000, printed_subtotal=4500000, itemised_tax=True,
    ),
]


def font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    names = ["arialbd.ttf", "DejaVuSans-Bold.ttf"] if bold else ["arial.ttf", "DejaVuSans.ttf"]
    for name in names:
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default(size)


def inr(paise: int) -> str:
    """Indian digit grouping: 10620000 -> '1,06,200.00'."""
    rupees, p = divmod(paise, 100)
    s = str(rupees)
    head, tail = s[:-3], s[-3:]
    groups = []
    while len(head) > 2:
        groups.insert(0, head[-2:])
        head = head[:-2]
    if head:
        groups.insert(0, head)
    return ",".join(groups + [tail]) + f".{p:02d}"


def render(v: Variant) -> Path:
    lines = [(d, hsn, q, u, r, q * r) for d, hsn, q, u, r in v.items]
    line_sum = sum(amt for *_, amt in lines)
    subtotal = line_sum if v.printed_subtotal is None else v.printed_subtotal
    if v.printed_subtotal is not None:
        assert subtotal != line_sum, "a planted subtotal error must differ from the line sum"
    assert subtotal * GST_HALF_RATE % 100 == 0, "tax must be whole paise"
    cgst = sgst = subtotal * GST_HALF_RATE // 100
    total = subtotal + cgst + sgst
    assert total == v.expected_total, f"{v.file}: total_in_words is written for {inr(v.expected_total)}"

    img = Image.new("RGB", (W, H), "white")
    d = ImageDraw.Draw(img)
    f_title, f_h, f_b, f_s = font(40, True), font(24, True), font(22), font(18)
    right = W - MARGIN

    d.text((W // 2, 70), "TAX INVOICE", font=f_title, fill=INK, anchor="mt")
    d.line((MARGIN, 130, right, 130), fill=INK, width=2)

    y = 150
    d.text((MARGIN, y), v.vendor[0], font=f_h, fill=INK)
    for i, line in enumerate(v.vendor[1:], 1):
        d.text((MARGIN, y + i * 32 + 4), line, font=f_b, fill=INK)
    for i, (k, val) in enumerate(v.meta):
        d.text((760, y + i * 32), f"{k}:", font=f_b, fill=GREY)
        d.text((right, y + i * 32), val, font=f_b, fill=INK, anchor="ra")

    y = 330
    d.text((MARGIN, y), "Bill To", font=f_s, fill=GREY)
    d.text((MARGIN, y + 26), v.buyer[0], font=f_h, fill=INK)
    for i, line in enumerate(v.buyer[1:], 1):
        d.text((MARGIN, y + 26 + i * 32 + 4), line, font=f_b, fill=INK)

    # Items table
    y = 520
    cols = [(MARGIN, "#", "la"), (MARGIN + 50, "Description", "la"), (640, "HSN", "la"), (790, "Qty", "ra"),
            (810, "Unit", "la"), (1000, "Rate", "ra"), (right, "Amount", "ra")]
    d.rectangle((MARGIN, y, right, y + 44), fill=(238, 238, 238))
    for x, label, anchor in cols:
        d.text((x + (8 if anchor == "la" else -8), y + 22), label, font=f_h, fill=INK, anchor=anchor[0] + "m")
    y += 44
    for n, (desc, hsn, qty, unit, rate, amt) in enumerate(lines, 1):
        cells = [str(n), desc, hsn, str(qty), unit, inr(rate), inr(amt)]
        for (x, _, anchor), text in zip(cols, cells):
            d.text((x + (8 if anchor == "la" else -8), y + 28), text, font=f_b, fill=INK, anchor=anchor[0] + "m")
        y += 56
        d.line((MARGIN, y, right, y), fill=RULE, width=1)

    # Totals
    rows = [("Subtotal", subtotal, f_b), (f"CGST @ {GST_HALF_RATE}%", cgst, f_b),
            (f"SGST @ {GST_HALF_RATE}%", sgst, f_b)]
    if v.itemised_tax:
        rows += [("IGST @ 0%", 0, f_b), ("Total Tax", cgst + sgst, f_b)]
    rows.append(("Total (INR)", total, f_h))
    y += 20
    for label, value, f in rows:
        if f is f_h:
            d.line((760, y, right, y), fill=INK, width=2)
            y += 10
        d.text((760, y), label, font=f, fill=INK)
        d.text((right - 8, y), inr(value), font=f, fill=INK, anchor="ra")
        y += 38

    y += 20
    d.text((MARGIN, y), "Amount in words:", font=f_s, fill=GREY)
    d.text((MARGIN, y + 26), v.total_in_words, font=f_h, fill=INK)

    # Bank details
    y += 110
    d.rectangle((MARGIN, y, 760, y + 200), outline=INK, width=2)
    d.text((MARGIN + 20, y + 16), "Bank Details (for payment)", font=f_h, fill=INK)
    for i, (k, val) in enumerate(v.bank):
        d.text((MARGIN + 20, y + 62 + i * 32), f"{k}:", font=f_b, fill=GREY)
        d.text((MARGIN + 210, y + 62 + i * 32), val, font=f_b, fill=INK)

    d.text((right, y + 120), f"For {v.vendor[0]}", font=f_b, fill=INK, anchor="ra")
    d.line((right - 300, y + 185, right, y + 185), fill=INK, width=1)
    d.text((right, y + 192), "Authorised Signatory", font=f_s, fill=GREY, anchor="ra")

    d.line((MARGIN, H - 110, right, H - 110), fill=RULE, width=1)
    d.text((W // 2, H - 80), "SYNTHETIC TEST INVOICE - fictional data for software testing only. Not a real document.",
           font=f_s, fill=GREY, anchor="mt")

    out = FIXTURES / v.file
    out.parent.mkdir(parents=True, exist_ok=True)
    img.save(out, optimize=True)
    print(f"Wrote {out} ({out.stat().st_size} bytes); total {inr(total)}")
    return out


def main() -> None:
    for variant in VARIANTS:
        render(variant)


if __name__ == "__main__":
    main()
