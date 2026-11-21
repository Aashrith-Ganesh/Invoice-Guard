from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, PositiveInt

from app.schemas.payment import PaymentStatus


class CreatePaymentLink(BaseModel):
    model_config = ConfigDict(extra="forbid")

    invoice_id: PositiveInt
    approval_id: PositiveInt


class PaymentLinkToken(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)

    token: str = Field(pattern=r"^sim_[0-9a-f]{32}\.[0-9a-f]{64}$")


class PublicPaymentLink(BaseModel):
    invoice_reference: str
    vendor_name: str
    amount: Decimal
    currency: str
    payment_reference: str
    expires_at: str
    status: PaymentStatus | Literal["READY"]


class CreatedPaymentLink(PublicPaymentLink):
    path: str
