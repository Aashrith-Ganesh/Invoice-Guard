from decimal import Decimal
from uuid import uuid4

from sqlalchemy import Select, select
from sqlalchemy.orm import Session

from app.core.exceptions import reject
from app.models import AuditLog, Business, Invoice, InvoiceValidation, Vendor
from app.schemas.invoice import ExtractedInvoice, normalize_number
from app.schemas.validation import Check, Decision, Status
from app.services.duplicate_service import find_duplicate
from app.services.prioritisation_service import payment_deadline, priority_score
from app.services.validation_service import arithmetic, cash_check, completeness, minor
from app.services.vendor_service import verify_vendor


def scoped_invoice(session: Session, business_id: int, invoice_id: int) -> Invoice:
    invoice = session.scalar(select(Invoice).where(
        Invoice.id == invoice_id, Invoice.business_id == business_id,
    ))
    if invoice is None:
        raise reject(404, "INVOICE_NOT_FOUND", "Invoice was not found.")
    return invoice


def canonical_validations(invoice: Invoice) -> Select[tuple[InvoiceValidation]]:
    return select(InvoiceValidation).where(
        InvoiceValidation.business_id == invoice.business_id,
        InvoiceValidation.invoice_id == invoice.id,
        InvoiceValidation.duplicate_submission.is_(False),
    )


def current_validation_run(session: Session, invoice: Invoice) -> str | None:
    return session.scalar(canonical_validations(invoice).with_only_columns(InvoiceValidation.run_id)
                          .order_by(InvoiceValidation.id.desc()).limit(1))


def latest_checks(session: Session, invoice: Invoice) -> list[Check]:
    run_id = current_validation_run(session, invoice)
    query = canonical_validations(invoice).where(InvoiceValidation.run_id == run_id)
    return [Check.model_validate(row) for row in session.scalars(query.order_by(InvoiceValidation.id))]


def outcome(checks: list[Check]) -> Status:
    statuses = {check.status for check in checks}
    if "BLOCK" in statuses:
        return "BLOCK"
    return "HOLD" if "HOLD" in statuses else "PASS"


def decision(business: Business, invoice: Invoice, vendor: Vendor | None,
             checks: list[Check], *, permitted: bool = False, can_approve: bool = True) -> Decision:
    status = outcome(checks)
    failures = [check for check in checks if check.status != "PASS"]
    score = None
    if status == "PASS" and can_approve and vendor and invoice.payment_deadline:
        score = priority_score(business, vendor, invoice.payment_deadline)
    return Decision(
        invoice_id=invoice.id, overall_status=status, results=checks,
        failure_reasons=[check.detail for check in failures],
        risk_indicators=[check.code for check in failures], priority_score=score,
        acceptance_date=invoice.acceptance_date, written_agreement=invoice.written_agreement,
        payment_deadline=invoice.payment_deadline, requires_owner_approval=status == "PASS" and can_approve and not permitted,
        payout_permitted=permitted,
    )


def store_checks(session: Session, invoice: Invoice, checks: list[Check], *, duplicate_submission: bool = False) -> None:
    run_id = uuid4().hex
    session.add_all(InvoiceValidation(
        business_id=invoice.business_id, invoice_id=invoice.id, run_id=run_id, duplicate_submission=duplicate_submission,
        **check.model_dump(),
    ) for check in checks)


def evaluate(session: Session, business: Business, data: ExtractedInvoice, original: dict,
             existing: Invoice | None = None) -> Decision:
    vendor, account, checks = verify_vendor(session, business.id, data)
    candidate = Invoice(
        business_id=business.id, vendor_id=vendor.id if vendor else None,
        bank_account_id=account.id if account else None,
        bank_verified_at=account.verified_at if account else None,
        normalized_invoice_number=normalize_number(data.invoice_number) if data.invoice_number else None,
        invoice_date=data.invoice_date, acceptance_date=data.acceptance_date,
        written_agreement=data.written_agreement, currency=data.currency,
        amount_minor=minor(data.grand_total) if data.grand_total is not None else None,
        document_sha256=data.document_sha256.lower() if data.document_sha256 else None,
        extracted=original,
    )
    candidate.payment_deadline = payment_deadline(business, vendor, candidate)
    checks.extend(completeness(business, vendor, data))
    checks.extend(arithmetic(data, Decimal(business.rounding_minor) / 100))
    checks.extend(cash_check(business, candidate.currency, candidate.amount_minor))
    if existing:
        identity = None
        duplicate = next(check for check in latest_checks(session, existing) if check.code == "DUPLICATE_SCAN")
    else:
        identity, duplicate = find_duplicate(session, candidate)
    checks.append(duplicate)
    candidate.overall_status = outcome(checks)

    if identity:
        store_checks(session, identity, checks, duplicate_submission=True)
        session.add(AuditLog(business_id=business.id, action="invoice_duplicate_submission",
                             entity_id=identity.id, details={
                                 "extracted": original, "status": candidate.overall_status,
                             }))
        candidate.id = identity.id
        return decision(business, candidate, vendor, checks)

    if existing:
        existing.bank_account_id = candidate.bank_account_id
        existing.bank_verified_at = candidate.bank_verified_at
        existing.payment_deadline = candidate.payment_deadline
        existing.overall_status = candidate.overall_status
        candidate = existing
    else:
        session.add(candidate)
        session.flush()
    store_checks(session, candidate, checks)
    session.add(AuditLog(business_id=business.id, action="invoice_validated", entity_id=candidate.id,
                         details={"status": candidate.overall_status, "bank_account_id": candidate.bank_account_id}))
    return decision(business, candidate, vendor, checks)
