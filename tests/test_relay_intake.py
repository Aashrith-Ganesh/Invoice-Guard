"""Invoice intake: the backend extracts and validates, then hands the decision to the Cashfree Relay webhook.

Relay never sees the document and never decides; it only routes the decision (WhatsApp, Sheets).
The real webhook is never called from tests: conftest's autouse `relay_events` fixture records events instead.
"""
import asyncio
import json
from types import SimpleNamespace
from uuid import uuid4

import httpx
from fastapi import HTTPException
from pydantic import SecretStr
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api import document_routes
from app.integrations.relay import intake
from app.models import AuditLog

UPLOAD = "/api/agents/sarvam/invoices"
PNG = b"\x89PNG\r\n\x1a\n" + b"synthetic"
JPEG = b"\xff\xd8\xff\xe0" + b"synthetic"
TAMIL = "சரிபார்ப்பு தேவை"


def extraction(invoice, **overrides):
    result = {
        "supplier_legal_name": invoice["legal_name"],
        "supplier_gstin": invoice["gstin"],
        "invoice_number": invoice["invoice_number"],
        "invoice_date": invoice["invoice_date"],
        "currency": invoice["currency"],
        "line_items": [line | {"description": "Synthetic item"} for line in invoice["lines"]],
        **{key: invoice[key] for key in ("subtotal", "cgst_rate", "cgst", "sgst_rate", "sgst",
                                         "igst_rate", "igst", "tax_total", "grand_total")},
        "total_in_words": "Rupees one hundred and eighteen only",
        "bank_reference": "",
    }
    return {"result": result | overrides, "annotations": {}}


def fake_sarvam(monkeypatch, job_id, payload, *, tamil=TAMIL):
    async def provider(method, path, **kwargs):
        if path == "/translate":
            if tamil is None:
                raise HTTPException(502, "Sarvam returned an upstream error.")
            return {"translated_text": tamil}
        if method == "POST":
            return {"job_id": str(job_id), "status": "pending"}
        if path.endswith("/status"):
            return {"status": "completed"}
        return payload

    monkeypatch.setattr(document_routes, "sarvam_request", provider)


def run_intake(client, invoice, monkeypatch, payload, **kwargs):
    job_id = uuid4()
    fake_sarvam(monkeypatch, job_id, payload, **kwargs)
    assert client.post(UPLOAD, files={"file": ("invoice.png", PNG)}).status_code == 202
    context = {"acceptance_date": invoice["acceptance_date"], "written_agreement": invoice["written_agreement"],
               "confirmed_bank_reference": invoice["bank_reference"]}
    return job_id, client.post(f"{UPLOAD}/{job_id}/validate", json=context)


def relay_audits(engine):
    with Session(engine) as session:
        return [row.details for row in session.scalars(
            select(AuditLog).where(AuditLog.action == "relay_intake_notified"))]


def test_png_and_jpeg_invoices_are_sent_to_sarvam_with_their_type(api, monkeypatch):
    client, _ = api
    sent = []

    async def provider(method, path, **kwargs):
        sent.append(kwargs["files"]["file"])
        return {"job_id": str(uuid4()), "status": "pending"}

    monkeypatch.setattr(document_routes, "sarvam_request", provider)
    for name, content in (("scan.png", PNG), ("photo.jpg", JPEG), ("bill.pdf", b"%PDF-synthetic")):
        assert client.post(UPLOAD, files={"file": (name, content)}).status_code == 202
    assert [(name, mime) for name, _, mime in sent] == [
        ("invoice.png", "image/png"), ("invoice.jpg", "image/jpeg"), ("invoice.pdf", "application/pdf")]


def test_unsupported_upload_is_rejected_before_sarvam(api, monkeypatch):
    client, _ = api
    calls = []

    async def provider(method, path, **kwargs):
        calls.append(path)
        return {}

    monkeypatch.setattr(document_routes, "sarvam_request", provider)
    response = client.post(UPLOAD, files={"file": ("notes.txt", b"plain synthetic text")})
    assert response.status_code == 415
    assert calls == []


