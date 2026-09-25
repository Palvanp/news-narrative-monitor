from datetime import datetime, timezone

from sqlalchemy import (
    JSON,
    Boolean,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from backend.models.types import Embedding, UTCDateTime

EMBEDDING_DIM = 1024


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class Monitor(Base):
    __tablename__ = "monitors"

    id: Mapped[int] = mapped_column(primary_key=True)
    topic: Mapped[str] = mapped_column(String(300))
    hindi_keywords: Mapped[str | None] = mapped_column(String(300))
    languages: Mapped[list[str]] = mapped_column(JSON, default=lambda: ["en", "hi"])
    time_range_hours: Mapped[int] = mapped_column(Integer, default=24)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)

    runs: Mapped[list["MonitoringRun"]] = relationship(back_populates="monitor", cascade="all, delete-orphan")


class MonitoringRun(Base):
    __tablename__ = "monitoring_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    monitor_id: Mapped[int] = mapped_column(ForeignKey("monitors.id", ondelete="CASCADE"), index=True)
    status: Mapped[str] = mapped_column(String(20), default="pending")  # pending|running|completed|failed
    stage: Mapped[str | None] = mapped_column(String(50))
    progress: Mapped[float] = mapped_column(Float, default=0.0)
    message: Mapped[str | None] = mapped_column(Text)
    error: Mapped[str | None] = mapped_column(Text)
    window_start: Mapped[datetime | None] = mapped_column(UTCDateTime)
    window_end: Mapped[datetime | None] = mapped_column(UTCDateTime)
    stats: Mapped[dict] = mapped_column(JSON, default=dict)
    started_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    finished_at: Mapped[datetime | None] = mapped_column(UTCDateTime)

    monitor: Mapped[Monitor] = relationship(back_populates="runs")


class Source(Base):
    __tablename__ = "sources"

    id: Mapped[int] = mapped_column(primary_key=True)
    domain: Mapped[str] = mapped_column(String(255), unique=True)
    country: Mapped[str | None] = mapped_column(String(100))


class Article(Base):
    __tablename__ = "articles"
    __table_args__ = (UniqueConstraint("run_id", "normalized_url"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("monitoring_runs.id", ondelete="CASCADE"), index=True)
    source_id: Mapped[int | None] = mapped_column(ForeignKey("sources.id"))
    url: Mapped[str] = mapped_column(Text)
    normalized_url: Mapped[str] = mapped_column(Text)
    title: Mapped[str] = mapped_column(Text)
    body: Mapped[str | None] = mapped_column(Text)
    body_status: Mapped[str] = mapped_column(String(20), default="pending")  # pending|ok|failed|skipped
    language: Mapped[str | None] = mapped_column(String(8))
    gdelt_language: Mapped[str | None] = mapped_column(String(40))
    published_at: Mapped[datetime | None] = mapped_column(UTCDateTime, index=True)
    fetched_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    duplicate_of: Mapped[int | None] = mapped_column(ForeignKey("articles.id"))
    dedup_reason: Mapped[str | None] = mapped_column(String(20))  # url|headline|near_dup
    relevance: Mapped[float | None] = mapped_column(Float)  # cosine similarity to the monitor topic

    source: Mapped[Source | None] = relationship()
    embedding: Mapped["ArticleEmbedding | None"] = relationship(back_populates="article", cascade="all, delete-orphan")
    sentiment: Mapped["SentimentScore | None"] = relationship(back_populates="article", cascade="all, delete-orphan")
    entities: Mapped[list["ArticleEntity"]] = relationship(back_populates="article", cascade="all, delete-orphan")


class ArticleEmbedding(Base):
    __tablename__ = "embeddings"

    article_id: Mapped[int] = mapped_column(ForeignKey("articles.id", ondelete="CASCADE"), primary_key=True)
    model: Mapped[str] = mapped_column(String(100))
    vector: Mapped[object] = mapped_column(Embedding(EMBEDDING_DIM))

    article: Mapped[Article] = relationship(back_populates="embedding")


class SentimentScore(Base):
    __tablename__ = "sentiment_scores"

    article_id: Mapped[int] = mapped_column(ForeignKey("articles.id", ondelete="CASCADE"), primary_key=True)
    model: Mapped[str] = mapped_column(String(100))
    label: Mapped[str] = mapped_column(String(10))  # positive|neutral|negative
    positive: Mapped[float] = mapped_column(Float)
    neutral: Mapped[float] = mapped_column(Float)
    negative: Mapped[float] = mapped_column(Float)

    article: Mapped[Article] = relationship(back_populates="sentiment")


class Entity(Base):
    __tablename__ = "entities"
    __table_args__ = (UniqueConstraint("canonical_name", "type"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    canonical_name: Mapped[str] = mapped_column(String(255))
    type: Mapped[str] = mapped_column(String(30))  # PERSON|ORG|PARTY|GOV|LOC|COUNTRY|EVENT|POLICY


class ArticleEntity(Base):
    __tablename__ = "article_entities"

    article_id: Mapped[int] = mapped_column(ForeignKey("articles.id", ondelete="CASCADE"), primary_key=True)
    entity_id: Mapped[int] = mapped_column(ForeignKey("entities.id", ondelete="CASCADE"), primary_key=True)
    surface_form: Mapped[str] = mapped_column(String(255))
    count: Mapped[int] = mapped_column(Integer, default=1)

    article: Mapped[Article] = relationship(back_populates="entities")
    entity: Mapped[Entity] = relationship()


class Narrative(Base):
    __tablename__ = "narratives"

    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("monitoring_runs.id", ondelete="CASCADE"), index=True)
    cluster_label: Mapped[int] = mapped_column(Integer)
    label: Mapped[str] = mapped_column(Text)
    label_source: Mapped[str] = mapped_column(String(20), default="keywords")  # llm|keywords
    summary: Mapped[str | None] = mapped_column(Text)
    keywords: Mapped[list[str]] = mapped_column(JSON, default=list)
    centroid: Mapped[object | None] = mapped_column(Embedding(EMBEDDING_DIM))
    stats: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)

    articles: Mapped[list["ArticleNarrative"]] = relationship(back_populates="narrative", cascade="all, delete-orphan")


class ArticleNarrative(Base):
    __tablename__ = "article_narratives"

    article_id: Mapped[int] = mapped_column(ForeignKey("articles.id", ondelete="CASCADE"), primary_key=True)
    narrative_id: Mapped[int] = mapped_column(ForeignKey("narratives.id", ondelete="CASCADE"), primary_key=True)
    similarity: Mapped[float] = mapped_column(Float)
    is_representative: Mapped[bool] = mapped_column(Boolean, default=False)
    evidence_text: Mapped[str | None] = mapped_column(Text)

    article: Mapped[Article] = relationship()
    narrative: Mapped[Narrative] = relationship(back_populates="articles")


class Brief(Base):
    __tablename__ = "briefs"

    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("monitoring_runs.id", ondelete="CASCADE"), index=True)
    model: Mapped[str] = mapped_column(String(100))
    status: Mapped[str] = mapped_column(String(20), default="pending")  # pending|running|completed|failed
    error: Mapped[str | None] = mapped_column(Text)
    content: Mapped[dict | None] = mapped_column(JSON)
    markdown: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


class LLMCache(Base):
    __tablename__ = "llm_cache"

    prompt_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    model: Mapped[str] = mapped_column(String(100))
    response: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
