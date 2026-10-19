import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, Record


class NewsroomTask(Record, Base):
    __tablename__ = "newsroom_tasks"
    __table_args__ = (
        CheckConstraint(
            "status IN ('TO_DO','IN_PROGRESS','IN_REVIEW','COMPLETED')", name="ck_task_status"
        ),
        CheckConstraint("priority IN ('LOW','MEDIUM','HIGH','URGENT')", name="ck_task_priority"),
    )
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text, default="")
    assignee_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True)
    creator_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    story_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("stories.id"), index=True)
    priority: Mapped[str] = mapped_column(String(16), default="MEDIUM")
    status: Mapped[str] = mapped_column(String(24), default="TO_DO")
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    feedback: Mapped[str] = mapped_column(Text, default="")
