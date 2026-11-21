from decimal import Decimal
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, PositiveInt, SecretStr, StringConstraints, model_validator


class ApprovalRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    invoice_id: PositiveInt
    previous_payment_id: PositiveInt | None = None
    reason: Annotated[str, StringConstraints(min_length=10, max_length=500, strip_whitespace=True)] | None = None

    @model_validator(mode="after")
    def paired_control_fields(self) -> "ApprovalRequest":
        if (self.previous_payment_id is None) != (self.reason is None):
            raise ValueError("Provide both previous_payment_id and reason for a controlled retry")
        return self


class ConfirmRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    token: Annotated[SecretStr, Field(min_length=43, max_length=43)]


class ApprovalView(BaseModel):
    approval_id: int
    invoice_id: int
    amount: Decimal
    currency: str
    bank_account_id: int
    expires_at: str
    status: Literal["PENDING_APPROVAL", "APPROVED"]


class ApprovalChallenge(ApprovalView):
    token: str
