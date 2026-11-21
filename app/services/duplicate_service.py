from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Invoice
from app.schemas.validation import Check


def find_duplicate(session: Session, candidate: Invoice
                   ) -> tuple[Invoice | None, Check]:
    query = select(Invoice).where(Invoice.business_id == candidate.business_id)
    if candidate.vendor_id and candidate.normalized_invoice_number:
        same_id = session.scalar(query.where(
            Invoice.vendor_id == candidate.vendor_id,
            Invoice.normalized_invoice_number == candidate.normalized_invoice_number,
        ))
        if same_id:
            evidence = ("invoice_date", "amount_minor", "currency", "document_sha256")
            conflicts = [
                field for field in evidence
                if getattr(candidate, field) is not None and getattr(same_id, field) is not None
                and getattr(candidate, field) != getattr(same_id, field)
            ]
            if conflicts:
                return same_id, Check(code="POSSIBLE_DUPLICATE", status="HOLD",
                                      detail="Invoice identity matches with conflicting evidence.", fields=conflicts)
            return same_id, Check(code="CONFIRMED_DUPLICATE", status="BLOCK", detail="Invoice identity already exists.")

    if candidate.document_sha256:
        same_document = session.scalar(query.where(Invoice.document_sha256 == candidate.document_sha256).limit(1))
        if same_document:
            return None, Check(code="CONFIRMED_DUPLICATE", status="BLOCK", detail="Document digest already exists.")
    if candidate.vendor_id and candidate.invoice_date and candidate.amount_minor is not None and candidate.currency:
        secondary = session.scalar(query.where(
            Invoice.vendor_id == candidate.vendor_id, Invoice.invoice_date == candidate.invoice_date,
            Invoice.amount_minor == candidate.amount_minor, Invoice.currency == candidate.currency,
        ).limit(1))
        if secondary:
            return None, Check(code="POSSIBLE_DUPLICATE", status="HOLD", detail="Vendor, date, amount and currency match another invoice.")
    return None, Check(code="DUPLICATE_SCAN", status="PASS", detail="No duplicate evidence found.")
