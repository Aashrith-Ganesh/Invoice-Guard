"""Invoice extraction and display translation for an existing FastAPI app."""

from hashlib import sha256
from pathlib import Path
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, File, HTTPException, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.dependencies import Actor, Database
from app.core.exceptions import reject
from app.database.session import write_transaction
from app.integrations.sarvam.documents import sarvam_request
from app.integrations.sarvam.invoice_mapping import InvoiceContext, map_invoice
from app.models import AuditLog, Business
from app.models.document_job import DocumentJob
from app.schemas.validation import Decision
from app.services.invoice_service import evaluate

router = APIRouter(prefix="/api/agents/sarvam", tags=["Sarvam"])
MAX_FILE_BYTES = 10 * 1024 * 1024
JOB_PATH = "/doc-ai/v1/job"


# Share the checked-in provider contract with Relay's extraction step.
INVOICE_SCHEMA = (Path(__file__).resolve().parents[2] / "docs/relay/sarvam_invoice_schema.json").read_text(
    encoding="utf-8"
)


class TranslationInput(BaseModel):
    text: Annotated[str, Field(min_length=1, max_length=2000)]
    source_language: str = "en-IN"
    target_language: str


@router.post("/invoices", status_code=202)
async def submit_invoice(actor: Actor, engine: Database, file: Annotated[UploadFile, File()]):
    content = await file.read(MAX_FILE_BYTES + 1)
    if len(content) > MAX_FILE_BYTES:
        raise HTTPException(413, "PDF must be 10 MiB or smaller.")
    if not content.startswith(b"%PDF-"):
        raise HTTPException(415, "Upload an invoice PDF.")
    job = await sarvam_request(
        "POST",
        f"{JOB_PATH}/extract",
        files={"file": ("invoice.pdf", content, "application/pdf")},
        data={"schema": INVOICE_SCHEMA, "output_format": "json"},
    )
    try:
        job_id = UUID(job["job_id"])
    except (KeyError, TypeError, ValueError, AttributeError) as exc:
        raise HTTPException(502, "Sarvam did not return a valid job ID.") from exc
    with write_transaction(engine) as session:
        session.add(DocumentJob(
            job_id=str(job_id), business_id=actor.business_id, document_sha256=sha256(content).hexdigest(),
        ))
    return {"job_id": job_id, "status": job.get("status", "pending")}


def owned_job(session: Session, job_id: UUID, business_id: int) -> DocumentJob:
    job = session.get(DocumentJob, str(job_id))
    if job is None or job.business_id != business_id:
        raise HTTPException(404, "Document job was not found.")
    return job


async def fetch_extraction(job_id: UUID) -> tuple[str, dict | None]:
    path = f"{JOB_PATH}/{job_id}"
    status = (await sarvam_request("GET", f"{path}/status")).get("status")
    if status not in {"pending", "running", "completed", "partially_completed", "failed", "rejected"}:
        raise HTTPException(502, "Unexpected Sarvam job status.")
    if status not in {"completed", "partially_completed"}:
        return status, None
    extraction = await sarvam_request("GET", f"{path}/results")
    if not isinstance(extraction.get("result"), dict):
        raise HTTPException(502, "Sarvam did not return invoice fields.")
    return status, extraction


@router.get("/invoices/{job_id}")
async def invoice_status(job_id: UUID, actor: Actor, engine: Database):
    with Session(engine) as session:
        saved = owned_job(session, job_id, actor.business_id).original_extraction
    status, extraction = ("completed", saved) if saved is not None else await fetch_extraction(job_id)
    result = {"job_id": job_id, "status": status}
    if extraction is not None:
        result.update(invoice=extraction["result"], annotations=extraction.get("annotations"))
    return result


@router.post("/invoices/{job_id}/validate")
async def validate_extraction(job_id: UUID, context: InvoiceContext, actor: Actor, engine: Database) -> Decision:
    if context.confirmed_bank_reference is not None and actor.role != "owner":
        raise reject(403, "OWNER_REQUIRED", "An owner must confirm the independently checked bank reference.")
    with Session(engine) as session:
        saved = owned_job(session, job_id, actor.business_id).original_extraction
    if saved is None:
        status, saved = await fetch_extraction(job_id)
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
        return decision


@router.post("/translate")
async def translate_display_text(body: TranslationInput, actor: Actor):
    if body.source_language == body.target_language:
        return {"text": body.text, "language": body.target_language}
    result = await sarvam_request(
        "POST",
        "/translate",
        json={
            "input": body.text,
            "source_language_code": body.source_language,
            "target_language_code": body.target_language,
            "model": "sarvam-translate:v1",
        },
    )
    if not isinstance(result.get("translated_text"), str):
        raise HTTPException(502, "Sarvam did not return translated text.")
    return {"text": result["translated_text"], "language": body.target_language}
