import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import AuditLog

ROUTE = "/api/v1/workspace/balance"


def test_owner_adjusts_balance_and_records_audit(api):
    client, engine = api
    old = client.get("/api/v1/workspace").json()["cash_available"]
    payload = {"expected_balance": old, "cash_available": "135.09"}
    updated = client.patch(ROUTE, json=payload)
    assert updated.status_code == 200
    assert updated.json()["cash_available"] == "135.09"
    assert client.get("/api/v1/workspace").json()["cash_available"] == "135.09"
    assert client.patch(ROUTE, json=payload).status_code == 409
    with Session(engine) as session:
        event = session.scalar(select(AuditLog).where(AuditLog.action == "cash_balance_adjusted"))
        assert event.details["new_cash_minor"] == 13509
        assert event.details["owner"] == "demo-owner"


@pytest.mark.parametrize(("bearer", "amount", "expected"), [
    ("test-service", "0", 403),
    ("test-owner", "-1", 422),
    ("test-owner", "1.123", 422),
])
def test_balance_adjustment_requires_owner_and_valid_amount(api, bearer, amount, expected):
    client, _ = api
    current = client.get("/api/v1/workspace").json()["cash_available"]
    assert client.patch(ROUTE, headers={"Authorization": f"Bearer {bearer}"},
                        json={"cash_available": amount, "expected_balance": current}).status_code == expected
    assert client.get("/api/v1/workspace").json()["cash_available"] == current
