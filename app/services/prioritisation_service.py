from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

from app.models import Business, Invoice, Vendor
from app.services.validation_service import rounded


def payment_deadline(business: Business, vendor: Vendor | None, invoice: Invoice) -> date | None:
    if not invoice.acceptance_date or not vendor:
        return None
    days = business.standard_days
    if vendor.classification in {"Micro", "Small"}:
        if invoice.written_agreement is None:
            return None
        days = business.msme_agreement_days if invoice.written_agreement else business.msme_days
    return invoice.acceptance_date + timedelta(days=days)


def priority_score(business: Business, vendor: Vendor, deadline: date, *, today: date | None = None) -> Decimal:
    today = today or datetime.now(UTC).date()
    remaining = (deadline - today).days
    urgency = max(0, min(100, 100 - remaining * 5))
    overdue = max(0, min(100, -remaining * 10))
    msme = {"Micro": 100, "Small": 80, "Medium": 50, "Non-MSME": 0}[vendor.classification]
    weights = [Decimal(str(weight)) for weight in business.priority_weights]
    if len(weights) != 4 or any(weight < 0 for weight in weights) or sum(weights) <= 0:
        raise ValueError("Invalid business priority weights")
    components = (urgency, overdue, msme, vendor.priority)
    return rounded(sum(weight * score for weight, score in zip(weights, components, strict=True)) / sum(weights))
