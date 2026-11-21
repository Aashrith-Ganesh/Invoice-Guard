from sqlalchemy.orm import Session

from app.models import Business, Invoice, Vendor
from app.schemas.validation import Check, Decision
from app.services.approval_service import RETRYABLE, available_approval, bank_is_current, latest_payment
from app.services.invoice_service import decision, latest_checks, outcome
from app.services.validation_service import cash_check


def invoice_view(session: Session, business: Business, invoice: Invoice) -> Decision:
    """Current decision for a stored invoice, re-checking live cash and bank state."""
    vendor = session.get(Vendor, invoice.vendor_id) if invoice.vendor_id else None
    checks = latest_checks(session, invoice)
    previous = latest_payment(session, invoice)
    can_approve = not previous or previous.status in RETRYABLE
    if can_approve:
        live_cash = cash_check(business, invoice.currency, invoice.amount_minor)
        persisted_cash_hold = any(check.code in {"INSUFFICIENT_CASH", "CURRENCY_UNSUPPORTED"} for check in checks)
        if not persisted_cash_hold:
            checks = [check for check in checks if check.code != "CASH_AVAILABLE"]
            checks.extend(live_cash)
        if outcome(checks) == "PASS" and not bank_is_current(session, invoice):
            checks.append(Check(code="BANK_CHANGED", status="HOLD",
                                detail="The verified bank account has changed since validation."))
    permitted = can_approve and outcome(checks) == "PASS" and available_approval(session, invoice, previous)
    return decision(business, invoice, vendor, checks, permitted=permitted, can_approve=can_approve)
