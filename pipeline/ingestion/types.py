from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class RawArticle:
    """An article as collected from any source, before cleaning."""

    url: str
    title: str
    domain: str
    seen_at: datetime
    origin: str = "unknown"  # rss
    language_hint: str | None = None  # the source's declared language: a code ("hi") or name ("Hindi")
    source_country: str | None = None
    summary: str | None = None
    body: str | None = None
    body_status: str = "pending"  # pending|ok|summary|failed
    extra: dict = field(default_factory=dict)
