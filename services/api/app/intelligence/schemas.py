from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

TAXONOMY = [
    "Bangladesh",
    "Politics & Governance",
    "Business & Economy",
    "Technology",
    "World",
    "Science & Environment",
    "Health",
    "Education",
    "Sports",
    "Entertainment",
    "Lifestyle",
]
WEIGHTS = {
    "bangladesh_relevance": 0.30,
    "public_impact": 0.25,
    "trend_momentum": 0.20,
    "evidence_quality": 0.15,
    "freshness_originality": 0.10,
}


class Controls(BaseModel):
    model_config = ConfigDict(extra="forbid")
    automatic_classification: bool = False
    paused: bool = False
    model: str = ""
    daily_budget_usd: float = Field(default=1, gt=0, le=100)
    cycle_limit: int = Field(default=50, ge=5, le=100)
    ai_cycle_limit: int = Field(default=5, ge=0, le=10)
    concurrency: int = Field(default=1, ge=1, le=4)
    cadence_minutes: int = Field(default=15, ge=5, le=1440)
    taxonomy: list[str] = Field(
        default_factory=lambda: TAXONOMY.copy(), min_length=2, max_length=30
    )
    weights: dict[str, float] = Field(default_factory=lambda: WEIGHTS.copy())

    @field_validator("taxonomy")
    @classmethod
    def valid_taxonomy(cls, values):
        normalized = [" ".join(v.split()) for v in values]
        keys = ["".join(c for c in v.casefold() if c.isalnum()) for v in normalized]
        if len(set(keys)) != len(keys) or any(not v or len(v) > 80 for v in normalized):
            raise ValueError("Taxonomy labels must be distinct and nonempty")
        return normalized

    @model_validator(mode="after")
    def valid_weights(self):
        if (
            set(self.weights) != set(WEIGHTS)
            or any(not 0 <= v <= 1 for v in self.weights.values())
            or abs(sum(self.weights.values()) - 1) > 0.00001
        ):
            raise ValueError("Use all five ranking weights with a total of 1")
        return self


class Classification(BaseModel):
    model_config = ConfigDict(extra="forbid")
    primary_category: str
    secondary_category: str | None
    tags: list[str]
    topic_keywords: list[str]
    entities: list[str]
    geography: list[str]
    bangladesh_relevance: int = Field(ge=0, le=100)
    public_interest: int = Field(ge=0, le=100)
    confidence: float = Field(ge=0, le=1)
    evidence_limitations: list[str]

    @field_validator("tags", "topic_keywords", "entities", "geography", "evidence_limitations")
    @classmethod
    def bounded_lists(cls, values):
        if len(values) > 20 or any(len(v) > 300 for v in values):
            raise ValueError("Classification metadata exceeds bounds")
        return list(dict.fromkeys(values))
