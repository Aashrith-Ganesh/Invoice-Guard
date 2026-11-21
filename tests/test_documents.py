"""PDF upload → extraction → rules → Prism rating → lane (Processed ≥ 80 / On hold < 80)."""
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.integrations.sarvam.demo_pdf import read_payload, render
from app.integrations.sarvam.types import Rating, Signal
from app.models import AuditLog, Document, Invoice
from app.services import samples
from test_payments import issue

ROOT = "/api/v1"


def pdf(payload: dict) -> bytes:
    return render(payload)


# Blocked cases are not in the demo menu; tests build them here so the rules stay covered.
TRAPS = {
    "wrong-total": lambda: samples._invoice(6, "SSS-219", [("Stage lighting and sound", "1", "40000.00"),
                                                           ("Generator rental, per day", "2", "6500.00")],
                                            total_override="62999.00"),
    "name-mismatch": lambda: samples._invoice(7, "MWC-77", [("Printed invitation cards", "800", "45.00")],
                                              legal_name="Fictional Vendr 7 Pvt"),
    "tamil-printed": lambda: samples._invoice(3, "KMD-07", [("Mandap flower decoration", "1", "65000.00")],
                                              display={"language": "ta"}),
}


def sample(name: str) -> bytes:
    return render(TRAPS[name]()) if name in TRAPS else samples.sample_pdf(name)


def upload(client, content: bytes, name="invoice.pdf", **headers):
    return client.post(f"{ROOT}/documents", files={"file": (name, content, "application/pdf")}, headers=headers)


def uploaded(client, content: bytes) -> dict:
    response = upload(client, content)
    assert response.status_code == 201, response.text
    return response.json()


class FixedRater:
    def __init__(self, score: int) -> None:
        self.score = score

    def rate(self, extraction, decision):
        return Rating("fixed", self.score, [Signal("FIXED", "Fixed score for tests.", 100 - self.score)])


def test_demo_pdf_round_trips_its_extraction():
    payload = {"version": 1, "invoice": {"invoice_number": "X-1"}, "display": {"items": []}}
    content = pdf(payload)
    assert content.startswith(b"%PDF-") and content.rstrip().endswith(b"%%EOF")
    assert read_payload(content) == payload


def test_clean_invoice_is_processed(api):
    client, _ = api
    view = uploaded(client, sample("clean-printed"))
    assert view["lane"] == "PROCESSED"
    assert view["rating"]["score"] >= 80 and view["payment_ready"]
    assert view["decision"]["overall_status"] == "PASS"
    assert view["reasons"] == []


def test_low_rating_holds_even_when_rules_pass(api):
    client, _ = api
    view = uploaded(client, sample("handwritten-hindi"))
    assert view["decision"]["overall_status"] == "PASS"
    assert view["rating"]["score"] < 80
    assert view["lane"] == "ON_HOLD" and view["can_verify"] and not view["payment_ready"]
    assert [reason["code"] for reason in view["reasons"]] == ["LOW_RATING"]


def test_rating_hold_blocks_approval_until_a_person_verifies(api):
    client, engine = api
    view = uploaded(client, sample("handwritten-hindi"))
    blocked = issue(client, view["invoice_id"])
    assert blocked.status_code == 409 and blocked.json()["error"]["code"] == "REVIEW_REQUIRED"

    verified = client.post(f"{ROOT}/documents/{view['document_id']}/review",
                           json={"action": "verify", "note": "Checked the paper bill against the booking."})
    assert verified.status_code == 200, verified.text
    assert verified.json()["lane"] == "PROCESSED"
    assert issue(client, view["invoice_id"]).status_code == 201
    with Session(engine) as session:
        actions = set(session.scalars(select(AuditLog.action).where(AuditLog.entity_id == view["document_id"])))
    assert {"document_uploaded", "document_verified"} <= actions


def test_high_rating_never_clears_a_rule_hold_or_block(api):
    client, _ = api
    client.app.state.rater = FixedRater(100)
    for name, status in (("changed-bank", "HOLD"), ("wrong-total", "BLOCK"), ("name-mismatch", "BLOCK")):
        view = uploaded(client, sample(name))
        assert view["rating"]["score"] == 100
        assert view["decision"]["overall_status"] == status, name
        assert view["lane"] == "ON_HOLD" and not view["can_verify"] and not view["payment_ready"], name
        refused = client.post(f"{ROOT}/documents/{view['document_id']}/review",
                              json={"action": "verify", "note": "Looks fine to me."})
        assert refused.status_code == 409


