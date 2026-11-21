from decimal import Decimal
from hmac import compare_digest, digest

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.exceptions import reject
from app.database.base import utc_now
from app.integrations.cashfree.simulator import simulated_reference
from app.models import AuditLog, Business, Payment, PaymentLink, Vendor
from app.schemas.payment import InitiateRequest, SimulatorEvent
from app.schemas.payment_link import CreatedPaymentLink, CreatePaymentLink, PublicPaymentLink
from app.services.payment_service import apply_event, approved_attempt, initiate


def signed_reference(secret: str, reference: str, purpose: str) -> str:
    return digest(secret.encode(), f"ps3-hosted:{purpose}:{reference}".encode(), "sha256").hex()


def view(session: Session, link: PaymentLink) -> PublicPaymentLink:
    payment = session.get(Payment, link.payment_id) if link.payment_id is not None else None
    return PublicPaymentLink(
        invoice_reference=link.invoice_reference, vendor_name=link.vendor_name,
        amount=Decimal(link.amount_minor).scaleb(-2), currency=link.currency,
        payment_reference=link.reference, expires_at=link.expires_at,
        status=payment.status if payment else "READY",
    )


def ensure_active(link: PaymentLink) -> None:
    if link.expires_at <= utc_now():
        raise reject(410, "PAYMENT_LINK_EXPIRED", "This simulation link has expired.")


def create(session: Session, business: Business, data: CreatePaymentLink,
           secret: str) -> tuple[CreatedPaymentLink, bool]:
    link = session.scalar(select(PaymentLink).where(
        PaymentLink.business_id == business.id, PaymentLink.approval_id == data.approval_id,
    ))
    created = link is None
    if link is None:
        invoice, approval = approved_attempt(session, business, data.invoice_id, data.approval_id)
        vendor_name = session.get(Vendor, invoice.vendor_id).legal_name
        link = PaymentLink(
            business_id=business.id, invoice_id=invoice.id, approval_id=approval.id,
            reference=simulated_reference(), invoice_reference=invoice.extracted["invoice_number"],
            vendor_name=vendor_name, amount_minor=approval.amount_minor, currency=approval.currency,
            expires_at=approval.expires_at,
        )
        session.add(link)
        session.flush()
        session.add(AuditLog(business_id=business.id, action="hosted_payment_link_created",
                             entity_id=invoice.id, details={"link_id": link.id}))
    elif link.invoice_id != data.invoice_id:
        raise reject(409, "APPROVAL_REQUIRED", "The approval belongs to a different invoice.")
    ensure_active(link)
    signature = signed_reference(secret, link.reference, "link")
    return CreatedPaymentLink(**view(session, link).model_dump(),
                              path=f"/app/pay.html#{link.reference}.{signature}"), created


def find(session: Session, token: str, secret: str) -> PaymentLink:
    reference, signature = token.split(".", 1)
    expected = signed_reference(secret, reference, "link")
    if compare_digest(signature, expected):
        link = session.scalar(select(PaymentLink).where(PaymentLink.reference == reference))
        if link is not None:
            ensure_active(link)
            return link
    raise reject(404, "PAYMENT_LINK_NOT_FOUND", "This simulation link is invalid.")


def settle(session: Session, link: PaymentLink, secret: str) -> PublicPaymentLink:
    if link.payment_id is not None:
        return view(session, link)

    business = session.get(Business, link.business_id)
    attempt, _ = initiate(session, business, InitiateRequest(
        invoice_id=link.invoice_id, approval_id=link.approval_id,
        idempotency_key=signed_reference(secret, link.reference, "attempt"),
    ), reference=link.reference)
    result = apply_event(session, SimulatorEvent(external_reference=attempt.external_reference, status="SUCCESS"))
    link.payment_id = result.payment_id
    session.add(AuditLog(business_id=link.business_id, action="hosted_simulated_payment_completed",
                         entity_id=result.payment_id, details={"link_id": link.id, "invoice_id": link.invoice_id}))
    return view(session, link)
