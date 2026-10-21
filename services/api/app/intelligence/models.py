import uuid
from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, Record


class IntelligenceSettings(Base):
    __tablename__ = "intelligence_settings"
    id: Mapped[int] = mapped_column(primary_key=True)
    config: Mapped[dict] = mapped_column(JSON)
    last_cycle: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    lease_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ItemAnalysis(Record, Base):
    __tablename__ = "item_analyses"
    item_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("ingested_items.id"), unique=True)
    input_hash: Mapped[str] = mapped_column(String(64))
    model: Mapped[str] = mapped_column(String(200))
    prompt_version: Mapped[str] = mapped_column(String(40))
    status: Mapped[str] = mapped_column(String(24))
    result: Mapped[dict] = mapped_column(JSON)
    editorial_override: Mapped[dict] = mapped_column(JSON, default=dict)


class StoryCluster(Record, Base):
    __tablename__ = "story_clusters"
    title: Mapped[str] = mapped_column(String(500))
    category: Mapped[str] = mapped_column(String(100))
    keywords: Mapped[list] = mapped_column(JSON)
    last_activity: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    confidence: Mapped[float] = mapped_column()
    editorial_lock: Mapped[bool] = mapped_column(default=False)
    dismissed: Mapped[bool] = mapped_column(default=False)
    pinned: Mapped[bool] = mapped_column(default=False)
    score_override: Mapped[int | None]


class ClusterMember(Record, Base):
    __tablename__ = "cluster_members"
    cluster_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("story_clusters.id"), index=True)
    item_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("ingested_items.id"), unique=True)
    editorial_lock: Mapped[bool] = mapped_column(default=False)


class TrendSnapshot(Record, Base):
    __tablename__ = "trend_snapshots"
    __table_args__ = (UniqueConstraint("cluster_id", "window", "bucket"),)
    cluster_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("story_clusters.id"), index=True)
    window: Mapped[str] = mapped_column(String(8))
    bucket: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    momentum: Mapped[float] = mapped_column()
    score: Mapped[float] = mapped_column()
    signals: Mapped[dict] = mapped_column(JSON)


class IntelligenceUsage(Record, Base):
    __tablename__ = "intelligence_usage"
    cache_key: Mapped[str] = mapped_column(String(64), unique=True)
    item_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("ingested_items.id"))
    day: Mapped[str] = mapped_column(String(10), index=True)
    model: Mapped[str] = mapped_column(String(200))
    prompt_version: Mapped[str] = mapped_column(String(40))
    status: Mapped[str] = mapped_column(String(24))
    input_tokens: Mapped[int] = mapped_column(default=0)
    output_tokens: Mapped[int] = mapped_column(default=0)
    reserved_usd: Mapped[float] = mapped_column(Numeric(14, 8))
    cost_usd: Mapped[float | None] = mapped_column(Numeric(14, 8))
    result: Mapped[dict] = mapped_column(JSON, default=dict)
    error: Mapped[str] = mapped_column(String(1000), default="")


class ProviderObservation(Record, Base):
    __tablename__ = "provider_observations"
    provider: Mapped[str] = mapped_column(String(40), index=True)
    topic: Mapped[str] = mapped_column(String(300))
    geography: Mapped[str] = mapped_column(String(20))
    metrics: Mapped[dict] = mapped_column(JSON)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