def test_changed_bank_can_be_rechecked_but_stays_held(api):
    client, _ = api
    view = uploaded(client, sample("changed-bank"))
    assert view["can_recheck"] and "BANK_CHANGE" in [reason["code"] for reason in view["reasons"]]
    again = client.post(f"{ROOT}/invoices/{view['invoice_id']}/revalidate")
    assert again.status_code == 200 and again.json()["overall_status"] == "HOLD"


def test_repeat_upload_is_held_and_original_stays_processed(api):
    client, _ = api
    first = uploaded(client, sample("clean-printed"))
    second = uploaded(client, sample("clean-printed"))
    assert second["lane"] == "ON_HOLD" and not second["can_verify"]
    assert "CONFIRMED_DUPLICATE" in second["decision"]["risk_indicators"]
    assert [reason["code"] for reason in second["reasons"]] == ["DUPLICATE_UPLOAD"]
    assert client.get(f"{ROOT}/documents/{first['document_id']}").json()["lane"] == "PROCESSED"


def test_rejected_invoice_cannot_be_approved(api):
    client, _ = api
    view = uploaded(client, sample("handwritten-hindi"))
    rejected = client.post(f"{ROOT}/documents/{view['document_id']}/review",
                           json={"action": "reject", "note": "Vendor says this bill was cancelled."})
    assert rejected.json()["lane"] == "REJECTED"
    blocked = issue(client, view["invoice_id"])
    assert blocked.status_code == 409 and blocked.json()["error"]["code"] == "INVOICE_REJECTED"


def test_unreadable_pdf_lands_on_hold_without_an_invoice(api):
    client, _ = api
    view = uploaded(client, b"%PDF-1.4\n%%EOF\n")
    assert view["lane"] == "ON_HOLD" and view["invoice_id"] is None
    assert view["rating"]["score"] == 0 and not view["can_verify"] and view["can_reject"]


def test_non_pdf_is_refused(api):
    client, _ = api
    assert upload(client, b"hello", name="x.txt").status_code == 415


def test_service_role_cannot_review(api):
    client, _ = api
    view = uploaded(client, sample("handwritten-hindi"))
    response = client.post(f"{ROOT}/documents/{view['document_id']}/review",
                           json={"action": "verify", "note": "Service should not."},
                           headers={"Authorization": "Bearer test-service"})
    assert response.status_code == 403


def test_documents_are_business_scoped(api):
    client, _ = api
    view = uploaded(client, sample("clean-printed"))
    other = {"Authorization": "Bearer other-owner"}
    # business 2 is not seeded, so its credential is not accepted at all
    assert client.get(f"{ROOT}/documents/{view['document_id']}", headers=other).status_code == 401


def test_extraction_is_stored_as_returned(api):
    client, engine = api
    view = uploaded(client, sample("wrong-total"))
    with Session(engine) as session:
        invoice = session.get(Invoice, view["invoice_id"])
        document = session.get(Document, view["document_id"])
        assert invoice.extracted["grand_total"] == "62999.00"  # wrong on purpose; never corrected
        assert document.extraction["invoice"] == invoice.extracted


def test_translation_falls_back_to_built_in_tamil(api):
    client, _ = api
    view = uploaded(client, sample("changed-bank"))
    result = client.post(f"{ROOT}/documents/{view['document_id']}/translate", json={"language": "ta"}).json()
    assert result["provider"] == "built-in"
    assert any("வங்கிக் கணக்கு" in reason for reason in result["reasons"])
    assert result["items"] == ["கேண்டிட் புகைப்படம், 2 நாட்கள்"]


def test_translation_uses_sarvam_when_configured(api):
    client, _ = api

    class Fake:
        name = "sarvam"

        def translate(self, texts, target):
            return [f"[{target}] {text}" for text in texts]

    client.app.state.translator = Fake()
    view = uploaded(client, sample("clean-printed"))
    result = client.post(f"{ROOT}/documents/{view['document_id']}/translate", json={"language": "kn"}).json()
    assert result["provider"] == "sarvam" and result["summary"][0].startswith("[kn] ")


def test_pdf_and_workspace_endpoints(api):
    client, _ = api
    view = uploaded(client, sample("tamil-printed"))
    file = client.get(f"{ROOT}/documents/{view['document_id']}/file")
    assert file.status_code == 200 and file.headers["content-type"] == "application/pdf"
    space = client.get(f"{ROOT}/workspace").json()
    assert space["threshold"] == 80 and space["role"] == "owner" and "ta" in space["languages"]
    assert {item["name"] for item in client.get(f"{ROOT}/samples").json()} == {
        "clean-printed", "handwritten-hindi", "changed-bank"}
