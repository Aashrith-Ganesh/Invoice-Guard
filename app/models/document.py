from sqlalchemy import CheckConstraint, Index, JSON, LargeBinary
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base, BusinessRecord, scoped_fk, scoped_id


class Document(BusinessRecord, Base):
    """An uploaded invoice PDF, its extraction, the advisory Prism rating and any human review."""

    __tablename__ = "documents"
    __table_args__ = (
        scoped_id(),
        scoped_fk("invoices", "invoice_id"),
        Index("ix_document_invoice", "business_id", "invoice_id"),
        CheckConstraint("review_status IN ('NONE', 'VERIFIED', 'REJECTED')"),
        CheckConstraint("rating_score IS NULL OR rating_score BETWEEN 0 AND 100"),
    )

    invoice_id: Mapped[int | None]
    duplicate_submission: Mapped[bool] = mapped_column(default=False)
    filename: Mapped[str]
    sha256: Mapped[str]
    size_bytes: Mapped[int]
    content: Mapped[bytes] = mapped_column(LargeBinary)
    extractor: Mapped[str]
    extraction: Mapped[dict | None] = mapped_column(JSON)
    rating_provider: Mapped[str | None]
    rating_score: Mapped[int | None]
    rating_signals: Mapped[list] = mapped_column(JSON, default=list)
    review_status: Mapped[str] = mapped_column(default="NONE")
    review_note: Mapped[str | None]
    reviewed_at: Mapped[str | None]
