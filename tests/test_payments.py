from concurrent.futures import ThreadPoolExecutor
from hmac import digest

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database.base import utc_now
from app.models import Business, Invoice, VendorBankAccount
from test_invoices import validate

ROOT = "/api/v1"


def issue(client, invoice_id, **kwargs):
    return client.post(f"{ROOT}/approvals", json={"invoice_id": invoice_id, **kwargs})


def confirm(client, token):
    return client.post(f"{ROOT}/approvals/confirm", json={"token": token})


def approve(client, invoice_id, **kwargs):
    created = issue(client, invoice_id, **kwargs)
    assert created.status_code == 201, created.text
    confirmed = confirm(client, created.json()["token"])
    assert confirmed.status_code == 200, confirmed.text
    return confirmed.json()["approval_id"]


def initiate(client, invoice_id, approval_id, key="test-key"):
    return client.post(f"{ROOT}/payments/initiate", json={
        "invoice_id": invoice_id, "approval_id": approval_id, "idempotency_key": key,
    })


def event(client, payment, status):
    payload = f'{{"external_reference":"{payment["external_reference"]}","status":"{status}"}}'
    signature = digest(b"test-webhook", payload.encode(), "sha256").hex()
    return client.post(f"{ROOT}/webhooks/payout", content=payload,
                       headers={"X-Simulator-Signature": signature})


def test_concurrent_idempotent_payment(api, invoice):
    client, engine = api
    invoice_id = validate(api, invoice)["invoice_id"]
    approval_id = approve(client, invoice_id)
    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(lambda _: initiate(client, invoice_id, approval_id), range(2)))
    assert {response.status_code for response in responses} == {200, 201}
    assert responses[0].json() == responses[1].json()
    assert responses[0].json()["status"] == "INITIATED"
    assert initiate(client, invoice_id, approval_id, "another-key").status_code == 409
    with Session(engine) as session:
        assert session.get(Business, 1).cash_minor == 10000000 - 11800


def test_owner_and_token_replay(api, invoice):
    client, _ = api
    invoice_id = validate(api, invoice)["invoice_id"]
    assert client.post(f"{ROOT}/approvals", json={"invoice_id": invoice_id},
                       headers={"Authorization": "Bearer test-service"}).status_code == 403
    token = issue(client, invoice_id).json()["token"]
    assert confirm(client, token).status_code == 200
    assert confirm(client, token).status_code == 409


def test_amount_mutation_invalidates_approval(api, invoice):
    client, engine = api
    invoice_id = validate(api, invoice)["invoice_id"]
    issued = issue(client, invoice_id).json()
    with Session(engine) as session, session.begin():
        session.get(Invoice, invoice_id).amount_minor += 1
    assert confirm(client, issued["token"]).status_code == 409


def test_cash_decrease_after_approval(api, invoice):
    client, engine = api
    invoice_id = validate(api, invoice)["invoice_id"]
    approval_id = approve(client, invoice_id)
    with Session(engine) as session, session.begin():
        session.get(Business, 1).cash_minor = 100
    assert initiate(client, invoice_id, approval_id).json()["error"]["code"] == "INSUFFICIENT_CASH"
    assert client.get(f"{ROOT}/invoices/{invoice_id}").json()["overall_status"] == "HOLD"


def test_bank_change_needs_verification_and_fresh_approval(api, invoice):
    client, engine = api
    invoice_id = validate(api, invoice)["invoice_id"]
    stale_token = issue(client, invoice_id).json()["token"]
    changed_id = validate(api, invoice | {
        "invoice_number": "DEMO-101", "invoice_date": "2026-11-02",
        "bank_reference": "demo:vendor-1:alternate",
    })["invoice_id"]
    assert issue(client, changed_id).status_code == 409
    with Session(engine) as session, session.begin():
        old = session.scalar(select(VendorBankAccount).where(
            VendorBankAccount.reference == "demo:vendor-1:current"))
        old.is_primary = False
        old.retired_at = utc_now()
        session.flush()
        new = session.scalar(select(VendorBankAccount).where(
            VendorBankAccount.reference == "demo:vendor-1:alternate"))
        new.is_primary = True
        new.verified_at = utc_now()
    assert confirm(client, stale_token).status_code == 409
    assert client.post(f"{ROOT}/invoices/{changed_id}/revalidate").json()["overall_status"] == "PASS"
    approval_id = approve(client, changed_id)
    assert initiate(client, changed_id, approval_id).status_code == 201