def test_passing_decision_is_sent_to_relay_with_tamil_summary(api, invoice, monkeypatch, relay_events):
    client, engine = api
    job_id, response = run_intake(client, invoice, monkeypatch, extraction(invoice))
    assert response.status_code == 200, response.text
    decision = response.json()
    assert decision["overall_status"] == "PASS"
    assert response.headers["X-Relay-Notified"] == "true"

    [event] = relay_events
    assert event["event"] == "invoice.validated"
    assert event["job_id"] == str(job_id)
    assert event["invoice_id"] == decision["invoice_id"]
    assert event["overall_status"] == "PASS"
    assert event["payout_permitted"] is False
    assert event["requires_owner_approval"] is True
    assert (event["invoice_number"], event["vendor_name"]) == ("DEMO-100", "Fictional Vendor 1")
    assert (event["currency"], event["amount"]) == ("INR", "118.00")
    assert "needs your approval" in event["summary_en"]
    assert event["summary_ta"] == TAMIL
    assert relay_audits(engine) == [{"job_id": str(job_id), "delivered": True}]


def test_blocked_decision_tells_relay_every_reason(api, invoice, monkeypatch, relay_events):
    client, _ = api
    payload = extraction(invoice, grand_total="200.00", total_in_words="Rupees two hundred only")
    _, response = run_intake(client, invoice, monkeypatch, payload)
    decision = response.json()
    assert decision["overall_status"] == "BLOCK"

    [event] = relay_events
    assert event["overall_status"] == "BLOCK"
    assert "ARITHMETIC_GRAND_TOTAL" in event["risk_indicators"]
    assert "will not be paid" in event["summary_en"]
    for reason in decision["failure_reasons"]:
        assert reason in event["summary_en"]


def test_relay_or_translation_failure_never_changes_the_decision(api, invoice, monkeypatch):
    client, engine = api
    seen = []

    async def relay_down(event):
        seen.append(event)
        return False

    monkeypatch.setattr(document_routes, "notify_intake", relay_down)
    job_id, response = run_intake(client, invoice, monkeypatch, extraction(invoice), tamil=None)
    assert response.status_code == 200, response.text
    assert response.json()["overall_status"] == "PASS"
    assert response.headers["X-Relay-Notified"] == "false"
    assert seen[0]["summary_ta"] == ""
    assert relay_audits(engine) == [{"job_id": str(job_id), "delivered": False}]


def test_relay_event_carries_no_bank_details(api, invoice, monkeypatch, relay_events):
    client, _ = api
    run_intake(client, invoice, monkeypatch, extraction(invoice))
    [event] = relay_events
    assert not any("bank" in key for key in event)
    assert invoice["bank_reference"] not in json.dumps(event, ensure_ascii=False)


def use_webhook(monkeypatch, url):
    monkeypatch.setattr(intake, "get_settings",
                        lambda: SimpleNamespace(relay_intake_webhook_url=SecretStr(url)))


def no_request(request):
    raise AssertionError("No request expected")


def test_notifier_does_nothing_without_an_https_webhook(monkeypatch):
    for url in ("", "  ", "http://relay.invalid/hook"):
        use_webhook(monkeypatch, url)
        assert asyncio.run(intake.notify_intake({"x": 1}, transport=httpx.MockTransport(no_request))) is False


def test_notifier_posts_json_and_reports_delivery(monkeypatch):
    use_webhook(monkeypatch, "https://relay.invalid/inbound/webhook/synthetic")
    seen = []

    def accept(request):
        seen.append(request)
        return httpx.Response(200, json={"executionId": "1"})

    assert asyncio.run(intake.notify_intake({"overall_status": "PASS"}, transport=httpx.MockTransport(accept)))
    assert json.loads(seen[0].content) == {"overall_status": "PASS"}
    assert seen[0].headers["content-type"] == "application/json"


def test_notifier_reports_failure_without_raising(monkeypatch):
    use_webhook(monkeypatch, "https://relay.invalid/inbound/webhook/synthetic")

    def not_found(request):
        return httpx.Response(404, json={"title": "Webhook Not Found"})

    def unreachable(request):
        raise httpx.ConnectError("synthetic outage", request=request)

    for handler in (not_found, unreachable):
        assert asyncio.run(intake.notify_intake({}, transport=httpx.MockTransport(handler))) is False
