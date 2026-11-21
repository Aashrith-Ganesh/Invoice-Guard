import unicodedata
from datetime import date
from decimal import Decimal
from typing import Annotated

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field, StringConstraints, field_validator

from app.schemas.vendor import BankReference


def reject_float(value: object) -> object:
    if isinstance(value, float):
        raise ValueError("Use a decimal string or integer")
    return value


def normalize_number(value: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKC", value).casefold() if c.isalnum())


Money = Annotated[Decimal, BeforeValidator(reject_float), Field(ge=0, max_digits=12, decimal_places=2)]
Rate = Annotated[Decimal, BeforeValidator(reject_float), Field(ge=0, le=100, decimal_places=4)]
Confidence = Annotated[Decimal, Field(ge=0, le=1)]
Label = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]


class Line(BaseModel):
    model_config = ConfigDict(extra="forbid")
    quantity: Annotated[Decimal, BeforeValidator(reject_float), Field(gt=0, max_digits=10, decimal_places=4)]
    unit_price: Money


class ExtractedInvoice(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)

    invoice_number: Label | None = None
    invoice_date: date | None = None
    acceptance_date: date | None = None
    written_agreement: Annotated[bool, Field(strict=True)] | None = None
    currency: Annotated[str, Field(pattern=r"^[A-Z]{3}$")] | None = None
    gstin: Label | None = None
    legal_name: Label | None = None
    bank_reference: BankReference | None = None
    document_sha256: Annotated[str, Field(pattern=r"^[a-fA-F0-9]{64}$")] | None = None
    lines: Annotated[list[Line], Field(min_length=1, max_length=500)] | None = None
    subtotal: Money | None = None
    cgst_rate: Rate | None = None
    sgst_rate: Rate | None = None
    igst_rate: Rate | None = None
    cgst: Money | None = None
    sgst: Money | None = None
    igst: Money | None = None
    tax_total: Money | None = None
    grand_total: Money | None = None
    confidence: Annotated[dict[Label, Confidence], Field(max_length=100)] | None = None

    @field_validator("invoice_number")
    @classmethod
    def meaningful_number(cls, value: str | None) -> str | None:
        if value and not normalize_number(value):
            raise ValueError("Invoice number must contain a letter or digit")
        return value

    @field_validator("gstin")
    @classmethod
    def normalize_gstin(cls, value: str | None) -> str | None:
        return value.upper() if value else None

    @field_validator("invoice_date", "acceptance_date")
    @classmethod
    def supported_date(cls, value: date | None) -> date | None:
        if value and not 1900 <= value.year <= 9900:
            raise ValueError("Date outside supported range")
        return value


class RevalidateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    bank_reference: BankReference
