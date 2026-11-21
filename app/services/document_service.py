import re
from decimal import Decimal, InvalidOperation
from hashlib import sha256

from pydantic import ValidationError
from sqlalchemy import delete, func, or_, select
from sqlalchemy.orm import Session

from app.core.exceptions import reject
from app.database.base import utc_now
from app.integrations.sarvam.types import Extraction, Rater, Translator
from app.models import Approval, AuditLog, Business, Document, Invoice, InvoiceValidation, Payment, PaymentLink, Vendor
from app.models.document_job import DocumentJob
from app.schemas.document import (
    DocumentView, Event, RatingView, Reason, ReviewView, SignalView, TranslationView,
)
from app.schemas.invoice import ExtractedInvoice
from app.schemas.validation import Decision
from app.services.approval_service import latest_payment
from app.services.invoice_service import evaluate
from app.services.payment_service import payment_view
from app.services.plain_language import FIELD_LABELS, ITEMS, REASONS, SUMMARY, reason_key
from app.services.review_policy import THRESHOLD, lane, processing_override
from app.services.view_service import invoice_view

MAX_BYTES = 10 * 1024 * 1024
BUILT_IN = {"ta", "hi"}
TAX_FIELDS = {"cgst", "sgst", "igst", "cgst_rate", "sgst_rate", "igst_rate", "tax_total"}


def safe_filename(name: str | None) -> str:
    base = re.sub(r"[^A-Za-z0-9._ -]", "_", (name or "invoice.pdf").rsplit("/", 1)[-1].rsplit("\\", 1)[-1])
    return (base.strip(" .") or "invoice.pdf")[:120]


def scoped_document(session: Session, business_id: int, document_id: int) -> Document:
    document = session.scalar(select(Document).where(
        Document.id == document_id, Document.business_id == business_id,
    ))
    if document is None:
        raise reject(404, "DOCUMENT_NOT_FOUND", "Document was not found.")
    return document


def clear_demo_bills(session: Session, business_id: int, owner_id: str | None) -> int:
    scoped_documents = Document.business_id == business_id
    cleared = session.scalar(select(func.count()).select_from(Document).where(scoped_documents))
    for model in (PaymentLink, Payment, Approval, InvoiceValidation, Document, DocumentJob, Invoice):
        session.execute(delete(model).where(model.business_id == business_id))

    # Bill history uses integer entity IDs. Remove its entries before SQLite can reuse those IDs.
    bill_actions = (
        "document_uploaded", "document_verified", "document_rejected",
        "document_skip_tax", "document_process_demo", "document_return_to_review",
        "invoice_validated", "invoice_duplicate_submission", "approval_issued", "approval_confirmed",
        "simulated_payment_initiated", "simulated_payment_status", "hosted_payment_link_created",
        "hosted_simulated_payment_completed", "sarvam_extraction_validated", "relay_intake_notified",
    )
    session.execute(delete(AuditLog).where(AuditLog.business_id == business_id, AuditLog.action.in_(bill_actions)))
    session.add(AuditLog(business_id=business_id, entity_id=business_id, action="demo_bills_cleared",
                         details={"documents": cleared, "owner": owner_id}))
    return cleared


def validate_upload(content: bytes) -> None:
    if len(content) > MAX_BYTES:
        raise reject(413, "FILE_TOO_LARGE", "PDF must be 10 MB or smaller.")
    if not content.startswith(b"%PDF-"):
        raise reject(415, "PDF_REQUIRED", "Upload a PDF invoice.")



def upload(session: Session, business: Business, filename: str | None, content: bytes,
           extraction: Extraction, rater: Rater) -> Document:
    digest = sha256(content).hexdigest()
    decision: Decision | None = None
    invoice_fields = None
    error = extraction.error
    if extraction.invoice is not None:
        # The digest is computed here from the uploaded bytes; every extracted field is kept as returned.
        invoice_fields = dict(extraction.invoice) | {"document_sha256": digest}
        try:
            data = ExtractedInvoice.model_validate(invoice_fields)
        except ValidationError:
            error = "The extraction does not match the invoice schema."
        else:
            newest = session.scalar(select(func.max(Invoice.id)).where(Invoice.business_id == business.id)) or 0
            decision = evaluate(session, business, data, invoice_fields)
            duplicate_submission = decision.invoice_id <= newest
    rating_input = extraction if decision else Extraction(extraction.provider, None, extraction.display, error)
    rating = rater.rate(rating_input, decision)
    document = Document(
        business_id=business.id, invoice_id=decision.invoice_id if decision else None,
        duplicate_submission=bool(decision and duplicate_submission), filename=safe_filename(filename),
        sha256=digest, size_bytes=len(content), content=content, extractor=extraction.provider,
        extraction={"invoice": invoice_fields, "display": extraction.display, "error": error,
                    "provider_result": extraction.provider_result,
                    "decision_at_upload": decision.model_dump(mode="json") if decision else None},
        rating_provider=rating.provider, rating_score=rating.score,
        rating_signals=[signal.__dict__ for signal in rating.signals],
    )
    session.add(document)
    session.flush()
    session.add(AuditLog(business_id=business.id, action="document_uploaded", entity_id=document.id, details={
        "invoice_id": document.invoice_id, "sha256": digest, "rating": rating.score,
        "rating_provider": rating.provider, "rule_status": decision.overall_status if decision else None,
        "duplicate_submission": document.duplicate_submission,
    }))
    return document


