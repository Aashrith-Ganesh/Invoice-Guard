from sqlalchemy import CheckConstraint, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base, BusinessRecord, scoped_id


class Vendor(BusinessRecord, Base):
    __tablename__ = "vendors"
    __table_args__ = (
        scoped_id(),
        UniqueConstraint("business_id", "gstin"),
        CheckConstraint("classification IN ('Micro', 'Small', 'Medium', 'Non-MSME')"),
        CheckConstraint("priority BETWEEN 0 AND 100"),
    )

    gstin: Mapped[str]
    legal_name: Mapped[str]
    classification: Mapped[str]
    priority: Mapped[int] = mapped_column(default=50)
