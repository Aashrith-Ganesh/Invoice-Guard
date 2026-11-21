from sqlalchemy import JSON
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base, BusinessRecord


class AuditLog(BusinessRecord, Base):
    __tablename__ = "audit_logs"

    action: Mapped[str]
    entity_id: Mapped[int]
    details: Mapped[dict] = mapped_column(JSON, default=dict)