def current_decision(session: Session, business: Business, document: Document) -> Decision | None:
    if document.invoice_id is None:
        return None
    if document.duplicate_submission:
        stored = (document.extraction or {}).get("decision_at_upload")
        return Decision.model_validate(stored) if stored else None
    return invoice_view(session, business, session.get(Invoice, document.invoice_id))


def reasons_for(document: Document, decision: Decision | None, language: str = "en",
                *, business: Business) -> list[Reason]:
    def text(code: str, fallback: str) -> str:
        table = REASONS.get(reason_key(code), {})
        return table.get(language) or table.get("en") or fallback

    reasons: list[Reason] = []
    if document.review_status == "REJECTED":
        reasons.append(Reason(code="REJECTED", severity="block", text=text("REJECTED", "")))
    if decision is None:
        description = text("EXTRACTION_FAILED", "")
        if language == "en":
            description += (" Demo mode only reads built-in samples." if document.extractor == "demo"
                            else " No usable fields were returned. Check that the PDF is legible and try again.")
        reasons.append(Reason(code="EXTRACTION_FAILED", severity="hold", text=description))
    else:
        if document.duplicate_submission:
            reasons.append(Reason(code="DUPLICATE_UPLOAD", severity="block", text=text("DUPLICATE_UPLOAD", "")))
        seen = set()
        for check in decision.results:
            key = check.code if language == "en" else reason_key(check.code)
            if check.status == "PASS" or key in seen or (document.duplicate_submission and key == "CONFIRMED_DUPLICATE"):
                continue
            seen.add(key)
            description = text(check.code, check.detail)
            if language == "en":
                fields = ", ".join(FIELD_LABELS[field] for field in check.fields if field in FIELD_LABELS)
                if check.code == "MISSING_FIELDS" and fields:
                    description = f"Missing required information: {fields}."
                    if "bank_reference" in check.fields:
                        description += " Confirm the vendor's bank account independently before supplying its internal reference."
                elif check.code == "LOW_CONFIDENCE" and fields:
                    description = f"Low extraction confidence: {fields}. Compare these fields with the original PDF."
                elif check.code.startswith("ARITHMETIC_") and fields:
                    description = f"The {fields} does not match the calculation. {check.detail}"
                elif check.code in {"BANK_CHANGE", "BANK_UNVERIFIED", "BANK_CHANGED"}:
                    description = check.detail + " Confirm the account through a trusted vendor contact, then recheck the bill."
                elif check.code == "POSSIBLE_DUPLICATE" and fields:
                    description = f"The invoice identity matches an existing bill, but these fields differ: {fields}. Compare the two bills before paying."
                elif check.code == "INSUFFICIENT_CASH":
                    amount = _money(((document.extraction or {}).get("invoice") or {}).get("grand_total"))
                    cash = Decimal(business.cash_minor).scaleb(-2)
                    if amount is not None:
                        description = (f"Invoice amount: {business.currency} {amount}. "
                                       f"Available now: {business.currency} {cash:.2f}. "
                                       "Recheck the bill when sufficient cash is available.")
            reasons.append(Reason(code=check.code, severity="block" if check.status == "BLOCK" else "hold",
                                  text=description))
    rules_clear = decision is not None and decision.overall_status == "PASS" and not document.duplicate_submission
    if rules_clear and document.review_status == "NONE" and (document.rating_score is None
                                                             or document.rating_score < THRESHOLD):
        description = text("LOW_RATING", "")
        if language == "en" and document.rating_score is not None:
            description = (f"The review rating is {document.rating_score}/100. The threshold is {THRESHOLD}/100. "
                           "Compare the extracted details with the original PDF before marking it verified.")
        reasons.append(Reason(code="LOW_RATING", severity="hold", text=description))
    return reasons


