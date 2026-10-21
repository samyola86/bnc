"""Import every mapped model for Alembic metadata discovery."""

from app.ai.models import AIJob
from app.auth.models import AuthAttempt, LoginSession, ResetToken, User
from app.editorial.models import AuditEvent, Story, StorySource, StoryVersion
from app.ingestion.models import (
    CollectionRun,
    Feed,
    FeedEntry,
    IngestedItem,
    IngestionSettings,
    Source,
)
from app.intelligence.models import (
    ClusterMember,
    IntelligenceSettings,
    IntelligenceUsage,
    ItemAnalysis,
    ProviderObservation,
    StoryCluster,
    TrendSnapshot,
)
from app.publishing.models import Channel, Publication, PublishingRequest, ReviewDecision
from app.tasks.models import NewsroomTask

__all__ = [
    "IntelligenceSettings",
    "ItemAnalysis",
    "StoryCluster",
    "ClusterMember",
    "TrendSnapshot",
    "IntelligenceUsage",
    "ProviderObservation",
    "AuthAttempt",
    "LoginSession",
    "ResetToken",
    "ReviewDecision",
    "NewsroomTask",
    "AIJob",
    "User",
    "Story",
    "StoryVersion",
    "Source",
    "Channel",
    "Publication",
    "PublishingRequest",
    "Feed",
    "FeedEntry",
    "IngestedItem",
    "IngestionSettings",
    "CollectionRun",
    "StorySource",
    "AuditEvent",
]
