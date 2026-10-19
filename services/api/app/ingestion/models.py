import uuid
from datetime import datetime

from sqlalchemy import JSON, CheckConstraint, DateTime, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, Record


class Source(Record, Base):
    __tablename__ = "sources"

    publisher: Mapped[str] = mapped_column(String(200))
    homepage: Mapped[str] = mapped_column(String(2048))
    language: Mapped[str] = mapped_column(String(8), default="bn")
    rights: Mapped[str] = mapped_column(String(100), default="unverified")
    notes: Mapped[str | None] = mapped_column(Text)
    source_type: Mapped[str] = mapped_column(String(24), default="rss")
    url: Mapped[str] = mapped_column(String(2048), default="")
    feed_url: Mapped[str | None] = mapped_column(String(2048))
    category: Mapped[str] = mapped_column(String(100), default="")
    active: Mapped[bool] = mapped_column(default=True)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    draft_language: Mapped[str | None] = mapped_column(String(8))
    extraction_mode: Mapped[str] = mapped_column(String(24), default="metadata")
    polling_interval: Mapped[int] = mapped_column(default=15)
    health: Mapped[str] = mapped_column(String(24), default="UNTESTED")
    last_checked: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_success: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(Text)
    next_collection_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    failure_count: Mapped[int] = mapped_column(default=0)
    collection_lock_id: Mapped[uuid.UUID | None]
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        CheckConstraint("polling_interval BETWEEN 5 AND 1440", name="ck_source_frequency"),
        CheckConstraint(
            "source_type IN ('rss','website','api','json_feed','manual')", name="ck_source_type"
        ),
        CheckConstraint(
            "extraction_mode IN ('metadata','reference_only')", name="ck_source_extraction"
        ),
    )


class Feed(Record, Base):
    __tablename__ = "feeds"
    __table_args__ = (UniqueConstraint("source_id", "url", name="uq_source_feed"),)

    source_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("sources.id"), index=True)
    url: Mapped[str] = mapped_column(String(2048))
    title: Mapped[str] = mapped_column(String(500), default="")
    etag: Mapped[str | None] = mapped_column(String(500))
    last_modified: Mapped[str | None] = mapped_column(String(200))
    last_success: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class IngestedItem(Record, Base):
    """One canonical candidate; FeedEntry retains every feed's provenance."""

    __tablename__ = "ingested_items"
    __table_args__ = (
        CheckConstraint(
            "editorial_status IN ('DISCOVERED','SELECTED','DRAFT','DISMISSED')",
            name="ck_candidate_status",
        ),
        CheckConstraint("bangladesh_relevance BETWEEN 0 AND 100", name="ck_rank_relevance"),
        CheckConstraint("public_impact BETWEEN 0 AND 100", name="ck_rank_impact"),
        CheckConstraint("corroboration BETWEEN 0 AND 100", name="ck_rank_corroboration"),
        CheckConstraint("uniqueness BETWEEN 0 AND 100", name="ck_rank_uniqueness"),
        CheckConstraint(
            "rank_override IS NULL OR rank_override BETWEEN 0 AND 100", name="ck_rank_override"
        ),
    )

    normalized_url: Mapped[str] = mapped_column(String(2048), unique=True)
    content_hash: Mapped[str] = mapped_column(String(64), unique=True)
    title: Mapped[str] = mapped_column(String(500))
    excerpt: Mapped[str] = mapped_column(Text, default="")
    category: Mapped[str] = mapped_column(String(100), default="")
    language: Mapped[str] = mapped_column(String(8), default="bn")
    author: Mapped[str] = mapped_column(String(200), default="")
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    editorial_status: Mapped[str] = mapped_column(String(24), default="DISCOVERED", index=True)
    pinned: Mapped[bool] = mapped_column(default=False)
    bangladesh_relevance: Mapped[int] = mapped_column(default=50)
    public_impact: Mapped[int] = mapped_column(default=50)
    corroboration: Mapped[int] = mapped_column(default=0)
    uniqueness: Mapped[int] = mapped_column(default=50)
    rank_override: Mapped[int | None]


class FeedEntry(Record, Base):
    __tablename__ = "feed_entries"
    __table_args__ = (UniqueConstraint("feed_id", "guid", name="uq_feed_guid"),)

    feed_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("feeds.id"), index=True)
    item_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("ingested_items.id"), index=True)
    guid: Mapped[str] = mapped_column(String(64))
    original_url: Mapped[str] = mapped_column(String(2048))
    publisher_name: Mapped[str] = mapped_column(String(200))
    rights_status: Mapped[str] = mapped_column(String(100))
    source_type: Mapped[str] = mapped_column(String(24))
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class CollectionRun(Record, Base):
    __tablename__ = "collection_runs"
    __table_args__ = (
        CheckConstraint(
            "status IN ('PENDING','RUNNING','SUCCEEDED','FAILED','SKIPPED')",
            name="ck_collection_status",
        ),
    )

    source_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("sources.id"), index=True)
    status: Mapped[str] = mapped_column(String(24), default="PENDING", index=True)
    trigger: Mapped[str] = mapped_column(String(16), default="manual")
    message: Mapped[str] = mapped_column(Text, default="Queued for collection")
    inserted: Mapped[int] = mapped_column(default=0)
    duplicates: Mapped[int] = mapped_column(default=0)
    skipped: Mapped[int] = mapped_column(default=0)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class IngestionSettings(Base):
    __tablename__ = "ingestion_settings"
    __table_args__ = (
        CheckConstraint("candidate_limit BETWEEN 20 AND 50", name="ck_candidate_limit"),
        CheckConstraint("default_interval BETWEEN 5 AND 1440", name="ck_default_interval"),
        CheckConstraint("draft_language IN ('bn','en')", name="ck_default_draft_language"),
        CheckConstraint("source_mode IN ('all_supported','feeds_only')", name="ck_source_mode"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    candidate_limit: Mapped[int] = mapped_column(default=30)
    default_interval: Mapped[int] = mapped_column(default=15)
    draft_language: Mapped[str] = mapped_column(String(8), default="bn")
    source_mode: Mapped[str] = mapped_column(String(24), default="all_supported")
    preferred_categories: Mapped[list] = mapped_column(JSON, default=list)
    automatic_collection: Mapped[bool] = mapped_column(default=True)