def _money(value: object) -> str | None:
    try:
        return f"{Decimal(str(value)):.2f}" if value is not None else None
    except InvalidOperation:
        return None


def invoice_summary(session: Session, document: Document, decision: Decision | None) -> dict:
    extraction = document.extraction or {}
    fields = extraction.get("invoice") or {}
    display = extraction.get("display") or {}
    vendor = None
    if document.invoice_id is not None:
        stored = session.get(Invoice, document.invoice_id)
        vendor = session.get(Vendor, stored.vendor_id) if stored and stored.vendor_id else None
    return {
        "vendor_name": fields.get("legal_name"),
        "trade_name": display.get("trade_name") or None,
        "vendor_address": display.get("vendor_address") or None,
        "vendor_classification": vendor.classification if vendor else None,
        "vendor_registered": vendor is not None,
        "gstin": fields.get("gstin"),
        "invoice_number": fields.get("invoice_number"),
        "invoice_date": fields.get("invoice_date"),
        "acceptance_date": fields.get("acceptance_date"),
        "payment_deadline": decision.payment_deadline.isoformat() if decision and decision.payment_deadline else None,
        "priority_score": str(decision.priority_score) if decision and decision.priority_score is not None else None,
        "currency": fields.get("currency"),
        "subtotal": _money(fields.get("subtotal")),
        "taxes": [{"name": name.upper(), "rate": str(fields.get(f"{name}_rate")), "amount": _money(fields.get(name))}
                  for name in ("cgst", "sgst", "igst") if _money(fields.get(name)) not in (None, "0.00")],
        "tax_total": _money(fields.get("tax_total")),
        "grand_total": _money(fields.get("grand_total")),
        "bank_reference": fields.get("bank_reference"),
        "language": display.get("language") or None,
        "handwritten": bool(display.get("handwritten")),
        "amount_in_words": display.get("amount_in_words") or None,
        "items": display.get("items") or [],
        "confidence": fields.get("confidence") or {},
        "extraction_error": extraction.get("error"),
    }


def events_for(session: Session, document: Document) -> list[Event]:
    conditions = [(AuditLog.entity_id == document.id) & AuditLog.action.like("document_%")]
    if document.invoice_id is not None:
        conditions.append((AuditLog.entity_id == document.invoice_id)
                          & AuditLog.action.in_(("invoice_validated", "invoice_duplicate_submission")))
    rows = session.scalars(select(AuditLog).where(AuditLog.business_id == document.business_id, or_(*conditions))
                           .order_by(AuditLog.id))
    keep = ("status", "rating", "rule_status", "note", "duplicate_submission")
    return [Event(action=row.action, at=row.created_at,
                  details={key: value for key, value in (row.details or {}).items() if key in keep})
            for row in rows]


def view(session: Session, business: Business, document: Document, *, with_events: bool = False) -> DocumentView:
    decision = current_decision(session, business, document)
    rule_status = decision.overall_status if decision else None
    current = lane(document, rule_status)
    override = processing_override(document)
    failures = [check for check in decision.results if check.status != "PASS"] if decision else []
    missing = next((check.fields for check in failures if check.code == "MISSING_FIELDS"), [])
    can_process = bool(missing and not override and current == "ON_HOLD" and rule_status == "HOLD"
                       and not document.duplicate_submission)
    can_skip_tax = can_process and len(failures) == 1 and set(missing).issubset(TAX_FIELDS)
    revalidatable = bool(decision and not document.duplicate_submission and rule_status == "HOLD"
                         and any(check.code == "DUPLICATE_SCAN" for check in decision.results))
    payment = None
    if document.invoice_id is not None and not document.duplicate_submission:
        payment = latest_payment(session, session.get(Invoice, document.invoice_id))
    return DocumentView(
        document_id=document.id, invoice_id=document.invoice_id, filename=document.filename,
        uploaded_at=document.created_at, size_bytes=document.size_bytes, extractor=document.extractor,
        duplicate_submission=document.duplicate_submission,
        lane="PROCESSED" if override and rule_status != "BLOCK" else current,
        processing_override=override, can_skip_tax=can_skip_tax, can_process_demo=can_process,
        reasons=reasons_for(document, decision, business=business) if current != "PROCESSED" or override else [],
        rating=RatingView(provider=document.rating_provider, score=document.rating_score, threshold=THRESHOLD,
                          signals=[SignalView(**signal) for signal in document.rating_signals or []]),
        review=ReviewView(status=document.review_status, note=document.review_note, reviewed_at=document.reviewed_at),
        can_verify=not override and current == "ON_HOLD" and rule_status == "PASS" and not document.duplicate_submission,
        can_reject=not override and current == "ON_HOLD",
        can_recheck=not override and current == "ON_HOLD" and revalidatable,
        payment_ready=not override and current == "PROCESSED",
        payment=payment_view(payment) if payment else None,
        invoice=invoice_summary(session, document, decision), decision=decision,
        events=events_for(session, document) if with_events else [],
    )


