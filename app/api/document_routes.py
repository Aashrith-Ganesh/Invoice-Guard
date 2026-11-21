"""Invoice extraction and display translation for an existing FastAPI app."""

import json
from app.api.dependencies import Actor, Database
from app.models.document_job import DocumentJob
from app.database.session import write_transaction
from sqlalchemy.orm import Session
from app.integrations.sarvam.documents import sarvam_request
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, File, HTTPException, UploadFile
from pydantic import BaseModel, Field

router = APIRouter(prefix="/api/agents/sarvam", tags=["Sarvam"])
MAX_FILE_BYTES = 10 * 1024 * 1024
JOB_PATH = "/doc-ai/v1/job"


def string_field(description: str) -> dict:
    return {"type": "string", "description": description}


INVOICE_SCHEMA = {
    "type": "object",
    "properties": {
        "invoice_number": string_field("Invoice number printed on the bill"),
        "invoice_date": string_field("Invoice date as printed"),
        "vendor_name": string_field("Vendor name as printed"),
        "gstin": string_field("Vendor GSTIN as printed, if present"),
        "currency": string_field("Currency code or symbol printed on the invoice"),
        "subtotal": string_field("Subtotal as printed before tax"),
        "tax": string_field("Total tax as printed"),
        "total": string_field("Total due in figures as printed"),
        "amount_in_words": string_field("Total in words as printed"),
        "bank_reference": string_field("Only an opaque ref: or demo: reference if printed; omit account numbers"),
        "ifsc": string_field("Bank IFSC as printed"),
        "line_items": {
            "type": "array",
            "description": "Itemized services or goods listed on the invoice",
            "items": {
                "type": "object",
                "description": "One invoice line as printed",
                "properties": {
                    "description": string_field("Service or item description as printed"),
                    "quantity": string_field("Quantity as printed"),
                    "unit_price": string_field("Unit price as printed"),
                    "amount": string_field("Line amount as printed"),
                },
            },
        },
    },
}


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
        data={"schema": json.dumps(INVOICE_SCHEMA), "output_format": "json"},
    )
    try:
        job_id = UUID(job["job_id"])
    except (KeyError, TypeError, ValueError, AttributeError) as exc:
        raise HTTPException(502, "Sarvam did not return a valid job ID.") from exc
    with write_transaction(engine) as session:
        session.add(DocumentJob(job_id=str(job_id), business_id=actor.business_id))
    return {"job_id": job_id, "status": job.get("status", "pending")}


@router.get("/invoices/{job_id}")
async def invoice_status(job_id: UUID, actor: Actor, engine: Database):
    with Session(engine) as session:
        job = session.get(DocumentJob, str(job_id))
        if job is None or job.business_id != actor.business_id:
            raise HTTPException(404, "Document job was not found.")
    path = f"{JOB_PATH}/{job_id}"
    status_payload = await sarvam_request("GET", f"{path}/status")
    status = status_payload.get("status")
    if status not in {
        "pending", "running", "completed", "partially_completed", "failed", "rejected"
    }:
        raise HTTPException(502, "Unexpected Sarvam job status.")
    result = {"job_id": job_id, "status": status}
    if status in {"completed", "partially_completed"}:
        extraction = await sarvam_request("GET", f"{path}/results")
        if not isinstance(extraction.get("result"), dict):
            raise HTTPException(502, "Sarvam did not return invoice fields.")
        result["invoice"] = extraction["result"]
        result["annotations"] = extraction.get("annotations")
    return result


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
