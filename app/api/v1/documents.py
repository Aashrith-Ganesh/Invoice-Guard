from fastapi import APIRouter, Request, UploadFile
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.dependencies import Actor, Database, Owner
from app.core.exceptions import reject
from app.database.session import write_transaction
from app.integrations.sarvam.translate import LANGUAGES
from app.models import Business, Document
from app.schemas.document import (
    DocumentView, ReviewRequest, Sample, TranslateRequest, TranslationView, Workspace,
)
from app.services import document_service, samples
from app.services.review_policy import THRESHOLD

router = APIRouter(tags=["documents"])


@router.get("/workspace")
def workspace(request: Request, actor: Actor, engine: Database) -> Workspace:
    with Session(engine) as session:
        business = session.get(Business, actor.business_id)
        translator = request.app.state.translator
        return Workspace(business_name=business.name, currency=business.currency,
                         cash_available=f"{business.cash_minor / 100:.2f}", role=actor.role, threshold=THRESHOLD,
                         translation_provider=translator.name if translator else "built-in", languages=LANGUAGES)


@router.post("/documents", status_code=201)
async def upload_document(request: Request, file: UploadFile, actor: Actor, engine: Database) -> DocumentView:
    content = await file.read(document_service.MAX_BYTES + 1)
    with write_transaction(engine) as session:
        business = session.get(Business, actor.business_id)
        document = document_service.upload(session, business, file.filename, content,
                                           request.app.state.extractor, request.app.state.rater)
        return document_service.view(session, business, document, with_events=True)


@router.get("/documents")
def list_documents(actor: Actor, engine: Database) -> list[DocumentView]:
    with Session(engine) as session:
        business = session.get(Business, actor.business_id)
        rows = session.scalars(select(Document).where(Document.business_id == business.id)
                               .order_by(Document.id.desc()).limit(500))
        return [document_service.view(session, business, row) for row in rows]


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
def review_document(document_id: int, data: ReviewRequest, owner: Owner, engine: Database) -> DocumentView:
    with write_transaction(engine) as session:
        business = session.get(Business, owner.business_id)
        document = document_service.scoped_document(session, business.id, document_id)
        document_service.review(session, business, document, data.action, data.note)
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
