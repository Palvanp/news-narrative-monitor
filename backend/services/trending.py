"""Trending topics for the home page, recomputed at most every 30 minutes.

Reading the ~30 feeds and scoring candidates takes 10-20 s, so the result is
cached in memory and refreshed in a background thread when the API starts.
"""

import logging
import threading
import time
from datetime import datetime, timezone

from pipeline.ingestion.trending import WINDOW_HOURS, trending_topics

log = logging.getLogger(__name__)

TTL_SECONDS = 30 * 60
_lock = threading.Lock()
_cache: dict = {}


def get_trending(force: bool = False) -> dict:
    with _lock:
        if force or not _cache or time.monotonic() - _cache["at"] > TTL_SECONDS:
            started = time.perf_counter()
            try:
                topics = [{"topic": s.topic, "en": s.en, "hi": s.hi, "headlines": s.headlines} for s in trending_topics()]
                error = None
            except Exception as exc:  # feeds down: show no suggestions rather than fail the page
                log.warning("trending topics failed: %s", exc)
                topics, error = [], str(exc)
            _cache.update(
                at=time.monotonic(),
                value={
                    "window_hours": WINDOW_HOURS,
                    "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                    "topics": topics,
                    "error": error,
                },
            )
            log.info("trending topics: %d in %.1fs", len(topics), time.perf_counter() - started)
        return _cache["value"]


def warm_up() -> None:
    threading.Thread(target=get_trending, name="trending-warm-up", daemon=True).start()
