import uuid
from datetime import datetime

from sqlalchemy import JSON, CheckConstraint, DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, Record


class AIJob(Record, Base):
    __tablename__ = "ai_jobs"
    __table_args__ = (
        CheckConstraint(
            "status IN ('PENDING','RUNNING','SUCCEEDED','FAILED')", name="ck_ai_status"
        ),
    )

    story_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("stories.id"), index=True)
    editor_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True)
    base_version: Mapped[int]
    model: Mapped[str] = mapped_column(String(200))
    template_version: Mapped[str] = mapped_column(String(50), default="news-draft-v1")
    input_hash: Mapped[str] = mapped_column(String(64))
    input_json: Mapped[dict] = mapped_column(JSON)
    result: Mapped[dict | None] = mapped_column(JSON)
    usage: Mapped[dict | None] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(24), default="PENDING", index=True)
    message: Mapped[str] = mapped_column(Text, default="Queued for AI drafting")
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
