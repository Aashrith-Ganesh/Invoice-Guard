"""Red-line coverage that complements test_invoices.py and test_payments.py.

Map (see CLAUDE.md): RL1 bank verified, RL2 approval, RL3 no double pay, RL4 traceability,
RL5 no silent correction / masked accounts. RL2-RL3 are covered mainly in test_payments.py.
"""
import logging

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.masking import install_account_masking, mask_account
from app.models import AuditLog, Invoice, Payment
from test_invoices import validate
from test_payments import approve, initiate, issue

ROOT = "/api/v1"


def test_mask_keeps_last_four_only():
    masked = mask_account("123456789012")
    assert masked == "XXXXXXXX9012"


def test_logs_never_contain_full_account_numbers(caplog):
    install_account_masking()
    with caplog.at_level(logging.INFO):
        logging.getLogger("redline5").info("paying account %s now", "123456789012")
    assert "123456789012" not in caplog.text
    assert "9012" in caplog.text


def test_rl1_changed_bank_cannot_be_approved_or_paid(api, invoice):
    client, _ = api
    result = validate(api, invoice | {"bank_reference": "demo:vendor-1:alternate"})
    assert result["overall_status"] == "HOLD"
    assert "BANK_CHANGE" in result["risk_indicators"]
    assert issue(client, result["invoice_id"]).status_code == 409


def test_rl5_extraction_is_stored_exactly_as_submitted(api, invoice):
    _, engine = api
    submitted = invoice | {"grand_total": "117.00"}  # wrong on purpose: must be blocked, not corrected
    result = validate(api, submitted)
    assert result["overall_status"] == "BLOCK"
    with Session(engine) as session:
        stored = session.scalar(select(Invoice).where(Invoice.id == result["invoice_id"]))
        assert stored.extracted == submitted


def test_rl4_payment_traces_to_invoice_approval_and_audit(api, invoice):
    client, engine = api
    invoice_id = validate(api, invoice)["invoice_id"]
    approval_id = approve(client, invoice_id)
    payment = initiate(client, invoice_id, approval_id).json()
    with Session(engine) as session:
        row = session.scalar(select(Payment).where(Payment.id == payment["payment_id"]))
        assert (row.invoice_id, row.approval_id) == (invoice_id, approval_id)
        actions = set(session.scalars(select(AuditLog.action).where(AuditLog.business_id == 1)))
    assert {"invoice_validated", "approval_issued", "approval_confirmed",
            "simulated_payment_initiated"} <= actions


def test_uvicorn_access_log_keeps_format_and_masks_account(caplog):
    from uvicorn.logging import AccessFormatter

    formatter = AccessFormatter('%(client_addr)s "%(request_line)s" %(status_code)s', use_colors=False)
    with caplog.at_level(logging.INFO, logger="uvicorn.access"):
        logging.getLogger("uvicorn.access").info(
            '%s - "%s %s HTTP/%s" %d', "127.0.0.1:1234", "GET",
            "/example?account=123456789012", "1.1", 200,
        )
    formatted = formatter.format(caplog.records[-1])
    assert "XXXXXXXX9012" in formatted
    assert "200 OK" in formatted
    assert "123456789012" not in formatted


def test_payment_identifies_exact_validation_run_and_approving_owner(api, invoice):
    from app.models import Approval, InvoiceValidation

    client, engine = api
    invoice_id = validate(api, invoice)["invoice_id"]
    validate(api, invoice)
    approval_id = approve(client, invoice_id)
    payment = initiate(client, invoice_id, approval_id).json()
    with Session(engine) as session:
        attempt = session.get(Payment, payment["payment_id"])
        approval = session.get(Approval, attempt.approval_id)
        assert approval.owner_id == "demo-owner"
        checks = list(session.scalars(select(InvoiceValidation).where(
            InvoiceValidation.business_id == attempt.business_id,
            InvoiceValidation.invoice_id == attempt.invoice_id,
            InvoiceValidation.run_id == approval.validation_run_id,
        )))
        assert checks and all(row.status == "PASS" and not row.duplicate_submission for row in checks)
        confirmation = session.scalar(select(AuditLog).where(
            AuditLog.business_id == attempt.business_id,
            AuditLog.entity_id == approval.id,
            AuditLog.action == "approval_confirmed",
        ))
        assert confirmation.details["owner_id"] == "demo-owner"
        assert confirmation.details["validation_run_id"] == approval.validation_run_id


def test_other_owner_cannot_confirm_same_business_challenge(api, invoice):
    from test_payments import confirm

    client, _ = api
    invoice_id = validate(api, invoice)["invoice_id"]
    token = issue(client, invoice_id).json()["token"]
    response = client.post(f"{ROOT}/approvals/confirm", json={"token": token},
                           headers={"Authorization": "Bearer second-owner"})
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "INVALID_APPROVAL"
    assert confirm(client, token).status_code == 200


def test_revalidation_invalidates_previous_challenge_and_confirmed_approval(api, invoice):
    from test_payments import confirm

    client, _ = api
    invoice_id = validate(api, invoice)["invoice_id"]
    challenge = issue(client, invoice_id).json()["token"]
    approval_id = approve(client, invoice_id)
    assert client.post(f"{ROOT}/invoices/{invoice_id}/revalidate").json()["overall_status"] == "PASS"
    assert confirm(client, challenge).json()["error"]["code"] == "STALE_APPROVAL"
    assert initiate(client, invoice_id, approval_id).json()["error"]["code"] == "APPROVAL_REQUIRED"
    assert initiate(client, invoice_id, approve(client, invoice_id)).status_code == 201
