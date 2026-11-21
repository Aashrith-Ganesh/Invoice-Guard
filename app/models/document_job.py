from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column
from app.database.base import Base


class DocumentJob(Base):
    __tablename__ = "sarvam_document_jobs"
    job_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    business_id: Mapped[int] = mapped_column(ForeignKey("businesses.id"))
