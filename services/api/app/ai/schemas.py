from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class GenerateInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    base_version: int = Field(ge=1)
    language: Literal["bn", "en"]
    reporting_notes: str = Field(default="", max_length=15000)
    notes_permitted: bool = False


class StrictOutput(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class Paragraph(StrictOutput):
    text: str = Field(min_length=1, max_length=10000)
    supporting_source_ids: list[str] = Field(min_length=1, max_length=30)

    @field_validator("text")
    @classmethod
    def nonblank_text(cls, value):
        if not value.strip():
            raise ValueError("A paragraph cannot be blank")
        return value


class Captions(StrictOutput):
    facebook: str = Field(max_length=5000)
    instagram: str = Field(max_length=5000)


class GeneratedDraft(StrictOutput):
    language: Literal["bn", "en"]
    headline: str = Field(min_length=1, max_length=500)
    summary: str = Field(max_length=5000)
    paragraphs: list[Paragraph] = Field(min_length=1, max_length=30)
    category: str = Field(max_length=100)
    tags: list[str] = Field(max_length=20)
    social_captions: Captions
    claims_to_verify: list[str] = Field(max_length=50)
    editorial_warnings: list[str] = Field(max_length=30)
    ready_for_review: Literal[False]

    @field_validator("headline")
    @classmethod
    def nonblank_headline(cls, value):
        if not value.strip():
            raise ValueError("Headline cannot be blank")
        return value.strip()
