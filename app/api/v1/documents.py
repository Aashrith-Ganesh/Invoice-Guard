from datetime import date
from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Form, Query, Request, UploadFile
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.dependencies import Actor, Database, Owner
from app.core.exceptions import reject
from app.database.session import write_transaction
from app.integrations.sarvam.extractor import extract_live
from app.integrations.sarvam.invoice_mapping import InvoiceContext
from app.schemas.vendor import BankReference
from app.integrations.sarvam.translate import LANGUAGES
from app.models import AuditLog, Business, Document
from app.schemas.document import (
    BalanceAdjustment, BalanceView, DocumentView, ReviewRequest, Sample, TranslateRequest, TranslationView, Workspace,
)
from app.services import document_service, samples
from app.services.review_policy import THRESHOLD
from app.services.validation_service import minor

router = APIRouter(tags=["documents"])


def demo_reset_enabled(request: Request) -> bool:
    return (request.app.state.document_extractor_mode == "demo"
            or request.app.state.settings.enable_demo_bill_reset)


def demo_processing_enabled(request: Request) -> bool:
    return (request.app.state.document_extractor_mode == "demo"
            or request.app.state.settings.enable_demo_processing)


@router.get("/workspace")
def workspace(request: Request, actor: Actor, engine: Database) -> Workspace:
    with Session(engine) as session:
        business = session.get(Business, actor.business_id)
        translator = request.app.state.translator
        return Workspace(business_name=business.name, currency=business.currency,
                         cash_available=f"{Decimal(business.cash_minor).scaleb(-2):.2f}", role=actor.role, threshold=THRESHOLD,
                         translation_provider=translator.name if translator else "built-in", languages=LANGUAGES,
                         extraction_mode=request.app.state.document_extractor_mode,
                         demo_processing_enabled=actor.role == "owner" and demo_processing_enabled(request),
                         can_clear_bills=actor.role == "owner" and demo_reset_enabled(request))


@router.patch("/workspace/balance")
def adjust_balance(data: BalanceAdjustment, actor: Owner, engine: Database) -> BalanceView:
    with write_transaction(engine) as session:
        business = session.get(Business, actor.business_id)
        previous = business.cash_minor
        if previous != minor(data.expected_balance):
            raise reject(409, "BALANCE_CHANGED", "The balance changed. Review the current balance before saving.")
        updated = minor(data.cash_available)
        if updated != previous:
            business.cash_minor = updated
            session.add(AuditLog(business_id=actor.business_id, entity_id=actor.business_id,
                                 action="cash_balance_adjusted", details={
                                     "previous_cash_minor": previous, "new_cash_minor": updated,
                                     "owner": actor.subject,
                                 }))
        return BalanceView(cash_available=f"{Decimal(updated).scaleb(-2):.2f}")


@router.post("/documents", status_code=201)
async def upload_document(request: Request, file: UploadFile, actor: Actor, engine: Database,
                          acceptance_date: Annotated[date | None, Form()] = None,
                          written_agreement: Annotated[bool | None, Form()] = None,
                          confirmed_bank_reference: Annotated[BankReference | None, Form()] = None) -> DocumentView:
    if confirmed_bank_reference is not None and actor.role != "owner":
        raise reject(403, "OWNER_REQUIRED", "Only an owner can confirm an independently verified bank reference.")
    content = await file.read(document_service.MAX_BYTES + 1)
    document_service.validate_upload(content)
    if request.app.state.document_extractor_mode == "sarvam":
        extraction = await extract_live(content, InvoiceContext(
            acceptance_date=acceptance_date, written_agreement=written_agreement,
            confirmed_bank_reference=confirmed_bank_reference,
        ))
    else:
        extraction = request.app.state.extractor.extract(content, file.filename or "")
    with write_transaction(engine) as session:
        business = session.get(Business, actor.business_id)
        document = document_service.upload(session, business, file.filename, content,
                                           extraction, request.app.state.rater)
        return document_service.view(session, business, document, with_events=True)


@router.get("/documents")
def list_documents(actor: Actor, engine: Database,
                   limit: Annotated[int, Query(ge=1, le=500)] = 500,
                   before_id: Annotated[int | None, Query(ge=1, le=2**63 - 1)] = None) -> list[DocumentView]:
    with Session(engine) as session:
        business = session.get(Business, actor.business_id)
        query = select(Document).where(Document.business_id == business.id)
        if before_id is not None:
            query = query.where(Document.id < before_id)
        rows = session.scalars(query.order_by(Document.id.desc()).limit(limit))
        return [document_service.view(session, business, row) for row in rows]


@router.post("/documents/clear")
def clear_demo_bills(request: Request, owner: Owner, engine: Database) -> dict[str, int]:
    if not demo_reset_enabled(request):
        raise reject(403, "DEMO_REQUIRED", "Clearing all bills is available only in demo mode.")
    with write_transaction(engine) as session:
        cleared = document_service.clear_demo_bills(session, owner.business_id, owner.subject)
    return {"cleared": cleared}


@router.get("/documents/{document_id}")
def get_document(document_id: int, actor: Actor, engine: Database) -> DocumentView:
    with Session(engine) as session:
        business = session.get(Business, actor.business_id)
        document = document_service.scoped_document(session, business.id, document_id)
        return document_service.view(session, business, document, with_events=True)


@router.get("/documents/{document_id}/file")
def document_file(document_id: int, actor: Actor, engine: Database) -> Response:
    with Session(engine) as session:
        document = document_service.scoped_document(session, actor.business_id, document_id)
        return Response(document.content, media_type="application/pdf", headers={
            "Content-Disposition": f'inline; filename="{document.filename}"',
            "Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff",
        })


@router.post("/documents/{document_id}/review")
def review_document(document_id: int, data: ReviewRequest, request: Request,
                    owner: Owner, engine: Database) -> DocumentView:
    if data.action == "process_demo" and not demo_processing_enabled(request):
        raise reject(403, "DEMO_PROCESSING_DISABLED", "Demo processing is disabled.")
    with write_transaction(engine) as session:
        business = session.get(Business, owner.business_id)
        document = document_service.scoped_document(session, business.id, document_id)
        document_service.review(session, business, document, data.action, data.note, owner=owner.subject)
        session.flush()
        return document_service.view(session, business, document, with_events=True)


@router.post("/documents/{document_id}/translate")
def translate_document(document_id: int, data: TranslateRequest, request: Request,
                       actor: Actor, engine: Database) -> TranslationView:
    if data.language not in LANGUAGES:
        raise reject(422, "LANGUAGE_UNSUPPORTED", "Language is not supported.")
    with Session(engine) as session:
        business = session.get(Business, actor.business_id)
        document = document_service.scoped_document(session, business.id, document_id)
        return document_service.translate(session, business, document, data.language, request.app.state.translator)


@router.get("/samples")
def list_samples(actor: Actor) -> list[Sample]:
    return samples.catalog()


@router.get("/samples/{name}")
def sample_file(name: str, actor: Actor) -> Response:
    content = samples.sample_pdf(name)
    if content is None:
        raise reject(404, "SAMPLE_NOT_FOUND", "Sample was not found.")
    return Response(content, media_type="application/pdf",
                    headers={"Content-Disposition": f'inline; filename="{name}.pdf"'})
