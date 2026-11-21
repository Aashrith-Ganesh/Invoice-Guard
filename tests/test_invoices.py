from concurrent.futures import ThreadPoolExecutor

import pytest

VALIDATE = "/api/v1/invoices/validate"


def validate(api, invoice):
    response = api[0].post(VALIDATE, json=invoice)
    assert response.status_code == 200, response.text
    return response.json()


def test_valid_invoice(api, invoice):
    result = validate(api, invoice)
    assert result["overall_status"] == "PASS"
    assert result["requires_owner_approval"]
    assert not result["payout_permitted"]
    assert result["payment_deadline"] == "2026-11-17"


@pytest.mark.parametrize(("changes", "status", "code"), [
    ({"grand_total": "117.00"}, "BLOCK", "ARITHMETIC_GRAND_TOTAL"),
    ({"invoice_number": None}, "HOLD", "MISSING_FIELDS"),
    ({"gstin": "99YYYYY0000Y0Z0"}, "BLOCK", "UNKNOWN_VENDOR"),
    ({"bank_reference": "demo:vendor-1:alternate"}, "HOLD", "BANK_CHANGE"),
    ({"confidence": {"grand_total": "0.4"}}, "HOLD", "LOW_CONFIDENCE"),
])
def test_individual_decisions(api, invoice, changes, status, code):
    result = validate(api, invoice | changes)
    assert result["overall_status"] == status
    assert code in result["risk_indicators"]


def test_duplicate_and_conflict(api, invoice):
    original = validate(api, invoice)
    duplicate = validate(api, invoice)
    assert duplicate["invoice_id"] == original["invoice_id"]
    assert "CONFIRMED_DUPLICATE" in duplicate["risk_indicators"]
    conflict = validate(api, invoice | {"invoice_number": "DEMO 100", "invoice_date": "2026-10-30"})
    assert conflict["overall_status"] == "HOLD"
    assert conflict["invoice_id"] == original["invoice_id"]
    assert "POSSIBLE_DUPLICATE" in conflict["risk_indicators"]


def test_concurrent_duplicate(api, invoice):
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: validate(api, invoice), range(2)))
    assert sorted(row["overall_status"] for row in results) == ["BLOCK", "PASS"]


def test_batch_isolates_malformed_items(api, invoice):
    result = api[0].post("/api/v1/invoices/batch-validate", json=[
        {"lines": "invalid"}, invoice, invoice,
    ]).json()
    assert [row["status_code"] for row in result] == [422, 200, 200]
    assert result[2]["decision"]["overall_status"] == "BLOCK"


def test_deadline_priority_and_insufficient_cash(api, invoice):
    client, _ = api
    urgent = validate(api, invoice)
    later = validate(api, invoice | {
        "invoice_number": "LATER",
        "invoice_date": "2026-11-02",
        "written_agreement": True,
    })
    assert later["payment_deadline"] == "2026-12-17"
    too_large = validate(api, invoice | {
        "invoice_number": "OVER-CASH", "lines": [{"quantity": "1", "unit_price": "100001.00"}],
        "subtotal": "100001.00", "grand_total": "118001.18",
        "cgst": "9000.09", "sgst": "9000.09", "tax_total": "18000.18",
    })
    assert too_large["overall_status"] == "HOLD"
    assert too_large["priority_score"] is None
    assert "INSUFFICIENT_CASH" in too_large["risk_indicators"]
    rows = client.get("/api/v1/invoices/priorities").json()
    assert {row["invoice_id"] for row in rows[:2]} == {urgent["invoice_id"], later["invoice_id"]}
    assert rows[-1]["invoice_id"] == too_large["invoice_id"]


def test_initial_cash_hold_requires_revalidation_after_funding(api, invoice):
    from sqlalchemy.orm import Session

    from app.models import Business

    client, engine = api
    with Session(engine) as session, session.begin():
        session.get(Business, 1).cash_minor = 100
    invoice_id = validate(api, invoice)["invoice_id"]
    with Session(engine) as session, session.begin():
        session.get(Business, 1).cash_minor = 100000
    url = f"/api/v1/invoices/{invoice_id}"
    assert client.get(url).json()["overall_status"] == "HOLD"
    assert client.post(f"{url}/revalidate").json()["overall_status"] == "PASS"


@pytest.mark.parametrize(("field", "wrong"), [
    ("subtotal", "101.00"), ("cgst", "8.00"), ("sgst", "10.00"),
    ("igst", "1.00"), ("tax_total", "19.00"),
])
def test_arithmetic_validates_each_component(api, invoice, field, wrong):
    result = validate(api, invoice | {field: wrong})
    assert result["overall_status"] == "BLOCK"
    assert f"ARITHMETIC_{field.upper()}" in result["risk_indicators"]
