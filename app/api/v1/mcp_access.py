from fastapi import APIRouter

from app.api.dependencies import Database, MCPActor
from app.database.session import write_transaction
from app.models import Business
from app.schemas.invoice import ExtractedInvoice, InvoicePreviewInput
from app.schemas.mcp import ValidationPreview
from app.services.invoice_service import evaluate

router = APIRouter(prefix="/mcp", tags=["MCP"])


@router.get("/access")
def access(actor: MCPActor) -> dict[str, str]:
    return {"status": "ok"}


@router.post("/invoice-preview")
def invoice_preview(data: InvoicePreviewInput, actor: MCPActor, engine: Database) -> ValidationPreview:
    fields = data.model_dump(mode="json", exclude_none=True)
    with write_transaction(engine) as session, session.begin_nested() as preview:
        result = evaluate(session, session.get(Business, actor.business_id),
                          ExtractedInvoice.model_validate(fields), fields)
        preview.rollback()
    return ValidationPreview.model_validate(result.model_dump())
