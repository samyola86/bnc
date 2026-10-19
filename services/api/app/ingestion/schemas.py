import uuid
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
    candidate_limit: int = Field(ge=20, le=50)


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

    @field_validator("title")
    @classmethod
    def title_not_blank(cls, value):
        if not value.strip():
            raise ValueError("Headline is required")
        return value.strip()
