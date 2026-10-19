import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.ingestion.network import public_url

SourceType = Literal["rss", "website", "api", "json_feed", "manual"]
Rights = Literal["unverified", "metadata_only", "licensed", "owned", "prohibited"]


class SourceInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    publisher: str = Field(min_length=1, max_length=200)
    url: str = Field(min_length=1, max_length=2048)
    source_type: SourceType = "rss"
    feed_url: str | None = Field(default=None, max_length=2048)
    language: Literal["bn", "en"] = "bn"
    category: str = Field(default="", max_length=100)
    rights: Rights = "metadata_only"
    extraction_mode: Literal["metadata", "reference_only"] = "metadata"
    polling_interval: int = Field(default=15, ge=5, le=1440)
    active: bool = True
    notes: str = Field(default="", max_length=4000)
    draft_language: Literal["bn", "en"] | None = None

    @field_validator("url", "feed_url")
    @classmethod
    def validate_url(cls, value):
        return public_url(value) if value else None

    @field_validator("publisher")
    @classmethod
    def publisher_not_blank(cls, value):
        if not value.strip():
            raise ValueError("Publisher name is required")
        return value.strip()


class TestInput(BaseModel):
    url: str = Field(min_length=1, max_length=2048)
    source_type: SourceType = "rss"
    feed_url: str | None = Field(default=None, max_length=2048)
    rights: Rights = "metadata_only"
    extraction_mode: Literal["metadata", "reference_only"] = "metadata"

    @field_validator("url", "feed_url")
    @classmethod
    def validate_url(cls, value):
        return public_url(value) if value else None


class QueueSettingsInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    candidate_limit: int | None = Field(default=None, ge=20, le=50)
    default_interval: int | None = Field(default=None, ge=5, le=1440)
    draft_language: Literal["bn", "en"] | None = None
    source_mode: Literal["all_supported", "feeds_only"] | None = None
    preferred_categories: list[str] | None = Field(default=None, max_length=20)
    automatic_collection: bool | None = None

    @field_validator("preferred_categories")
    @classmethod
    def categories_not_blank(cls, value):
        if value is not None and any(not v.strip() or len(v) > 100 for v in value):
            raise ValueError("Categories must have 1–100 characters")
        return list(dict.fromkeys(v.strip() for v in value)) if value is not None else None


class CollectionSettings(BaseModel):
    candidate_limit: int = 30
    default_interval: int = 15
    draft_language: Literal["bn", "en"] = "bn"
    source_mode: Literal["all_supported", "feeds_only"] = "all_supported"
    preferred_categories: list[str] = Field(default_factory=list)
    automatic_collection: bool = True


class CandidatePatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    editorial_status: Literal["DISCOVERED", "SELECTED", "DISMISSED"] | None = None
    pinned: bool | None = None
    rank_override: int | None = Field(default=None, ge=0, le=100)
    bangladesh_relevance: int | None = Field(default=None, ge=0, le=100)
    public_impact: int | None = Field(default=None, ge=0, le=100)
    corroboration: int | None = Field(default=None, ge=0, le=100)
    uniqueness: int | None = Field(default=None, ge=0, le=100)


class CreditInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    source_id: uuid.UUID | None = None
    publisher_name: str = Field(default="", max_length=200)
    original_url: str | None = Field(default=None, max_length=2048)
    attribution_text: str = Field(default="", max_length=2000)
    is_original_reporting: bool = False
    rights_status: Rights = "unverified"

    @field_validator("original_url")
    @classmethod
    def validate_url(cls, value):
        return public_url(value) if value else None


class DraftInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    base_version: int = Field(ge=1)
    title: str = Field(min_length=1, max_length=500)
    summary: str = Field(default="", max_length=5000)
    body: str = Field(default="", max_length=100000)
    category: str = Field(default="", max_length=100)
    credits: list[CreditInput] = Field(default_factory=list, max_length=30)
    language: Literal["bn", "en"] | None = None
    tags: list[str] = Field(default_factory=list, max_length=20)
    social_captions: dict[Literal["facebook", "instagram"], str] = Field(default_factory=dict)
    ai_job_id: uuid.UUID | None = None
    format: Literal["article", "news_bite"] = "article"
    contributors: list[str] = Field(default_factory=list, max_length=20)
    cover_image_id: uuid.UUID | None = None
    image_alt: str = Field(default="", max_length=1000)
    image_caption: str = Field(default="", max_length=2000)
    reporting_notes: str = Field(default="", max_length=10000)
    destinations: list[Literal["wordpress", "facebook", "instagram", "linkedin", "x"]] = Field(
        default_factory=list, max_length=5
    )
    social_caption: str = Field(default="", max_length=5000)
    scheduled_at: datetime | None = None

    @field_validator("scheduled_at")
    @classmethod
    def timezone_required(cls, value):
        if value and value.utcoffset() is None:
            raise ValueError("Schedule must include a timezone")
        return value

    @field_validator("contributors")
    @classmethod
    def bounded_contributors(cls, value):
        if any(not name.strip() or len(name) > 200 for name in value):
            raise ValueError("Contributor names must contain 1–200 characters")
        return list(dict.fromkeys(name.strip() for name in value))

    @field_validator("tags")
    @classmethod
    def bounded_tags(cls, value):
        if any(not tag.strip() or len(tag) > 100 for tag in value):
            raise ValueError("Tags must contain 1–100 characters")
        return list(dict.fromkeys(tag.strip() for tag in value))

    @field_validator("social_captions")
    @classmethod
    def bounded_captions(cls, value):
        if any(len(caption) > 5000 for caption in value.values()):
            raise ValueError("Captions must be at most 5000 characters")
        return value

    @field_validator("title")
    @classmethod
    def title_not_blank(cls, value):
        if not value.strip():
            raise ValueError("Headline is required")
        return value.strip()
