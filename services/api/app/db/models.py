"""Import every mapped model for Alembic metadata discovery."""

from app.auth.models import User
from app.editorial.models import AuditEvent, Story, StorySource, StoryVersion
from app.ingestion.models import (
    CollectionRun,
    Feed,
    FeedEntry,
    IngestedItem,
    IngestionSettings,
    Source,
)
from app.publishing.models import Channel, Publication

__all__ = [
    "User",
    "Story",
    "StoryVersion",
    "Source",
    "Channel",
    "Publication",
    "Feed",
    "FeedEntry",
    "IngestedItem",
    "IngestionSettings",
    "CollectionRun",
    "StorySource",
    "AuditEvent",
]
