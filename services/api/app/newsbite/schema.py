import unicodedata
from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class NewsBite(BaseModel):
    model_config = ConfigDict(extra="forbid")
    template_id: Literal["newspaper", "dark-editorial", "breaking-news", "modern-magazine"] = (
        "newspaper"
    )
    template_version: Literal[1] = 1
    layout_version: Literal[1] = 1
    headline: str = Field(default="", max_length=1500)
    highlight: str = Field(default="", max_length=1500)
    supporting: str = Field(default="", max_length=5000)
    speaker: str = Field(default="", max_length=250)
    source_credit: str = Field(default="", max_length=300)
    publication_date: date | None = None
    focal_x: float = Field(default=0.5, ge=0, le=1)
    focal_y: float = Field(default=0.5, ge=0, le=1)
    image_rights: Literal["unverified", "owned", "licensed", "prohibited"] = "unverified"
    footer: str = Field(default="Trusted News. A Stronger Bangladesh.", max_length=150)

    @model_validator(mode="after")
    def highlight_exists(self):
        if self.highlight and self.highlight not in self.headline:
            raise ValueError("Highlighted segment must occur exactly in the graphic headline")
        if self.highlight:
            start = self.headline.index(self.highlight)
            end = start + len(self.highlight)
            if (
                unicodedata.category(self.highlight[0]).startswith("M")
                or (
                    end < len(self.headline)
                    and unicodedata.category(self.headline[end]).startswith("M")
                )
                or (start and self.headline[start - 1] == "\u09cd")
            ):
                raise ValueError("Highlight a complete shaped character or word")
        return self
