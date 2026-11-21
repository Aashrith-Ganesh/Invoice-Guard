from dataclasses import replace

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Approval, AuditLog, Business, Document, Invoice, InvoiceValidation, Payment, Vendor
from app.models.payment_link import PaymentLink
from app.services.samples import sample_pdf
from test_payment_links import create, public
from test_payments import approve

ROUTE = "/api/v1/documents/clear"


def upload(client, token):
    return client.post("/api/v1/documents", files={"file": ("demo.pdf", sample_pdf("clean-printed"))},
                       headers={"Authorization": f"Bearer {token}"}).json()


def test_owner_clears_only_demo_tenant_bills_and_preserves_balance(api):
    client, engine = api
    client.app.state.document_extractor_mode = "demo"
    with Session(engine) as session, session.begin():
        session.add(Business(id=2, name="Other business", cash_minor=9000))
        session.add(AuditLog(business_id=1, action="cash_balance_adjusted", entity_id=1))
        for action in ("document_skip_tax", "document_process_demo", "document_return_to_review"):
            session.add(AuditLog(business_id=1, action=action, entity_id=1))
    own = upload(client, "test-owner")
    other = upload(client, "other-owner")
    amount = client.get("/api/v1/workspace").json()["cash_available"]
    assert own["decision"]["overall_status"] == "PASS", own["decision"]["risk_indicators"]
    invoice_id = own["invoice_id"]
    link = create(client, invoice_id, approve(client, invoice_id)).json()
    token = link["path"].split("#")[1]
    assert public(client, "simulate", token).json()["status"] == "SUCCESS"
    reduced = client.get("/api/v1/workspace").json()["cash_available"]
    assert reduced != amount

    denied = client.post(ROUTE, headers={"Authorization": "Bearer test-service"})
    assert denied.status_code == 403
    result = client.post(ROUTE)
    assert result.status_code == 200 and result.json() == {"cleared": 1}
    assert client.get("/api/v1/documents").json() == []
    assert client.get("/api/v1/workspace").json()["cash_available"] == reduced
    assert client.get(f"/api/v1/documents/{other['document_id']}",
                      headers={"Authorization": "Bearer other-owner"}).status_code == 200
    assert public(client, "simulate", token).status_code == 404
    with Session(engine) as session:
        for model in (Document, Invoice, InvoiceValidation, Approval, Payment, PaymentLink):
            assert session.scalar(select(func.count()).select_from(model).where(model.business_id == 1)) == 0
        assert session.scalar(select(func.count()).select_from(Vendor).where(Vendor.business_id == 1)) == 10
        actions = session.scalars(select(AuditLog.action).where(AuditLog.business_id == 1)).all()
        assert set(actions) == {"cash_balance_adjusted", "demo_bills_cleared"}


def test_clear_is_disabled_outside_demo_mode(api):
    client, _ = api
    client.app.state.document_extractor_mode = "sarvam"
    settings = client.app.state.settings
    client.app.state.settings = replace(settings, enable_demo_bill_reset=False)
    assert client.get("/api/v1/workspace").json()["can_clear_bills"] is False
    assert client.post(ROUTE).status_code == 403
    client.app.state.settings = replace(settings, enable_demo_bill_reset=True)
    assert client.get("/api/v1/workspace").json()["can_clear_bills"] is True
    assert client.post(ROUTE).json() == {"cleared": 0}
