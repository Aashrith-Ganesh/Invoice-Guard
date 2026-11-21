from sqlalchemy import CheckConstraint, JSON
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base, BusinessRecord, scoped_fk


class InvoiceValidation(BusinessRecord, Base):
    __tablename__ = "invoice_validations"
    __table_args__ = (
        scoped_fk("invoices", "invoice_id"),
        CheckConstraint("status IN ('PASS', 'HOLD', 'BLOCK')"),
    )

    invoice_id: Mapped[int] = mapped_column(index=True)
    duplicate_submission: Mapped[bool] = mapped_column(default=False)
    run_id: Mapped[str]
    code: Mapped[str]
    status: Mapped[str]
    detail: Mapped[str]
    fields: Mapped[list] = mapped_column(JSON)
