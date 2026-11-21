from sqlalchemy import CheckConstraint, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base, BusinessRecord, scoped_fk, scoped_id


class Payment(BusinessRecord, Base):
    __tablename__ = "payments"
    __table_args__ = (
        scoped_id(),
        scoped_fk("invoices", "invoice_id"),
        scoped_fk("approvals", "approval_id"),
        scoped_fk("vendor_bank_accounts", "bank_account_id"),
        UniqueConstraint("business_id", "idempotency_key"),
        UniqueConstraint("business_id", "approval_id"),
        CheckConstraint("amount_minor > 0"),
        CheckConstraint("status IN ('PENDING_APPROVAL', 'APPROVED', 'INITIATED', 'SUCCESS', 'FAILED', 'UNKNOWN', 'REVERSED')"),
    )

    invoice_id: Mapped[int] = mapped_column(index=True)
    approval_id: Mapped[int]
    bank_account_id: Mapped[int]
    amount_minor: Mapped[int]
    currency: Mapped[str]
    idempotency_key: Mapped[str]
    external_reference: Mapped[str] = mapped_column(unique=True)
    status: Mapped[str]
