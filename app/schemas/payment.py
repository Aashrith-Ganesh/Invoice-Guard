from decimal import Decimal
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, PositiveInt

PaymentStatus = Literal["PENDING_APPROVAL", "APPROVED", "INITIATED", "SUCCESS", "FAILED", "UNKNOWN", "REVERSED"]


class InitiateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    invoice_id: PositiveInt
    approval_id: PositiveInt
    idempotency_key: Annotated[str, Field(pattern=r"^[A-Za-z0-9_.:-]{1,128}$")]


class PaymentView(BaseModel):
    payment_id: int
    invoice_id: int
    approval_id: int
    amount: Decimal
    currency: str
    external_reference: str
    status: PaymentStatus
    created_at: str


class SimulatorEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    external_reference: Annotated[str, Field(pattern=r"^sim_[0-9a-f]{32}$")]
    status: Literal["SUCCESS", "FAILED", "UNKNOWN", "REVERSED"]
