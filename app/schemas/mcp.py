"""Public projections for MCP reads and untrusted validation previews."""

from datetime import date
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import BaseModel, StringConstraints

from app.schemas.payment import PaymentStatus
from app.schemas.validation import Status

Code = Annotated[str, StringConstraints(pattern=r"^[A-Z][A-Z0-9_]{0,63}$")]
FieldName = Annotated[str, StringConstraints(pattern=r"^[a-z][a-z0-9_]{0,63}$")]
Currency = Annotated[str, StringConstraints(pattern=r"^[A-Z]{3}$")]


class CheckSummary(BaseModel):
    code: Code
    status: Status
    fields: list[FieldName]


class ValidationSummary(BaseModel):
    overall_status: Status
    results: list[CheckSummary]
    risk_indicators: list[Code]


class ValidationPreview(ValidationSummary):
    preview: Literal[True] = True


class InvoiceSummary(ValidationSummary):
    invoice_id: int
    priority_score: Decimal | None
    payment_deadline: date | None
    requires_owner_approval: bool
    payout_permitted: bool


class PriorityList(BaseModel):
    invoices: list[InvoiceSummary]


class PaymentSummary(BaseModel):
    payment_id: int
    invoice_id: int
    amount: Decimal
    currency: Currency
    status: PaymentStatus
