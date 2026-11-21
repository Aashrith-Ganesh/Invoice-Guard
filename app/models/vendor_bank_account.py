from sqlalchemy import Index, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base, BusinessRecord, scoped_fk, scoped_id


class VendorBankAccount(BusinessRecord, Base):
    __tablename__ = "vendor_bank_accounts"
    __table_args__ = (
        scoped_id(),
        scoped_fk("vendors", "vendor_id"),
        UniqueConstraint("business_id", "vendor_id", "reference"),
        Index("uq_vendor_primary_account", "business_id", "vendor_id", unique=True,
              sqlite_where=text("is_primary = 1")),
    )

    vendor_id: Mapped[int]
    reference: Mapped[str]
    is_primary: Mapped[bool] = mapped_column(default=False)
    verified_at: Mapped[str | None]
    retired_at: Mapped[str | None]
