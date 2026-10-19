import enum
import uuid
from datetime import datetime

from sqlalchemy import JSON, CheckConstraint, DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, Record


class PublicationState(enum.StrEnum):
    PENDING = "PENDING"
    SCHEDULED = "SCHEDULED"
    RUNNING = "RUNNING"
    CONFIRMED = "CONFIRMED"
    RETRYABLE_FAILED = "RETRYABLE_FAILED"
    PERMANENT_FAILED = "PERMANENT_FAILED"
    UNKNOWN_RECONCILE = "UNKNOWN_RECONCILE"
    CANCELLED = "CANCELLED"


class Channel(Record, Base):
    __tablename__ = "channels"

    type: Mapped[str] = mapped_column(String(40))
    remote_account_id: Mapped[str | None] = mapped_column(String(200))
    encrypted_secret_reference: Mapped[str | None] = mapped_column(String(500))


class Publication(Record, Base):
    __tablename__ = "publications"
    __table_args__ = (
        CheckConstraint(
            "status IN (" + ",".join(f"'{state.value}'" for state in PublicationState) + ")",
            name="ck_publication_status",
        ),
    )

    # Story is derived through the approved revision, avoiding mismatched story IDs.
    approved_version_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("story_versions.id"))
    channel_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("channels.id"), index=True)
    status: Mapped[str] = mapped_column(String(32), default="PENDING", index=True)
    remote_id: Mapped[str | None] = mapped_column(String(200))
    permalink: Mapped[str | None] = mapped_column(String(2048))
    scheduled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class PublishingRequest(Record, Base):
    """Editorial queue intent; never a claim of platform delivery or approval."""

    __tablename__ = "publishing_requests"
    __table_args__ = (
        CheckConstraint("status IN ('QUEUED','SCHEDULED','CANCELLED')", name="ck_request_status"),
    )
    story_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("stories.id"), index=True)
    version_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("story_versions.id"))
    destinations: Mapped[list] = mapped_column(JSON)
    scheduled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(24), index=True)
