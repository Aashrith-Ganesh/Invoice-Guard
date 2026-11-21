from datetime import date
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict

Status = Literal["PASS", "HOLD", "BLOCK"]


class Check(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    code: str
    status: Status
    detail: str
    fields: list[str] = []


class Decision(BaseModel):
    invoice_id: int
    overall_status: Status
    results: list[Check]
    failure_reasons: list[str]
    risk_indicators: list[str]
    priority_score: Decimal | None
    acceptance_date: date | None
    written_agreement: bool | None
    payment_deadline: date | None
    requires_owner_approval: bool
    payout_permitted: bool


class ErrorDetail(BaseModel):
    code: str
    message: str


class BatchItem(BaseModel):
    status_code: int
    decision: Decision | None = None
    error: ErrorDetail | None = None
