"""Render the synthetic English test invoice at tests/fixtures/invoice_test_001.png.

    python scripts/make_test_invoice.py

Needs Pillow (dev-only, not in requirements.txt). All names, GSTINs and bank details are fake.
Amounts are integer paise; the script asserts the arithmetic before drawing, so the image is internally consistent.
"""
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

OUT = Path(__file__).resolve().parent.parent / "tests" / "fixtures" / "invoice_test_001.png"
W, H = 1240, 1754  # A4 at 150 dpi
MARGIN = 80
INK, GREY, RULE = (20, 20, 20), (120, 120, 120), (190, 190, 190)

VENDOR = ["Sample Hardware Traders (TEST)", "12 Example Street, Demo Nagar", "Chennai 600000, Tamil Nadu",
          "GSTIN: 33ABCDE1234F1Z5", "Phone: +91 00000 00000"]
BUYER = ["Demo Hardware Wholesale (TEST)", "45 Placeholder Road, Test Town", "Chennai 600000, Tamil Nadu",
         "GSTIN: 33PQRST5678K1Z2"]
META = [("Invoice No", "INV-TEST-001"), ("Invoice Date", "18-11-2026"), ("Due Date", "18-12-2026"),
        ("Place of Supply", "Tamil Nadu (33)")]
# (description, HSN, qty, unit, rate in paise)
ITEMS = [("GI Pipe 25mm x 6m, medium class", "7306", 40, "Nos", 115000),
         ("PVC Elbow 25mm", "3917", 200, "Nos", 2250),
         ("Cement OPC 53 grade, 50 kg bag", "2523", 100, "Bags", 39500)]
GST_HALF_RATE = 9  # CGST 9% + SGST 9% (intra-state)
TOTAL_IN_WORDS = "Rupees One Lakh Six Thousand Two Hundred Only"
BANK = [("Account Name", "Sample Hardware Traders"), ("Bank", "Example Bank (TEST), Demo Nagar Branch"),
        ("Account No", "000012345678"), ("IFSC", "TEST0000001")]


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


def main() -> None:
    lines = [(d, hsn, q, u, r, q * r) for d, hsn, q, u, r in ITEMS]
    subtotal = sum(amt for *_, amt in lines)
    cgst = sgst = subtotal * GST_HALF_RATE // 100
    total = subtotal + cgst + sgst
    assert subtotal * GST_HALF_RATE % 100 == 0, "tax must be whole paise"
    assert total == 10620000, "TOTAL_IN_WORDS is written for Rs 1,06,200.00; update both together"

    img = Image.new("RGB", (W, H), "white")
    d = ImageDraw.Draw(img)
    f_title, f_h, f_b, f_s = font(40, True), font(24, True), font(22), font(18)
    right = W - MARGIN

    d.text((W // 2, 70), "TAX INVOICE", font=f_title, fill=INK, anchor="mt")
    d.line((MARGIN, 130, right, 130), fill=INK, width=2)

    y = 150
    d.text((MARGIN, y), VENDOR[0], font=f_h, fill=INK)
    for i, line in enumerate(VENDOR[1:], 1):
        d.text((MARGIN, y + i * 32 + 4), line, font=f_b, fill=INK)
    for i, (k, v) in enumerate(META):
        d.text((760, y + i * 32), f"{k}:", font=f_b, fill=GREY)
        d.text((right, y + i * 32), v, font=f_b, fill=INK, anchor="ra")

    y = 330
    d.text((MARGIN, y), "Bill To", font=f_s, fill=GREY)
    d.text((MARGIN, y + 26), BUYER[0], font=f_h, fill=INK)
    for i, line in enumerate(BUYER[1:], 1):
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
    y += 20
    for label, value, f in [("Subtotal", subtotal, f_b), (f"CGST @ {GST_HALF_RATE}%", cgst, f_b),
                            (f"SGST @ {GST_HALF_RATE}%", sgst, f_b), ("Total (INR)", total, f_h)]:
        if f is f_h:
            d.line((760, y, right, y), fill=INK, width=2)
            y += 10
        d.text((760, y), label, font=f, fill=INK)
        d.text((right - 8, y), inr(value), font=f, fill=INK, anchor="ra")
        y += 38

    y += 20
    d.text((MARGIN, y), "Amount in words:", font=f_s, fill=GREY)
    d.text((MARGIN, y + 26), TOTAL_IN_WORDS, font=f_h, fill=INK)

    # Bank details
    y += 110
    d.rectangle((MARGIN, y, 760, y + 200), outline=INK, width=2)
    d.text((MARGIN + 20, y + 16), "Bank Details (for payment)", font=f_h, fill=INK)
    for i, (k, v) in enumerate(BANK):
        d.text((MARGIN + 20, y + 62 + i * 32), f"{k}:", font=f_b, fill=GREY)
        d.text((MARGIN + 210, y + 62 + i * 32), v, font=f_b, fill=INK)

    d.text((right, y + 120), "For Sample Hardware Traders (TEST)", font=f_b, fill=INK, anchor="ra")
    d.line((right - 300, y + 185, right, y + 185), fill=INK, width=1)
    d.text((right, y + 192), "Authorised Signatory", font=f_s, fill=GREY, anchor="ra")

    d.line((MARGIN, H - 110, right, H - 110), fill=RULE, width=1)
    d.text((W // 2, H - 80), "SYNTHETIC TEST INVOICE - fictional data for software testing only. Not a real document.",
           font=f_s, fill=GREY, anchor="mt")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    img.save(OUT, optimize=True)
    print(f"Wrote {OUT} ({OUT.stat().st_size} bytes); total {inr(total)}")


if __name__ == "__main__":
    main()
