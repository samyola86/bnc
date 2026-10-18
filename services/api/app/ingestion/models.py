from sqlalchemy import String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, Record


class Source(Record, Base):
    __tablename__ = "sources"

    publisher: Mapped[str] = mapped_column(String(200))
    homepage: Mapped[str] = mapped_column(String(2048))
    language: Mapped[str] = mapped_column(String(8), default="bn")
    rights: Mapped[str] = mapped_column(String(100), default="unverified")
    notes: Mapped[str | None] = mapped_column(Text)
