from uuid import uuid4

from app.api import document_routes
from app.agent_framework import orchestrator


def test_vendor_chat_uses_business_scope(api, monkeypatch):
    client, _ = api
    async def chat(payload):
        if payload["messages"][-1]["role"] == "tool":
            return {"content": "Lookup complete"}
        return {"tool_calls": [{"id": "v1", "function": {
            "name": "get_vendor", "arguments": '{"vendor_id":1}'}}]}
    monkeypatch.setattr(orchestrator, "complete_chat", chat)
    body = {"agent_id": "vendor_agent", "input": {"content": "Find vendor 1"}}
    run = client.post("/api/v1/agent-runs", json=body)
    assert run.json()["outputs"][0]["data"]["vendor"]["id"] == 1
    assert client.get("/api/v1/agent-runs", headers={"Authorization": ""}).status_code == 401


def test_document_job_requires_ownership(api, monkeypatch):
    client, engine = api
    from app.models import Business
    from sqlalchemy.orm import Session
    job_id = uuid4()
    calls = []
    async def provider(method, path, **kwargs):
        calls.append(path)
        return {"job_id": str(job_id), "status": "pending"}
    monkeypatch.setattr(document_routes, "sarvam_request", provider)
    path = "/api/agents/sarvam/invoices"
    response = client.post(path, files={"file": ("test.pdf", b"%PDF-synthetic")})
    assert response.status_code == 202
    assert client.get(f"{path}/{job_id}").json()["status"] == "pending"
    with Session(engine) as session:
        session.add(Business(id=2, name="Second synthetic tenant", cash_minor=0))
        session.commit()
    assert client.get(f"{path}/{job_id}", headers={"Authorization": "Bearer other-owner"}).status_code == 404
    assert len(calls) == 2


def complete_result(invoice):
    result = {key: value for key, value in invoice.items()
              if key not in {"legal_name", "gstin", "lines", "acceptance_date", "written_agreement"}}
    return {
        "result": result | {
            "supplier_legal_name": invoice["legal_name"],
            "supplier_gstin": invoice["gstin"],
            "buyer_gstin": "unrelated",
            "line_items": [line | {"description": "Synthetic item"} for line in invoice["lines"]],
            "total_in_words": "Rupees one hundred and eighteen only",
        },
        "annotations": {"grand_total": {"confidence": 0.98, "sources": []}},
    }


def test_completed_sarvam_invoice_maps_and_preserves_original(api, invoice, monkeypatch):
    from app.models.document_job import DocumentJob
    from sqlalchemy.orm import Session

    client, engine = api
    job_id = uuid4()
    extraction = complete_result(invoice)

    async def provider(method, path, **kwargs):
        if method == "POST":
            return {"job_id": str(job_id), "status": "pending"}
        if path.endswith("/status"):
            return {"status": "completed"}
        return extraction

    monkeypatch.setattr(document_routes, "sarvam_request", provider)
    path = "/api/agents/sarvam/invoices"
    assert client.post(path, files={"file": ("demo.pdf", b"%PDF-synthetic")}).status_code == 202
    context = {key: invoice[key] for key in ("acceptance_date", "written_agreement")}
    context["confirmed_bank_reference"] = invoice["bank_reference"]
    validate_url = f"{path}/{job_id}/validate"
    denied = client.post(validate_url, json=context, headers={"Authorization": "Bearer test-service"})
    assert denied.status_code == 403
    response = client.post(validate_url, json=context)
    assert response.status_code == 200, response.text
    decision = response.json()
    assert decision["overall_status"] == "PASS"
    assert not decision["payout_permitted"]
    with Session(engine) as session:
        assert session.get(DocumentJob, str(job_id)).original_extraction == extraction


def test_mapper_does_not_infer_dates_taxes_bank_or_agreement(invoice):
    from app.integrations.sarvam.invoice_mapping import InvoiceContext, map_invoice

    payload = complete_result(invoice)
    payload["result"].update(invoice_date="01/11/2026", igst="", igst_rate="",
                             grand_total=118.00, acceptance_date="2026-11-02", written_agreement=True)
    mapped = map_invoice(payload, InvoiceContext())
    assert mapped.invoice_date is mapped.igst is mapped.igst_rate is mapped.grand_total is None
    assert mapped.acceptance_date is mapped.written_agreement is mapped.bank_reference is None


def test_mapper_keeps_exact_decimals_and_maps_low_leaf_confidence(invoice):
    from decimal import Decimal
    from app.integrations.sarvam.invoice_mapping import InvoiceContext, map_invoice

    payload = complete_result(invoice)
    payload["annotations"]["line_items"] = [{"quantity": {"confidence": "0.35"},
                                            "unit_price": {"confidence": 0.98}}]
    mapped = map_invoice(payload, InvoiceContext())
    assert str(mapped.grand_total) == "118.00"
    assert mapped.confidence == {"grand_total": Decimal("0.98"), "lines": Decimal("0.35")}
    assert mapped.total_in_words == "Rupees one hundred and eighteen only"


def test_mapper_drops_malformed_line_and_conflicting_bank(invoice):
    from app.integrations.sarvam.invoice_mapping import InvoiceContext, map_invoice

    payload = complete_result(invoice)
    payload["result"]["line_items"].append({"quantity": "two", "unit_price": "50.00"})
    payload["result"]["bank_reference"] = "demo:vendor-1:alternate"
    mapped = map_invoice(payload, InvoiceContext(confirmed_bank_reference=invoice["bank_reference"]))
    assert mapped.lines is None
    assert mapped.bank_reference is None


def test_validation_rejects_partial_or_other_tenant_job(api, invoice, monkeypatch):
    from app.models import Business
    from sqlalchemy.orm import Session

    client, engine = api
    job_id = uuid4()
    calls = []

    async def provider(method, path, **kwargs):
        calls.append(path)
        if method == "POST":
            return {"job_id": str(job_id), "status": "pending"}
        if path.endswith("/status"):
            return {"status": "partially_completed"}
        return complete_result(invoice)

    monkeypatch.setattr(document_routes, "sarvam_request", provider)
    path = "/api/agents/sarvam/invoices"
    assert client.post(path, files={"file": ("demo.pdf", b"%PDF-synthetic")}).status_code == 202
    with Session(engine) as session, session.begin():
        session.add(Business(id=2, name="Other synthetic business", cash_minor=0))
    url = f"{path}/{job_id}/validate"
    assert client.post(url, json={}, headers={"Authorization": "Bearer other-owner"}).status_code == 404
    assert len(calls) == 1
    response = client.post(url, json={})
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "EXTRACTION_NOT_COMPLETE"


def test_sarvam_translation_uses_display_only_contract(api, monkeypatch):
    client, _ = api

    async def provider(method, path, **kwargs):
        assert (method, path) == ("POST", "/translate")
        assert kwargs["json"]["model"] == "sarvam-translate:v1"
        return {"translated_text": "சரிபார்ப்பு தேவை"}

    monkeypatch.setattr(document_routes, "sarvam_request", provider)
    response = client.post("/api/agents/sarvam/translate",
                           json={"text": "Review required", "target_language": "ta-IN"})
    assert response.status_code == 200
    assert response.json() == {"text": "சரிபார்ப்பு தேவை", "language": "ta-IN"}


def test_invalid_written_amount_is_preserved_as_review_marker(invoice):
    from app.integrations.sarvam.invoice_mapping import InvoiceContext, map_invoice

    payload = complete_result(invoice)
    payload["result"]["total_in_words"] = ["Unusable transcription"]
    assert map_invoice(payload, InvoiceContext()).total_in_words == ""
