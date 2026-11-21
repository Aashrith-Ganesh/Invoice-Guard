"""Hand a validated invoice decision to the Cashfree Relay "Invoice Intake" webhook (sandbox).

Relay only routes what the backend already decided (WhatsApp to the owner, a ledger row).
The event carries no bank details, and the webhook URL is a credential that is never logged.
"""
from uuid import UUID

import httpx

from app.config import get_settings
from app.schemas.invoice import ExtractedInvoice
from app.schemas.validation import Decision

TIMEOUT_SECONDS = 15.0


def decision_event(job_id: UUID, decision: Decision, invoice: ExtractedInvoice) -> dict:
    """Flat, display-ready event. Every value comes from the decision or the mapped extraction."""
    number = invoice.invoice_number or "(number not read)"
    vendor = invoice.legal_name or "(vendor not read)"
    amount = f"{invoice.grand_total:.2f}" if invoice.grand_total is not None else ""
    money = f"{invoice.currency or ''} {amount}".strip() or "(amount not read)"
    head = f"Invoice {number} from {vendor} for {money}"
    reasons = " ".join(decision.failure_reasons)
    if decision.overall_status == "PASS":
        next_step = "It needs your approval before payment." if decision.requires_owner_approval else ""
        summary = f"{head} passed all checks. {next_step}".strip()
    elif decision.overall_status == "HOLD":
        summary = f"{head} is on hold and will not be paid until it is reviewed. Reasons: {reasons}"
    else:
        summary = f"{head} is blocked and will not be paid. Reasons: {reasons}"
    return {
        "event": "invoice.validated",
        "job_id": str(job_id),
        "invoice_id": decision.invoice_id,
        "invoice_number": invoice.invoice_number or "",
        "vendor_name": invoice.legal_name or "",
        "amount": amount,
        "currency": invoice.currency or "",
        "overall_status": decision.overall_status,
        "payout_permitted": decision.payout_permitted,
        "requires_owner_approval": decision.requires_owner_approval,
        "risk_indicators": ", ".join(decision.risk_indicators),
        "failure_reasons": reasons,
        "summary_en": summary,
        "summary_ta": "",
    }


async def notify_intake(event: dict, *, transport: httpx.AsyncBaseTransport | None = None) -> bool:
    """POST the event to Relay. Returns whether Relay accepted it; never raises."""
    url = get_settings().relay_intake_webhook_url.get_secret_value().strip()
    if not url.startswith("https://"):
        return False
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT_SECONDS, transport=transport) as client:
            response = await client.post(url, json=event)
    except httpx.HTTPError:
        return False
    return response.is_success
