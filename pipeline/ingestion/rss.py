"""Collect topic coverage from publisher RSS feeds.

Each feed lists an outlet's latest items (roughly the last 1-3 days). All feeds
are read, items outside the monitoring window are dropped, and the rest are
kept only if their headline or summary matches the topic in either language.
A copy of each downloaded feed is saved so a run can be inspected later.
"""

import asyncio
import calendar
import hashlib
import logging
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

import feedparser
import httpx
import yaml

from pipeline.cleaning.text import clean_text
from pipeline.ingestion.topic import TopicMatcher
from pipeline.ingestion.types import RawArticle

log = logging.getLogger(__name__)

FEEDS_PATH = Path(__file__).with_name("feeds.yaml")
# Several outlets refuse requests without a browser-like User-Agent.
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0 Safari/537.36"


@dataclass(frozen=True)
class Feed:
    outlet: str
    section: str
    url: str
    language: str


def load_feeds(languages: list[str], path: Path = FEEDS_PATH) -> list[Feed]:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    return [Feed(f["outlet"], f["section"], f["url"], lang) for lang in languages for f in data.get(lang, [])]


def _entry_time(entry) -> datetime | None:
    parsed = entry.get("published_parsed") or entry.get("updated_parsed")
    return datetime.fromtimestamp(calendar.timegm(parsed), tz=timezone.utc) if parsed else None


def parse_feed(content: bytes, feed: Feed) -> list[RawArticle]:
    items = []
    for entry in feedparser.parse(content).entries:
        title = clean_text(entry.get("title"))
        link = entry.get("link")
        published = _entry_time(entry)
        if not title or not link or published is None:
            continue
        items.append(
            RawArticle(
                url=link,
                title=title,
                domain=(urlsplit(link).hostname or "").removeprefix("www."),
                seen_at=published,
                origin="rss",
                language_hint=feed.language,
                source_country="India",
                summary=clean_text(entry.get("summary")) or None,
                extra={"outlet": feed.outlet, "section": feed.section},
            )
        )
    return items


async def _fetch(client: httpx.AsyncClient, feed: Feed, cache_dir: Path | None) -> bytes | None:
    try:
        resp = await client.get(feed.url)
        resp.raise_for_status()
    except httpx.HTTPError as exc:
        log.warning("feed failed: %s (%s): %s", feed.outlet, feed.section, exc)
        return None
    if cache_dir:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M")
        name = hashlib.sha1(feed.url.encode()).hexdigest()[:12]
        path = cache_dir / stamp / f"{feed.language}-{name}.xml"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(resp.content)
    return resp.content


async def _fetch_all(feeds: list[Feed], cache_dir: Path | None, on_progress: Callable[[int, int], None] | None):
    async with httpx.AsyncClient(timeout=20, follow_redirects=True, headers={"User-Agent": USER_AGENT}) as client:
        tasks = [asyncio.create_task(_fetch(client, f, cache_dir)) for f in feeds]
        for done, _ in enumerate(asyncio.as_completed(tasks), 1):
            await _
            if on_progress:
                on_progress(done, len(tasks))
        return [t.result() for t in tasks]


def collect_rss(
    feeds: list[Feed],
    matcher: TopicMatcher,
    start: datetime,
    end: datetime,
    cache_dir: Path | None = None,
    on_progress: Callable[[int, int], None] | None = None,
) -> tuple[list[RawArticle], dict]:
    contents = asyncio.run(_fetch_all(feeds, cache_dir, on_progress))
    stats: Counter = Counter()
    kept: list[RawArticle] = []
    for feed, content in zip(feeds, contents):
        if content is None:
            stats["feeds_failed"] += 1
            continue
        stats["feeds_ok"] += 1
        for item in parse_feed(content, feed):
            stats["headlines"] += 1
            if not start <= item.seen_at <= end:
                continue
            stats["in_window"] += 1
            if matcher.matches(f"{item.title} {item.summary or ''}"):
                kept.append(item)
    stats["matched"] = len(kept)
    return kept, dict(stats)
