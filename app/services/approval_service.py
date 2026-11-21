from datetime import UTC, datetime, timedelta
from decimal import Decimal
from secrets import token_urlsafe

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.exceptions import reject
from app.core.security import token_hash
from app.database.base import utc_now
from app.models import Approval, AuditLog, Business, Invoice, Payment, Vendor
from app.schemas.approval import ApprovalChallenge, ApprovalRequest, ApprovalView
from app.schemas.invoice import ExtractedInvoice
from app.services.invoice_service import scoped_invoice
from app.services.validation_service import cash_check, minor
from app.services.vendor_service import primary_account

RETRYABLE = {"FAILED", "REVERSED"}


def latest_payment(session: Session, invoice: Invoice) -> Payment | None:
    return session.scalar(select(Payment).where(
        Payment.business_id == invoice.business_id, Payment.invoice_id == invoice.id,
    ).order_by(Payment.id.desc()).limit(1))


def ensure_attempt_allowed(previous: Payment | None, controlled_id: int | None) -> None:
    if previous is None and controlled_id is None:
        return
    if previous and previous.status in RETRYABLE and previous.id == controlled_id:
        return
    raise reject(409, "PAYMENT_ATTEMPT_EXISTS",
                 "An existing attempt requires reconciliation or explicit owner recovery.")


def bank_is_current(session: Session, invoice: Invoice) -> bool:
    if invoice.vendor_id is None or invoice.bank_account_id is None:
        return False
    vendor = session.get(Vendor, invoice.vendor_id)
    account = primary_account(session, vendor)
    return bool(account and account.id == invoice.bank_account_id and account.verified_at
                and account.verified_at == invoice.bank_verified_at)


def require_eligible(session: Session, business: Business, invoice: Invoice) -> None:
    if invoice.overall_status != "PASS":
        raise reject(409, "INVOICE_INELIGIBLE", "Invoice must pass validation before approval or payout.")
    if not bank_is_current(session, invoice):
        raise reject(409, "BANK_CHANGED", "The verified bank account has changed since validation.")
    extracted = ExtractedInvoice.model_validate(invoice.extracted)
    if (extracted.grand_total is None or minor(extracted.grand_total) != invoice.amount_minor
            or extracted.currency != invoice.currency):
        raise reject(409, "INVOICE_CHANGED", "Payment terms differ from the validated extraction.")
    for check in cash_check(business, invoice.currency, invoice.amount_minor):
        if check.status != "PASS":
            raise reject(409, check.code, check.detail)


def approval_matches(approval: Approval, invoice: Invoice) -> bool:
    return (
        approval.business_id == invoice.business_id
        and approval.invoice_id == invoice.id
        and approval.amount_minor == invoice.amount_minor
        and approval.currency == invoice.currency
        and approval.bank_account_id == invoice.bank_account_id
        and approval.bank_verified_at == invoice.bank_verified_at
        and approval.expires_at > utc_now()
    )


def approval_view(approval: Approval) -> ApprovalView:
    return ApprovalView(
        approval_id=approval.id, invoice_id=approval.invoice_id,
        amount=Decimal(approval.amount_minor).scaleb(-2), currency=approval.currency,
        bank_account_id=approval.bank_account_id, expires_at=approval.expires_at,
        status="APPROVED" if approval.confirmed_at else "PENDING_APPROVAL",
    )


def issue(session: Session, business: Business, request: ApprovalRequest) -> ApprovalChallenge:
    invoice = scoped_invoice(session, business.id, request.invoice_id)
    ensure_attempt_allowed(latest_payment(session, invoice), request.previous_payment_id)
    require_eligible(session, business, invoice)
    token = token_urlsafe(32)
    approval = Approval(
        business_id=business.id, invoice_id=invoice.id, amount_minor=invoice.amount_minor,
        currency=invoice.currency, bank_account_id=invoice.bank_account_id,
        bank_verified_at=invoice.bank_verified_at, token_hash=token_hash(token),
        expires_at=(datetime.now(UTC) + timedelta(minutes=15)).isoformat(timespec="microseconds"),
        control_payment_id=request.previous_payment_id, control_reason=request.reason,
    )
    session.add(approval)
    session.flush()
    session.add(AuditLog(business_id=business.id, action="approval_issued", entity_id=approval.id))
    return ApprovalChallenge(**approval_view(approval).model_dump(), token=token)


def confirm(session: Session, business: Business, token: str) -> ApprovalView:
    approval = session.scalar(select(Approval).where(
        Approval.business_id == business.id, Approval.token_hash == token_hash(token),
    ))
    if approval is None or approval.confirmed_at is not None:
        raise reject(409, "INVALID_APPROVAL", "Approval token is invalid or has already been used.")
    invoice = scoped_invoice(session, business.id, approval.invoice_id)
    if not approval_matches(approval, invoice):
        raise reject(409, "STALE_APPROVAL", "Approval expired or its payment terms changed.")
    ensure_attempt_allowed(latest_payment(session, invoice), approval.control_payment_id)
    require_eligible(session, business, invoice)
    approval.confirmed_at = utc_now()
    session.add(AuditLog(business_id=business.id, action="approval_confirmed", entity_id=approval.id))
    return approval_view(approval)


def available_approval(session: Session, invoice: Invoice, previous: Payment | None) -> bool:
    if previous and previous.status not in RETRYABLE:
        return False
    control_id = previous.id if previous else None
    approvals = session.scalars(select(Approval).where(
        Approval.business_id == invoice.business_id, Approval.invoice_id == invoice.id,
        Approval.control_payment_id == control_id, Approval.confirmed_at.is_not(None),
        Approval.expires_at > utc_now(),
    ))
    return any(approval_matches(approval, invoice) for approval in approvals)