@pytest.mark.parametrize("status", ["UNKNOWN", "FAILED", "REVERSED"])
def test_no_blind_payment_retry(api, invoice, status):
    client, _ = api
    invoice_id = validate(api, invoice)["invoice_id"]
    approval_id = approve(client, invoice_id)
    payment = initiate(client, invoice_id, approval_id).json()
    if status == "REVERSED":
        assert event(client, payment, "SUCCESS").status_code == 200
    assert event(client, payment, status).json()["status"] == status
    assert initiate(client, invoice_id, approval_id, "new-key").status_code == 409
    assert issue(client, invoice_id).status_code == 409
    recovery = {"previous_payment_id": payment["payment_id"], "reason": "Owner reviewed the simulator result."}
    if status == "UNKNOWN":
        assert issue(client, invoice_id, **recovery).status_code == 409
        assert event(client, payment, "FAILED").json()["status"] == "FAILED"
    fresh = approve(client, invoice_id, **recovery)
    assert initiate(client, invoice_id, fresh, "new-key").status_code == 201


def test_unknown_vendor_has_no_approval(api, invoice):
    invoice_id = validate(api, invoice | {"gstin": "99YYYYY0000Y0Z0"})["invoice_id"]
    assert issue(api[0], invoice_id).status_code == 409


def test_webhook_has_separate_authentication(api):
    response = api[0].post(f"{ROOT}/webhooks/payout", json={"status": "SUCCESS"})
    assert response.status_code == 401


def test_invoice_view_approval_and_paid_flags(api, invoice):
    client, _ = api
    invoice_id = validate(api, invoice)["invoice_id"]
    url = f"{ROOT}/invoices/{invoice_id}"
    approval_id = approve(client, invoice_id)
    approved = client.get(url).json()
    assert approved["payout_permitted"]
    assert not approved["requires_owner_approval"]
    payment = initiate(client, invoice_id, approval_id).json()
    assert event(client, payment, "SUCCESS").status_code == 200
    paid = client.get(url).json()
    assert paid["overall_status"] == "PASS"
    assert not paid["payout_permitted"]
    assert not paid["requires_owner_approval"]


def test_original_invoice_can_be_rebound_after_trusted_rotation(api, invoice):
    from scripts.verify_demo_bank import verify_demo_bank

    client, engine = api
    invoice_id = validate(api, invoice)["invoice_id"]
    approval_id = approve(client, invoice_id)
    reference = "demo:vendor-1:alternate"
    verify_demo_bank(engine, business_id=1, vendor_id=1, reference=reference)
    url = f"{ROOT}/invoices/{invoice_id}"
    assert client.get(url).json()["overall_status"] == "HOLD"
    assert not client.get(url).json()["payout_permitted"]
    assert initiate(client, invoice_id, approval_id).status_code == 409
    rebound = client.post(f"{url}/revalidate", json={"bank_reference": reference})
    assert rebound.json()["overall_status"] == "PASS"
    assert initiate(client, invoice_id, approval_id).status_code == 409
    fresh = approve(client, invoice_id)
    assert initiate(client, invoice_id, fresh).status_code == 201


def test_cross_business_reads(api, invoice, monkeypatch):
    client, engine = api
    invoice_id = validate(api, invoice)["invoice_id"]
    approval_id = approve(client, invoice_id)
    payment = initiate(client, invoice_id, approval_id).json()
    with Session(engine) as session, session.begin():
        session.add(Business(id=2, name="Other Fictional Business", cash_minor=100000))
    headers = {"Authorization": "Bearer other-owner"}
    assert client.get(f"{ROOT}/invoices/{invoice_id}", headers=headers).status_code == 404
    assert client.get(f"{ROOT}/payments/{payment['payment_id']}", headers=headers).status_code == 404


def test_legacy_approval_cannot_start_a_new_payment(api, invoice):
    from app.models import Approval

    client, engine = api
    invoice_id = validate(api, invoice)["invoice_id"]
    approval_id = approve(client, invoice_id)
    with Session(engine) as session, session.begin():
        approval = session.get(Approval, approval_id)
        approval.owner_id = None
        approval.validation_run_id = None
    response = initiate(client, invoice_id, approval_id)
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "APPROVAL_REQUIRED"
