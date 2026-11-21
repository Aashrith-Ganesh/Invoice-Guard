from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.main import create_app
from app.models import Document
from app.services.samples import sample_pdf
from test_sarvam import complete_result


def test_merchant_sarvam_pipeline_uses_owner_verified_context(api, invoice, monkeypatch):
    from app.integrations.sarvam import extractor

    client, engine = api
    client.app.state.document_extractor_mode = "sarvam"
    job_id = str(uuid4())
    raw = complete_result(invoice)

    async def provider(method, path, **kwargs):
        if method == "POST":
            assert path == "/doc-ai/v1/job/extract"
            assert kwargs["files"]["file"][2] == "application/pdf"
            return {"job_id": job_id}
        return {"status": "completed"} if path.endswith("/status") else raw

    monkeypatch.setattr(extractor, "sarvam_request", provider)
    files = {"file": ("demo.pdf", sample_pdf("clean-printed"))}
    facts = {"acceptance_date": invoice["acceptance_date"], "written_agreement": "false",
             "confirmed_bank_reference": invoice["bank_reference"]}
    assert client.post("/api/v1/documents", files=files, data=facts,
                       headers={"Authorization": "Bearer test-service"}).status_code == 403
    response = client.post("/api/v1/documents", files=files, data=facts)
    assert response.status_code == 201, response.text
    doc = response.json()
    assert doc["extractor"] == "sarvam-vision"
    assert doc["decision"]["overall_status"] == "PASS"
    assert doc["payment"] is None
    with Session(engine) as session:
        assert session.get(Document, doc["document_id"]).extraction["provider_result"] == raw


def test_document_cursor_and_payment_visibility(api):
    from test_payments import approve, event, initiate

    client, _ = api
    docs = [client.post("/api/v1/documents", files={"file": (name + ".pdf", sample_pdf(name))}).json()
            for name in ("clean-printed", "changed-bank")]
    page = client.get("/api/v1/documents?limit=1").json()
    assert len(page) == 1 and page[0]["document_id"] == docs[1]["document_id"]
    older = client.get(f"/api/v1/documents?limit=1&before_id={page[0]['document_id']}").json()
    assert [row["document_id"] for row in older] == [docs[0]["document_id"]]
    invoice_id = docs[0]["invoice_id"]
    payment = initiate(client, invoice_id, approve(client, invoice_id)).json()
    assert event(client, payment, "SUCCESS").status_code == 200
    detail = client.get(f"/api/v1/documents/{docs[0]['document_id']}").json()
    assert detail["payment"]["status"] == "SUCCESS"


def test_cors_allows_only_configured_origin(monkeypatch, tmp_path):
    monkeypatch.setenv("CHECK_DATABASE_URL", f"sqlite:///{tmp_path / 'cors.db'}")
    monkeypatch.setenv("CHECK_CORS_ORIGINS", "https://frontend.example")
    with TestClient(create_app()) as client:
        for origin, status in (("https://frontend.example", 200), ("https://other.example", 400)):
            response = client.options("/api/v1/workspace", headers={
                "Origin": origin, "Access-Control-Request-Method": "GET",
                "Access-Control-Request-Headers": "authorization",
            })
            assert response.status_code == status
            assert response.headers.get("access-control-allow-origin") == (origin if status == 200 else None)
