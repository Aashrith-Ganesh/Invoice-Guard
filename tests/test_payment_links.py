from concurrent.futures import ThreadPoolExecutor

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import AuditLog, Business, Invoice, Payment
from test_invoices import validate
from test_payments import approve, issue

ROOT = "/api/v1/payments"
PUBLIC = "/api/v1/simulated-payment"


def create(client, invoice_id, approval_id, **kwargs):
    return client.post(f"{ROOT}/links", json={"invoice_id": invoice_id, "approval_id": approval_id}, **kwargs)


def public(client, operation, token):
    return client.post(f"{PUBLIC}/{operation}", json={"token": token}, headers={"Authorization": ""})


def test_link_requires_owner_and_confirmed_approval(api, invoice):
    client, _ = api
    invoice_id = validate(api, invoice)["invoice_id"]
    challenge = issue(client, invoice_id).json()
    approval_id = challenge["approval_id"]
    assert create(client, invoice_id, approval_id).status_code == 409
    assert create(client, invoice_id, approval_id, headers={"Authorization": "Bearer test-service"}).status_code == 403


def test_link_lifecycle_and_concurrent_replay(api, invoice):
    client, engine = api
    invoice_id = validate(api, invoice)["invoice_id"]
    approval_id = approve(client, invoice_id)
    first = create(client, invoice_id, approval_id)
    assert first.status_code == 201
    link = first.json()
    assert link["path"].startswith("/app/pay.html#")
    token = link["path"].split("#")[1]
    again = create(client, invoice_id, approval_id)
    assert again.status_code == 200 and again.json() == link
    with Session(engine) as session:
        assert session.scalar(select(func.count()).select_from(Payment)) == 0
    assert public(client, "status", token).json()["status"] == "READY"
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: public(client, "simulate", token), range(2)))
    assert all(response.status_code == 200 for response in results)
    paid = results[0].json()
    assert paid == results[1].json() == public(client, "status", token).json()
    assert paid["status"] == "SUCCESS" and paid["payment_reference"] == link["payment_reference"]
    assert paid["vendor_name"] == invoice["legal_name"] and paid["amount"] == "118.00"
    assert not {"token", "approval_id", "bank_reference", "bank_account_id"} & paid.keys()
    with Session(engine) as session:
        assert session.scalar(select(func.count()).select_from(Payment)) == 1
        assert session.get(Business, 1).cash_minor == 10000000 - 11800
        assert session.scalar(select(func.count()).select_from(AuditLog).where(
            AuditLog.action == "hosted_simulated_payment_completed")) == 1


def test_link_rechecks_terms_and_rejects_expired_or_invalid_token(api, invoice):
    from app.models.payment_link import PaymentLink

    client, engine = api
    invoice_id = validate(api, invoice)["invoice_id"]
    link = create(client, invoice_id, approve(client, invoice_id)).json()
    token = link["path"].split("#")[1]
    assert public(client, "status", "bad-token").status_code == 422
    tampered = token[:-1] + ("0" if token[-1] != "0" else "1")
    assert public(client, "status", tampered).status_code == 404
    with Session(engine) as session, session.begin():
        session.get(Invoice, invoice_id).amount_minor += 1
    assert public(client, "simulate", token).status_code == 409
    with Session(engine) as session, session.begin():
        session.scalar(select(PaymentLink)).expires_at = "2000-01-01T00:00:00.000000+00:00"
    assert public(client, "status", token).status_code == 410
    assert public(client, "simulate", token).status_code == 410
    with Session(engine) as session:
        assert session.scalar(select(func.count()).select_from(Payment)) == 0


def test_create_link_uses_configured_hosted_origin(api, invoice):
    from dataclasses import replace

    client, _ = api
    client.app.state.settings = replace(client.app.state.settings, hosted_payment_origin="http://localhost:8001")
    invoice_id = validate(api, invoice)["invoice_id"]
    result = create(client, invoice_id, approve(client, invoice_id))
    assert result.status_code == 201
    assert result.json()["path"].startswith("http://localhost:8001/app/pay.html#")


def test_hosted_listener_only_exposes_public_simulator(api):
    from fastapi.testclient import TestClient

    from app.hosted_payment import hosted_only

    client, _ = api
    with TestClient(hosted_only(client.app)) as hosted:
        assert hosted.get("/app/").status_code == 404
        assert hosted.get("/api/v1/workspace").status_code == 404
        assert hosted.post("/api/v1/payments/links", json={}).status_code == 404
        assert hosted.post("/api/v1/simulated-payment/status", json={"token": "invalid"}).status_code == 422