def review(session: Session, business: Business, document: Document, action: str, note: str,
           *, owner: str | None = None) -> None:
    current = view(session, business, document)
    if action in {"skip_tax", "process_demo", "return_to_review"}:
        allowed = {"skip_tax": current.can_skip_tax, "process_demo": current.can_process_demo,
                   "return_to_review": bool(current.processing_override)}
        if not allowed[action]:
            raise reject(409, "REVIEW_NOT_ALLOWED", "This processing option is unavailable for the bill's current checks.")
        extraction = dict(document.extraction or {})
        if action == "return_to_review":
            extraction.pop("processing_override", None)
        else:
            extraction["processing_override"] = action
        document.extraction = extraction
        session.add(AuditLog(business_id=business.id, action=f"document_{action}", entity_id=document.id,
                             details={"note": note, "invoice_id": document.invoice_id, "owner": owner}))
        return
    if action == "verify" and not current.can_verify:
        raise reject(409, "REVIEW_NOT_ALLOWED",
                     "Only an invoice whose rule checks pass can be verified; rule holds need their own fix.")
    if action == "reject" and not current.can_reject:
        raise reject(409, "REVIEW_NOT_ALLOWED", "Only an invoice on hold can be rejected.")
    document.review_status = "VERIFIED" if action == "verify" else "REJECTED"
    document.review_note = note
    document.reviewed_at = utc_now()
    session.add(AuditLog(business_id=business.id, action=f"document_{document.review_status.lower()}",
                         entity_id=document.id, details={"note": note, "invoice_id": document.invoice_id}))


def inr(amount: str | None) -> str:
    if amount is None:
        return "-"
    whole, _, cents = amount.partition(".")
    if len(whole) > 3:
        head, tail = whole[:-3], whole[-3:]
        whole = ",".join(re.findall(r"\d{1,2}(?=(?:\d{2})*$)", head)) + "," + tail
    return f"₹{whole}.{cents or '00'}"


def _summary(current: DocumentView, language: str) -> list[str]:
    template = SUMMARY.get(language, SUMMARY["en"])
    data = current.invoice
    if current.decision is None:
        return [template["unread"]]
    lines = [
        template["sent"].format(vendor=data.get("trade_name") or data.get("vendor_name") or "-",
                                number=data.get("invoice_number") or "-", date=data.get("invoice_date") or "-"),
        template["amount"].format(amount=inr(data.get("grand_total")), items=len(data.get("items") or [])),
    ]
    if data.get("payment_deadline"):
        lines.append(template["deadline"].format(deadline=data["payment_deadline"]))
    if current.processing_override:
        lines.append(template["ON_HOLD"].format(score=current.rating.score))
    else:
        lines.append(template[current.lane].format(score=current.rating.score))
    return lines


def translate(session: Session, business: Business, document: Document, language: str,
              translator: Translator | None) -> TranslationView:
    current = view(session, business, document)
    english_reasons = [reason.text for reason in current.reasons]
    items = [item.get("description", "") for item in current.invoice.get("items") or []]
    summary = _summary(current, "en")
    if language == "en":
        return TranslationView(language="en", provider="original", summary=summary, items=items, reasons=english_reasons)
    if translator is not None:
        translated = translator.translate(summary + items + english_reasons, language)
        if translated is not None and len(translated) == len(summary) + len(items) + len(english_reasons):
            first, second = len(summary), len(summary) + len(items)
            return TranslationView(language=language, provider="sarvam", summary=translated[:first],
                                   items=translated[first:second], reasons=translated[second:])
    if language in BUILT_IN:
        local_reasons = ([reason.text for reason in reasons_for(document, current.decision, language, business=business)]
                         if current.reasons else [])
        return TranslationView(language=language, provider="built-in", summary=_summary(current, language),
                               items=[ITEMS.get(item, {}).get(language, item) for item in items],
                               reasons=local_reasons)
    return TranslationView(language=language, provider="unavailable", summary=summary, items=items,
                           reasons=english_reasons)
