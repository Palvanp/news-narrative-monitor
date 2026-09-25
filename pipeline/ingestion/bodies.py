"""Fetch article pages and extract main text with trafilatura.

GDELT only returns metadata, so bodies are fetched from the publisher. Failures
are expected (paywalls, bot blocks, timeouts); those articles keep title-only text.
Extracted text is cached per URL so re-runs don't refetch.
"""

import asyncio
import hashlib
import logging
from collections.abc import Callable
from pathlib import Path

import httpx
import trafilatura

from pipeline.ingestion.gdelt import RawArticle

log = logging.getLogger(__name__)

USER_AGENT = "Mozilla/5.0 (compatible; nazar-research-prototype)"
MIN_BODY_CHARS = 200


def _cache_file(cache_dir: Path | None, url: str) -> Path | None:
    if not cache_dir:
        return None
    return cache_dir / f"{hashlib.sha1(url.encode()).hexdigest()}.txt"


def extract_text(html: str) -> str | None:
    text = trafilatura.extract(html, include_comments=False, include_tables=False, favor_precision=True)
    if text and len(text) >= MIN_BODY_CHARS:
        return text
    return None


async def _fetch_one(client: httpx.AsyncClient, sem: asyncio.Semaphore, article: RawArticle, cache_dir: Path | None) -> None:
    cache = _cache_file(cache_dir, article.url)
    if cache and cache.exists():
        text = cache.read_text(encoding="utf-8")
        article.body, article.body_status = (text or None), ("ok" if text else "failed")
        return

    async with sem:
        try:
            resp = await client.get(article.url)
            resp.raise_for_status()
            text = await asyncio.to_thread(extract_text, resp.text)
        except Exception as exc:  # network errors, 4xx/5xx, bad encodings
            log.debug("body fetch failed for %s: %s", article.url, exc)
            text = None

    article.body = text
    article.body_status = "ok" if text else "failed"
    if cache:
        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.write_text(text or "", encoding="utf-8")


async def fetch_bodies_async(
    articles: list[RawArticle],
    cache_dir: Path | None = None,
    concurrency: int = 10,
    timeout: float = 10.0,
    on_progress: Callable[[int, int], None] | None = None,
) -> None:
    sem = asyncio.Semaphore(concurrency)
    async with httpx.AsyncClient(timeout=timeout, follow_redirects=True, headers={"User-Agent": USER_AGENT}) as client:
        tasks = [asyncio.create_task(_fetch_one(client, sem, a, cache_dir)) for a in articles]
        for done, task in enumerate(asyncio.as_completed(tasks), 1):
            await task
            if on_progress and (done % 20 == 0 or done == len(tasks)):
                on_progress(done, len(tasks))


def fetch_bodies(articles: list[RawArticle], **kwargs) -> None:
    asyncio.run(fetch_bodies_async(articles, **kwargs))
