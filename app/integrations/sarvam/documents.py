from pathlib import Path
from uuid import UUID

import httpx
from fastapi import HTTPException

from app.config import get_settings


async def sarvam_request(method: str, path: str, **kwargs) -> dict:
    api_key = get_settings().sarvam_api_key.get_secret_value()
    if not api_key:
        raise HTTPException(503, "Sarvam credentials are missing on the server.")
    try:
        async with httpx.AsyncClient(
            base_url="https://api.sarvam.ai",
            headers={"api-subscription-key": api_key},
            timeout=30,
        ) as client:
            response = await client.request(method, path, **kwargs)
            response.raise_for_status()
            payload = response.json()
    except httpx.TimeoutException as exc:
        raise HTTPException(504, "Sarvam timed out.") from exc
    except httpx.HTTPStatusError as exc:
        status = exc.response.status_code
        if status in {400, 404, 413, 422, 429}:
            raise HTTPException(status, "Sarvam could not process the request.") from exc
        raise HTTPException(502, "Sarvam returned an upstream error.") from exc
    except (httpx.RequestError, ValueError) as exc:
        raise HTTPException(502, "Could not read the Sarvam response.") from exc
    if not isinstance(payload, dict):
        raise HTTPException(502, "Unexpected Sarvam response format.")
    return payload


JOB_PATH = "/doc-ai/v1/job"
# Sarvam Extract accepts PDF, PNG and JPEG. Detect the type from the bytes, not the client's filename.
DOCUMENT_TYPES = (
    (b"%PDF-", "invoice.pdf", "application/pdf"),
    (b"\x89PNG\r\n\x1a\n", "invoice.png", "image/png"),
    (b"\xff\xd8\xff", "invoice.jpg", "image/jpeg"),
)


# Share the checked-in provider contract with Relay's extraction step.
INVOICE_SCHEMA = (Path(__file__).resolve().parents[3] / "docs/relay/sarvam_invoice_schema.json").read_text(
    encoding="utf-8"
)


async def submit_extraction(content: bytes, *, request) -> tuple[UUID, str]:
    kind = next(((name, mime) for magic, name, mime in DOCUMENT_TYPES if content.startswith(magic)), None)
    if kind is None:
        raise HTTPException(415, "Upload the invoice as a PDF, PNG or JPEG file.")
    job = await request(
        "POST",
        f"{JOB_PATH}/extract",
        files={"file": (kind[0], content, kind[1])},
        data={"schema": INVOICE_SCHEMA, "output_format": "json"},
    )
    try:
        job_id = UUID(job["job_id"])
    except (KeyError, TypeError, ValueError, AttributeError) as exc:
        raise HTTPException(502, "Sarvam did not return a valid job ID.") from exc
    return job_id, job.get("status", "pending")


async def fetch_extraction(job_id: UUID, *, request) -> tuple[str, dict | None]:
    path = f"{JOB_PATH}/{job_id}"
    status = (await request("GET", f"{path}/status")).get("status")
    if status not in {"pending", "running", "completed", "partially_completed", "failed", "rejected"}:
        raise HTTPException(502, "Unexpected Sarvam job status.")
    if status not in {"completed", "partially_completed"}:
        return status, None
    extraction = await request("GET", f"{path}/results")
    if not isinstance(extraction.get("result"), dict):
        raise HTTPException(502, "Sarvam did not return invoice fields.")
    return status, extraction
