from sqlalchemy import CheckConstraint, UniqueConstraint
from sqlalchemy.orm import Mapped

from app.database.base import Base, BusinessRecord, scoped_fk, scoped_id


class Approval(BusinessRecord, Base):
    __tablename__ = "approvals"
    __table_args__ = (
        scoped_id(),
        scoped_fk("invoices", "invoice_id"),
        scoped_fk("vendor_bank_accounts", "bank_account_id"),
        UniqueConstraint("token_hash"),
        CheckConstraint("amount_minor > 0"),
    )

    invoice_id: Mapped[int]
    amount_minor: Mapped[int]
    currency: Mapped[str]
    bank_account_id: Mapped[int]
    bank_verified_at: Mapped[str]
    token_hash: Mapped[str]
    expires_at: Mapped[str]
    confirmed_at: Mapped[str | None]
    owner_id: Mapped[str | None]
    validation_run_id: Mapped[str | None]
    control_payment_id: Mapped[int | None]
    control_reason: Mapped[str | None]
