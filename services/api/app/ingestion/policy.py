"""Global defaults never replace existing per-source editorial choices."""

from app.ingestion.models import IngestionSettings
from app.ingestion.schemas import CollectionSettings


def collection_settings(session) -> CollectionSettings:
    row = session.get(IngestionSettings, 1)
    return (
        CollectionSettings.model_validate(row, from_attributes=True)
        if row
        else CollectionSettings()
    )


def scheduled_allowed(session, source) -> bool:
    policy = collection_settings(session)
    return policy.automatic_collection and (
        policy.source_mode == "all_supported" or source.source_type in {"rss", "json_feed"}
    )
