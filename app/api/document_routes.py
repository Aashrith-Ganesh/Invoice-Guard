"""Invoice extraction and display translation for an existing FastAPI app."""

from hashlib import sha256
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, File, HTTPException, Response, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.dependencies import Actor, Database
from app.core.exceptions import reject
from app.database.session import write_transaction
from app.integrations.relay.intake import decision_event, notify_intake
from app.integrations.sarvam.documents import fetch_extraction, sarvam_request, submit_extraction
from app.integrations.sarvam.invoice_mapping import InvoiceContext, map_invoice
from app.models import AuditLog, Business
from app.models.document_job import DocumentJob
from app.schemas.validation import Decision
from app.services.invoice_service import evaluate

router = APIRouter(prefix="/api/agents/sarvam", tags=["Sarvam"])
MAX_FILE_BYTES = 10 * 1024 * 1024
TRANSLATE_MODEL = "sarvam-translate:v1"


class TranslationInput(BaseModel):
    text: Annotated[str, Field(min_length=1, max_length=2000)]
    source_language: str = "en-IN"
    target_language: str


@router.post("/invoices", status_code=202)
async def submit_invoice(actor: Actor, engine: Database, file: Annotated[UploadFile, File()]):
    content = await file.read(MAX_FILE_BYTES + 1)
    if len(content) > MAX_FILE_BYTES:
        raise HTTPException(413, "Invoice file must be 10 MiB or smaller.")
    job_id, status = await submit_extraction(content, request=sarvam_request)
    with write_transaction(engine) as session:
        session.add(DocumentJob(
            job_id=str(job_id), business_id=actor.business_id, document_sha256=sha256(content).hexdigest(),
        ))
    return {"job_id": job_id, "status": status}


def owned_job(session: Session, job_id: UUID, business_id: int) -> DocumentJob:
    job = session.get(DocumentJob, str(job_id))
    if job is None or job.business_id != business_id:
        raise HTTPException(404, "Document job was not found.")
    return job


@router.get("/invoices/{job_id}")
async def invoice_status(job_id: UUID, actor: Actor, engine: Database):
    with Session(engine) as session:
        saved = owned_job(session, job_id, actor.business_id).original_extraction
    status, extraction = ("completed", saved) if saved is not None else await fetch_extraction(job_id, request=sarvam_request)
    result = {"job_id": job_id, "status": status}
    if extraction is not None:
        result.update(invoice=extraction["result"], annotations=extraction.get("annotations"))
    return result


@router.post("/invoices/{job_id}/validate")
async def validate_extraction(job_id: UUID, context: InvoiceContext, actor: Actor, engine: Database,
                              response: Response) -> Decision:
    if context.confirmed_bank_reference is not None and actor.role != "owner":
        raise reject(403, "OWNER_REQUIRED", "An owner must confirm the independently checked bank reference.")
    with Session(engine) as session:
        saved = owned_job(session, job_id, actor.business_id).original_extraction
    if saved is None:
        status, saved = await fetch_extraction(job_id, request=sarvam_request)
        if status != "completed" or saved is None:
            raise reject(409, "EXTRACTION_NOT_COMPLETE", "Only a fully completed extraction can be validated.")

    with write_transaction(engine) as session:
        job = owned_job(session, job_id, actor.business_id)
        if job.original_extraction is None:
            job.original_extraction = saved
        mapped = map_invoice(job.original_extraction, context, document_sha256=job.document_sha256)
        decision = evaluate(session, session.get(Business, actor.business_id),
                            mapped, mapped.model_dump(mode="json", exclude_none=True))
        session.add(AuditLog(
            business_id=actor.business_id, action="sarvam_extraction_validated", entity_id=decision.invoice_id,
            details={"job_id": str(job_id), "actor": actor.subject,
                     "bank_confirmation_supplied": context.confirmed_bank_reference is not None},
        ))

    # The decision is committed. Telling Relay is best-effort and can never change it.
    event = decision_event(job_id, decision, mapped)
    event["summary_ta"] = await tamil_or_blank(event["summary_en"])
    delivered = await notify_intake(event)
    with write_transaction(engine) as session:
        session.add(AuditLog(business_id=actor.business_id, action="relay_intake_notified",
                             entity_id=decision.invoice_id, details={"job_id": str(job_id), "delivered": delivered}))
    response.headers["X-Relay-Notified"] = "true" if delivered else "false"
    return decision


def translation_body(text: str, source_language: str, target_language: str) -> dict:
    return {"input": text, "source_language_code": source_language,
            "target_language_code": target_language, "model": TRANSLATE_MODEL}


async def tamil_or_blank(text: str) -> str:
    """Display-only Tamil copy of the owner summary; blank if Sarvam is unavailable."""
    try:
        result = await sarvam_request("POST", "/translate", json=translation_body(text, "en-IN", "ta-IN"))
    except HTTPException:
        return ""
    translated = result.get("translated_text")
    return translated if isinstance(translated, str) else ""


@router.post("/translate")
async def translate_display_text(body: TranslationInput, actor: Actor):
    if body.source_language == body.target_language:
        return {"text": body.text, "language": body.target_language}
    result = await sarvam_request(
        "POST", "/translate", json=translation_body(body.text, body.source_language, body.target_language),
    )
    if not isinstance(result.get("translated_text"), str):
        raise HTTPException(502, "Sarvam did not return translated text.")
    return {"text": result["translated_text"], "language": body.target_language}
