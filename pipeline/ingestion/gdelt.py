"""GDELT DOC 2.0 API client.

GDELT caps each query at 250 articles and rate-limits aggressively (in practice
stricter than its documented one request per 5 seconds). Each language query
starts with the whole monitoring period and is split in half only when it hits
the cap, which keeps the request count low. Raw responses are cached on disk so
runs are reproducible and interrupted runs resume cheaply.
"""

import hashlib
import json
import logging
import re
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx

log = logging.getLogger(__name__)

API_URL = "https://api.gdeltproject.org/api/v2/doc/doc"
MAX_RECORDS = 250
MIN_INTERVAL_S = 10.0
MIN_WINDOW = timedelta(hours=1)
RATE_LIMIT_MARKER = "Please limit requests"

# GDELT's sourcelang: operator takes language names.
GDELT_LANG = {"en": "english", "hi": "hindi"}

STOPWORDS = {"the", "and", "for", "with", "from", "into", "over", "about", "between", "amid", "of", "on", "in"}


@dataclass
class RawArticle:
    url: str
    title: str
    domain: str
    seen_at: datetime
    gdelt_language: str | None = None
    source_country: str | None = None
    query_language: str | None = None
    body: str | None = None
    body_status: str = "pending"
    extra: dict = field(default_factory=dict)


def build_query(topic: str, language: str) -> str:
    """Turn a free-text topic into a GDELT query for one language.

    GDELT rejects keywords shorter than 3 characters, and a leading '-' negates,
    so hyphenated compounds like "India-US" are split and short tokens dropped.
    A topic that already uses GDELT syntax (quotes or OR) is passed through.
    """
    if '"' in topic or " OR " in topic:
        terms = topic.strip()
    else:
        tokens = re.split(r"[\s\-–—/,]+", topic)
        kept = [t for t in tokens if len(t) >= 3 and t.lower() not in STOPWORDS]
        if not kept:
            raise ValueError(f"topic {topic!r} has no searchable keywords (GDELT needs words of 3+ characters)")
        terms = " ".join(kept)

    return f"{terms} sourcelang:{GDELT_LANG[language]}"


def _gdelt_ts(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y%m%d%H%M%S")


def parse_seendate(value: str) -> datetime:
    return datetime.strptime(value, "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc)


def parse_response(text: str, query_language: str | None = None) -> list[RawArticle]:
    """Parse an artlist JSON response. An empty result can come back as '{}' or ''."""
    text = text.strip().lstrip("﻿")
    if not text:
        return []
    data = json.loads(text, strict=False)  # GDELT occasionally emits raw control chars
    articles = []
    for item in data.get("articles", []):
        if not item.get("url") or not item.get("title"):
            continue
        articles.append(
            RawArticle(
                url=item["url"],
                title=item["title"],
                domain=item.get("domain") or "",
                seen_at=parse_seendate(item["seendate"]),
                gdelt_language=item.get("language"),
                source_country=item.get("sourcecountry") or None,
                query_language=query_language,
            )
        )
    return articles


class GdeltClient:
    def __init__(self, cache_dir: Path | None = None, client: httpx.Client | None = None):
        self.cache_dir = cache_dir
        self.client = client or httpx.Client(timeout=60, headers={"User-Agent": "nazar-research-prototype"})
        self._last_request = 0.0

    def _cache_path(self, params: dict) -> Path | None:
        if not self.cache_dir:
            return None
        key = hashlib.sha1(json.dumps(params, sort_keys=True).encode()).hexdigest()
        return self.cache_dir / f"{key}.json"

    def _throttle(self) -> None:
        wait = MIN_INTERVAL_S - (time.monotonic() - self._last_request)
        if wait > 0:
            time.sleep(wait)
        self._last_request = time.monotonic()

    def fetch_window(self, query: str, start: datetime, end: datetime, query_language: str | None = None) -> list[RawArticle]:
        params = {
            "query": query,
            "mode": "artlist",
            "format": "json",
            "maxrecords": MAX_RECORDS,
            "sort": "datedesc",
            "startdatetime": _gdelt_ts(start),
            "enddatetime": _gdelt_ts(end),
        }
        cache = self._cache_path(params)
        # Windows that ended over an hour ago won't change, so their responses are cacheable.
        cacheable = cache is not None and end < datetime.now(timezone.utc) - timedelta(hours=1)
        if cacheable and cache.exists():
            return parse_response(cache.read_text(encoding="utf-8"), query_language)

        text = self._get_with_retry(params)
        if cacheable:
            cache.parent.mkdir(parents=True, exist_ok=True)
            cache.write_text(text, encoding="utf-8")
        return parse_response(text, query_language)

    def _get_with_retry(self, params: dict, attempts: int = 4) -> str:
        backoff = 30.0
        for attempt in range(1, attempts + 1):
            self._throttle()
            try:
                resp = self.client.get(API_URL, params=params)
                resp.raise_for_status()
                text = resp.text
                if RATE_LIMIT_MARKER not in text[:200]:
                    stripped = text.strip()
                    if stripped and not stripped.startswith("{"):
                        raise ValueError(f"GDELT error: {stripped[:200]}")
                    return text
                log.warning("GDELT rate limit hit (attempt %d), backing off %.0fs", attempt, backoff)
            except httpx.HTTPError as exc:
                log.warning("GDELT request failed (attempt %d): %s", attempt, exc)
            if attempt < attempts:
                time.sleep(backoff)
                backoff *= 2
        raise RuntimeError("GDELT request failed after retries")


def fetch_range(
    client: GdeltClient,
    query: str,
    start: datetime,
    end: datetime,
    query_language: str | None = None,
    on_request: Callable[[], None] | None = None,
) -> list[RawArticle]:
    """Fetch [start, end); if the 250 cap is hit, split in half and recurse."""
    batch = client.fetch_window(query, start, end, query_language)
    if on_request:
        on_request()
    if len(batch) < MAX_RECORDS or end - start <= MIN_WINDOW:
        if len(batch) >= MAX_RECORDS:
            log.warning("window %s–%s still hits the %d cap; coverage is truncated", start, end, MAX_RECORDS)
        return batch
    mid = start + (end - start) / 2
    mid = mid.replace(second=0, microsecond=0)
    return fetch_range(client, query, start, mid, query_language, on_request) + fetch_range(
        client, query, mid, end, query_language, on_request
    )


def collect(
    client: GdeltClient,
    topic: str,
    languages: list[str],
    end: datetime,
    hours: int,
    hindi_keywords: str | None = None,
    on_progress: Callable[[int, int, int], None] | None = None,
) -> list[RawArticle]:
    """on_progress(query_index, n_queries, requests_made)."""
    # GDELT matches non-English articles against their English translation, so the
    # English topic finds Hindi coverage too; native Hindi keywords run as an extra
    # query because GDELT's OR operator can't combine multi-word groups.
    queries = [(lang, build_query(topic, lang)) for lang in languages]
    if "hi" in languages and hindi_keywords and hindi_keywords.strip():
        queries.append(("hi", build_query(hindi_keywords, "hi")))

    start = end - timedelta(hours=hours)
    articles: list[RawArticle] = []
    requests = 0
    for i, (lang, query) in enumerate(queries, 1):

        def counted() -> None:
            nonlocal requests
            requests += 1
            if on_progress:
                on_progress(i, len(queries), requests)

        articles.extend(fetch_range(client, query, start, end, lang, counted))
    return articles
