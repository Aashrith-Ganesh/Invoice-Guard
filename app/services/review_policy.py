"""Deterministic lane rule for uploaded invoices.

PROCESSED  = rule checks PASS, and (Prism rating >= 80 or a person verified it), and not rejected.
ON_HOLD    = anything else that is not rejected. A high rating never clears a rule HOLD or BLOCK.
REJECTED   = a person rejected it. It cannot be approved or paid.
"""
from typing import Literal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Document

THRESHOLD = 80
Lane = Literal["PROCESSED", "ON_HOLD", "REJECTED"]


def processing_override(document: Document) -> Literal["skip_tax", "process_demo"] | None:
    action = (document.extraction or {}).get("processing_override")
    return action if action in ("skip_tax", "process_demo") else None


def rating_cleared(document: Document) -> bool:
    if processing_override(document):
        return False
    if document.review_status == "VERIFIED":
        return True
    return document.rating_score is not None and document.rating_score >= THRESHOLD


def lane(document: Document, rule_status: str | None) -> Lane:
    if document.review_status == "REJECTED":
        return "REJECTED"
    if document.duplicate_submission or rule_status != "PASS":
        return "ON_HOLD"
    return "PROCESSED" if rating_cleared(document) else "ON_HOLD"


def primary_document(session: Session, business_id: int, invoice_id: int) -> Document | None:
    return session.scalar(select(Document).where(
        Document.business_id == business_id, Document.invoice_id == invoice_id,
        Document.duplicate_submission.is_(False),
    ).order_by(Document.id.desc()).limit(1))
