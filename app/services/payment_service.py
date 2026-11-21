from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.exceptions import reject
from app.integrations.cashfree.simulator import TRANSITIONS, simulated_reference
from app.models import Approval, AuditLog, Business, Payment
from app.schemas.payment import InitiateRequest, PaymentView, SimulatorEvent
from app.services.approval_service import approval_matches, ensure_attempt_allowed, latest_payment, require_eligible
from app.services.invoice_service import scoped_invoice


def payment_view(attempt: Payment) -> PaymentView:
    return PaymentView(
        payment_id=attempt.id, invoice_id=attempt.invoice_id, approval_id=attempt.approval_id,
        amount=Decimal(attempt.amount_minor).scaleb(-2), currency=attempt.currency,
        external_reference=attempt.external_reference, status=attempt.status, created_at=attempt.created_at,
    )


def initiate(session: Session, business: Business, request: InitiateRequest) -> tuple[PaymentView, bool]:
    existing = session.scalar(select(Payment).where(
        Payment.business_id == business.id, Payment.idempotency_key == request.idempotency_key,
    ))
    if existing:
        if (existing.invoice_id, existing.approval_id) != (request.invoice_id, request.approval_id):
            raise reject(409, "IDEMPOTENCY_CONFLICT", "Key belongs to a different payment request.")
        return payment_view(existing), False

    invoice = scoped_invoice(session, business.id, request.invoice_id)
    approval = session.scalar(select(Approval).where(
        Approval.business_id == business.id, Approval.id == request.approval_id,
    ))
    if approval is None or approval.confirmed_at is None or not approval_matches(approval, invoice):
        raise reject(409, "APPROVAL_REQUIRED", "A current confirmed owner approval is required.")

    ensure_attempt_allowed(latest_payment(session, invoice), approval.control_payment_id)
    require_eligible(session, business, invoice)
    payment = Payment(
        business_id=business.id, invoice_id=invoice.id, approval_id=approval.id,
        bank_account_id=approval.bank_account_id, amount_minor=approval.amount_minor,
        currency=approval.currency, idempotency_key=request.idempotency_key,
        external_reference=simulated_reference(), status="INITIATED",
    )
    business.cash_minor -= payment.amount_minor
    session.add(payment)
    session.flush()
    session.add(AuditLog(business_id=business.id, action="simulated_payment_initiated", entity_id=payment.id))
    return payment_view(payment), True


def apply_event(session: Session, event: SimulatorEvent) -> PaymentView:
    payment = session.scalar(select(Payment).where(Payment.external_reference == event.external_reference))
    if payment is None:
        raise reject(404, "PAYMENT_NOT_FOUND", "Payment was not found.")
    if payment.status == event.status:
        return payment_view(payment)
    if event.status not in TRANSITIONS.get(payment.status, ()):
        raise reject(409, "INVALID_TRANSITION", "The simulator event cannot transition this payment.")
    if event.status in {"FAILED", "REVERSED"}:
        business = session.get(Business, payment.business_id)
        business.cash_minor += payment.amount_minor
    previous = payment.status
    payment.status = event.status
    session.add(AuditLog(business_id=payment.business_id, action="simulated_payment_status", entity_id=payment.id,
                         details={"previous": previous, "status": payment.status}))
    return payment_view(payment)
