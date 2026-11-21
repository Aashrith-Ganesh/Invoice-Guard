from sqlalchemy import CheckConstraint, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base, BusinessRecord, scoped_fk


class PaymentLink(BusinessRecord, Base):
    __tablename__ = "payment_links"
    __table_args__ = (
        scoped_fk("invoices", "invoice_id"),
        scoped_fk("approvals", "approval_id"),
        scoped_fk("payments", "payment_id"),
        UniqueConstraint("business_id", "approval_id"),
        UniqueConstraint("business_id", "payment_id"),
        CheckConstraint("amount_minor > 0"),
    )

    invoice_id: Mapped[int]
    approval_id: Mapped[int]
    payment_id: Mapped[int | None]
    reference: Mapped[str] = mapped_column(unique=True)
    invoice_reference: Mapped[str]
    vendor_name: Mapped[str]
    amount_minor: Mapped[int]
    currency: Mapped[str]
    expires_at: Mapped[str]
