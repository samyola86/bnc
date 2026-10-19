from sqlalchemy import func, select

from app.editorial.models import Story, StoryVersion
from app.ingestion.models import IngestedItem
from app.publishing.models import Publication, PublishingRequest


def newsroom_summary(session):
    incoming = (
        session.scalar(
            select(func.count())
            .select_from(IngestedItem)
            .where(IngestedItem.editorial_status.in_(["DISCOVERED", "SELECTED"]))
        )
        or 0
    )
    originals = (
        session.scalar(
            select(func.count())
            .select_from(Story)
            .where(Story.origin_item_id.is_(None), Story.status.in_(["DRAFT", "CHANGES_REQUESTED"]))
        )
        or 0
    )

    def publication_count(states):
        return (
            session.scalar(
                select(func.count(func.distinct(StoryVersion.story_id)))
                .select_from(Publication)
                .join(StoryVersion, Publication.approved_version_id == StoryVersion.id)
                .where(Publication.status.in_(states))
            )
            or 0
        )

    awaiting = (
        select(StoryVersion.story_id)
        .join(Publication, Publication.approved_version_id == StoryVersion.id)
        .where(Publication.status.in_(["PENDING", "SCHEDULED", "RUNNING", "RETRYABLE_FAILED"]))
    )
    queued = select(PublishingRequest.story_id).where(PublishingRequest.status != "CANCELLED")
    awaiting_count = session.scalar(
        select(func.count()).select_from(awaiting.union(queued).subquery())
    )
    return {
        "incoming": {
            "count": incoming,
            "available": True,
            "definition": "Stored discovered and selected candidates, including inactive sources",
        },
        "original_drafts": {
            "count": originals,
            "available": True,
            "definition": "Independently authored stories in draft or changes requested",
        },
        "awaiting_publication": {
            "count": awaiting_count or 0,
            "available": True,
            "definition": "Queued stories and pending deliveries; platform connections required",
        },
        "published": {
            "count": publication_count(["CONFIRMED"]),
            "available": False,
            "definition": "Stored confirmed deliveries; publishing workflow is not implemented",
        },
    }
