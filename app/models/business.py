from sqlalchemy import CheckConstraint, JSON
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base, Record


class Business(Record, Base):
    __tablename__ = "businesses"
    __table_args__ = (CheckConstraint("cash_minor >= 0 AND rounding_minor >= 0"),)

    name: Mapped[str]
    currency: Mapped[str] = mapped_column(default="INR")
    cash_minor: Mapped[int]
    rounding_minor: Mapped[int] = mapped_column(default=1)
    confidence_threshold: Mapped[str] = mapped_column(default="0.85")
    field_confidence_thresholds: Mapped[dict] = mapped_column(JSON, default=dict)
    msme_days: Mapped[int] = mapped_column(default=15)
    msme_agreement_days: Mapped[int] = mapped_column(default=45)
    standard_days: Mapped[int] = mapped_column(default=30)
    priority_weights: Mapped[list] = mapped_column(JSON, default=lambda: [50, 25, 15, 10])
