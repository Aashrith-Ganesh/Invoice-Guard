from typing import Annotated, Any

from fastapi import APIRouter, Body, Depends, Request
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.dependencies import Actor, Database
from app.core.exceptions import reject
from app.database.session import write_transaction
from app.models import Business, Invoice, Vendor, VendorBankAccount
from app.schemas.invoice import ExtractedInvoice, RevalidateRequest
from app.schemas.validation import BatchItem, Check, Decision, ErrorDetail
from app.services.approval_service import RETRYABLE, available_approval, bank_is_current, latest_payment
from app.services.invoice_service import decision, evaluate, latest_checks, outcome, scoped_invoice
from app.services.validation_service import cash_check

router = APIRouter(prefix="/invoices", tags=["invoices"])


async def original_json(request: Request) -> dict:
    return await request.json()


@router.post("/validate")
def validate(data: ExtractedInvoice, original: Annotated[dict, Depends(original_json)],
             actor: Actor, engine: Database) -> Decision:
    with write_transaction(engine) as session:
        return evaluate(session, session.get(Business, actor.business_id), data, original)


@router.post("/batch-validate")
def batch_validate(items: Annotated[list[Any], Body(min_length=1, max_length=100)],
                   actor: Actor, engine: Database) -> list[BatchItem]:
    results = []
    for raw in items:
        try:
            data = ExtractedInvoice.model_validate(raw)
        except ValidationError:
            results.append(BatchItem(status_code=422, error=ErrorDetail(
                code="INVALID_INVOICE_INPUT", message="Item does not match the extracted invoice schema.",
            )))
            continue
        with write_transaction(engine) as session:
            result = evaluate(session, session.get(Business, actor.business_id), data, raw)
        results.append(BatchItem(status_code=200, decision=result))
    return results


def invoice_view(session: Session, business: Business, invoice: Invoice) -> Decision:
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


@router.get("/priorities")
def priorities(actor: Actor, engine: Database) -> list[Decision]:
    with Session(engine) as session:
        business = session.get(Business, actor.business_id)
        invoices = session.scalars(select(Invoice).where(Invoice.business_id == business.id).order_by(Invoice.id))
        rows = [invoice_view(session, business, invoice) for invoice in invoices]
        return sorted(rows, key=lambda row: (row.priority_score is None, -(row.priority_score or 0), row.invoice_id))


@router.get("/{invoice_id}")
def get_invoice(invoice_id: int, actor: Actor, engine: Database) -> Decision:
    with Session(engine) as session:
        invoice = scoped_invoice(session, actor.business_id, invoice_id)
        return invoice_view(session, session.get(Business, actor.business_id), invoice)


@router.post("/{invoice_id}/revalidate")
def revalidate(invoice_id: int, actor: Actor, engine: Database,
               correction: RevalidateRequest | None = None) -> Decision:
    with write_transaction(engine) as session:
        invoice = scoped_invoice(session, actor.business_id, invoice_id)
        checks = latest_checks(session, invoice)
        previous = latest_payment(session, invoice)
        if (invoice.overall_status == "BLOCK"
                or not any(check.code == "DUPLICATE_SCAN" for check in checks)
                or (previous and previous.status not in RETRYABLE)):
            raise reject(409, "REVALIDATION_UNAVAILABLE", "Invoice cannot be revalidated in its current state.")
        if correction and actor.role != "owner":
            raise reject(403, "OWNER_REQUIRED", "Owner authentication is required to select a different bank reference.")
        business = session.get(Business, actor.business_id)
        data = ExtractedInvoice.model_validate(invoice.extracted)
        if correction:
            data = data.model_copy(update={"bank_reference": correction.bank_reference})
        elif invoice.bank_account_id is not None:
            account = session.get(VendorBankAccount, invoice.bank_account_id)
            data = data.model_copy(update={"bank_reference": account.reference})
        evaluate(session, business, data, invoice.extracted, invoice)
        session.flush()
        return invoice_view(session, business, invoice)
