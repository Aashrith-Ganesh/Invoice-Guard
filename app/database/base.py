from datetime import UTC, datetime

from sqlalchemy import ForeignKey, ForeignKeyConstraint, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="microseconds")


class Base(DeclarativeBase):
    pass


class Record:
    id: Mapped[int] = mapped_column(primary_key=True)
    created_at: Mapped[str] = mapped_column(default=utc_now)


class BusinessRecord(Record):
    business_id: Mapped[int] = mapped_column(ForeignKey("businesses.id"), index=True)


def scoped_fk(table: str, column: str) -> ForeignKeyConstraint:
    return ForeignKeyConstraint(["business_id", column], [f"{table}.business_id", f"{table}.id"])


def scoped_id() -> UniqueConstraint:
    return UniqueConstraint("business_id", "id")
