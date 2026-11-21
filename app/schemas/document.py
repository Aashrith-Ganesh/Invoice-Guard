from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, StringConstraints

from app.schemas.invoice import Money
from app.schemas.payment import PaymentView
from app.schemas.validation import Decision

Lane = Literal["PROCESSED", "ON_HOLD", "REJECTED"]


class Reason(BaseModel):
    code: str
    severity: Literal["block", "hold"]
    text: str


class SignalView(BaseModel):
    code: str
    detail: str
    impact: int


class RatingView(BaseModel):
    provider: str | None
    score: int | None
    threshold: int
    signals: list[SignalView]


class ReviewView(BaseModel):
    status: Literal["NONE", "VERIFIED", "REJECTED"]
    note: str | None
    reviewed_at: str | None


class Event(BaseModel):
    action: str
    at: str
    details: dict


class DocumentView(BaseModel):
    document_id: int
    invoice_id: int | None
    filename: str
    uploaded_at: str
    size_bytes: int
    extractor: str
    duplicate_submission: bool
    lane: Lane
    reasons: list[Reason]
    rating: RatingView
    review: ReviewView
    processing_override: Literal["skip_tax", "process_demo"] | None = None
    can_skip_tax: bool = False
    can_process_demo: bool = False
    can_verify: bool
    can_reject: bool
    can_recheck: bool
    payment_ready: bool
    payment: PaymentView | None = None
    invoice: dict
    decision: Decision | None
    events: list[Event] = []


class ReviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action: Literal["verify", "reject", "skip_tax", "process_demo", "return_to_review"]
    note: Annotated[str, StringConstraints(strip_whitespace=True, min_length=3, max_length=500)]


class TranslateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    language: Annotated[str, StringConstraints(pattern=r"^[a-z]{2}$")]


class TranslationView(BaseModel):
    language: str
    provider: Literal["original", "sarvam", "built-in", "unavailable"]
    summary: list[str]
    items: list[str]
    reasons: list[str]


class Workspace(BaseModel):
    business_name: str
    currency: str
    cash_available: str
    role: str
    threshold: int
    translation_provider: str
    extraction_mode: Literal["demo", "sarvam"]
    can_clear_bills: bool
    demo_processing_enabled: bool = False
    languages: dict[str, str]


class Sample(BaseModel):
    name: str
    title: str
    description: str
    expected: Lane


class BalanceAdjustment(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_balance: Money
    cash_available: Money


class BalanceView(BaseModel):
    cash_available: str
