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
