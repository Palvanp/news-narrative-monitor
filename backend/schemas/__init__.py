from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

SUPPORTED_LANGUAGES = {"en", "hi"}


class MonitorCreate(BaseModel):
    topic: str = Field(min_length=3, max_length=300)
    hindi_keywords: str | None = Field(default=None, max_length=300)
    languages: list[str] = Field(default_factory=lambda: ["en", "hi"])
    time_range_hours: int = Field(default=24, ge=1, le=24 * 7)

    @field_validator("languages")
    @classmethod
    def _languages(cls, value: list[str]) -> list[str]:
        value = [v.strip().lower() for v in value if v.strip()]
        if not value or not set(value) <= SUPPORTED_LANGUAGES:
            raise ValueError(f"languages must be a non-empty subset of {sorted(SUPPORTED_LANGUAGES)}")
        return sorted(set(value), key=["en", "hi"].index)


class RunOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    monitor_id: int
    status: str
    stage: str | None
    progress: float
    message: str | None
    error: str | None
    window_start: datetime | None
    window_end: datetime | None
    stats: dict
    started_at: datetime | None
    finished_at: datetime | None


class MonitorOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    topic: str
    hindi_keywords: str | None
    languages: list[str]
    time_range_hours: int
    created_at: datetime
    latest_run: RunOut | None = None


class EntityOut(BaseModel):
    id: int
    name: str
    type: str
    articles: int


class NarrativeCard(BaseModel):
    id: int
    run_id: int
    label: str
    label_source: str
    summary: str | None
    keywords: list[str]
    volume: int
    growth_pct: float | None
    is_new: bool
    sentiment: dict[str, float]
    languages: dict[str, float]
    unique_sources: int
    spikes: list[str]
    top_entities: list[EntityOut]


class NarrativeDetail(NarrativeCard):
    monitor_id: int
    topic: str
    stats: dict


class EvidenceItem(BaseModel):
    article_id: int
    title: str
    url: str
    source: str | None
    language: str | None
    published_at: datetime | None
    sentiment: str | None
    similarity: float
    is_representative: bool
    evidence_text: str | None
    syndicated_copies: int


class RelatedNarrative(BaseModel):
    id: int
    label: str
    similarity: float


class TimelineSeries(BaseModel):
    narrative_id: int
    label: str
    counts: list[int]


class Timeline(BaseModel):
    run_id: int
    edges: list[str]
    series: list[TimelineSeries]


class BriefOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    run_id: int
    model: str
    status: str
    error: str | None
    content: dict | None
    markdown: str | None
    created_at: datetime


class TrendingTopic(BaseModel):
    topic: str
    en: int
    hi: int
    headlines: list[str]


class Trending(BaseModel):
    window_hours: int
    generated_at: datetime
    topics: list[TrendingTopic]
    error: str | None = None
