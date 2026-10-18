import enum
import uuid

from sqlalchemy import JSON, CheckConstraint, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, Record


class EditorialState(enum.StrEnum):
    DISCOVERED = "DISCOVERED"
    SELECTED = "SELECTED"
    DRAFT = "DRAFT"
    IN_REVIEW = "IN_REVIEW"
    CHANGES_REQUESTED = "CHANGES_REQUESTED"
    APPROVED = "APPROVED"
    READY = "READY"
    UPDATED = "UPDATED"
    CORRECTED = "CORRECTED"
    RETRACTED = "RETRACTED"


class Story(Record, Base):
    __tablename__ = "stories"
    __table_args__ = (
        CheckConstraint("language IN ('bn', 'en')", name="ck_story_language"),
        CheckConstraint(
            "status IN (" + ",".join(f"'{state.value}'" for state in EditorialState) + ")",
            name="ck_story_status",
        ),
    )

    type: Mapped[str] = mapped_column(String(32), default="article")
    language: Mapped[str] = mapped_column(String(8), default="bn")
    status: Mapped[str] = mapped_column(String(32), default="DRAFT", index=True)
    author_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    # Composite revision references are introduced with the write workflow so that
    # cross-story approval and stale-write checks can be enforced together.


class StoryVersion(Record, Base):
    __tablename__ = "story_versions"
    __table_args__ = (
        UniqueConstraint("story_id", "version_number", name="uq_story_revision"),
        CheckConstraint("version_number > 0", name="ck_positive_revision"),
    )

    story_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("stories.id"), index=True)
    version_number: Mapped[int]
    editor_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    title: Mapped[str] = mapped_column(String(500))
    content_json: Mapped[dict] = mapped_column(JSON, default=dict)
