from datetime import date

from sqlalchemy import CheckConstraint, Index, JSON, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base, BusinessRecord, scoped_fk, scoped_id


class Invoice(BusinessRecord, Base):
    __tablename__ = "invoices"
    __table_args__ = (
        scoped_id(),
        scoped_fk("vendors", "vendor_id"),
        scoped_fk("vendor_bank_accounts", "bank_account_id"),
        UniqueConstraint("business_id", "vendor_id", "normalized_invoice_number"),
        Index("ix_invoice_document", "business_id", "document_sha256"),
        Index("ix_invoice_secondary", "business_id", "vendor_id", "invoice_date", "amount_minor", "currency"),
        CheckConstraint("overall_status IN ('PASS', 'HOLD', 'BLOCK')"),
    )

    vendor_id: Mapped[int | None]
    bank_account_id: Mapped[int | None]
    bank_verified_at: Mapped[str | None]
    normalized_invoice_number: Mapped[str | None]
    invoice_date: Mapped[date | None]
    acceptance_date: Mapped[date | None]
    written_agreement: Mapped[bool | None]
    payment_deadline: Mapped[date | None]
    amount_minor: Mapped[int | None]
    currency: Mapped[str | None]
    document_sha256: Mapped[str | None]
    extracted: Mapped[dict] = mapped_column(JSON)
    overall_status: Mapped[str]
