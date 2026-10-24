"""Stage 1: collect coverage from the RSS feeds, fetch bodies, clean, deduplicate (URL/headline), detect language."""

from collections import Counter

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.config import get_settings
from backend.models import Article, Monitor, MonitoringRun, Source
from backend.services.progress import InsufficientCoverage, Reporter
from pipeline.cleaning.dedup import dedup_urls, headline_duplicates
from pipeline.cleaning.text import clean_body, clean_text, is_malformed
from pipeline.cleaning.urls import normalize_url
from pipeline.ingestion.bodies import fetch_bodies
from pipeline.ingestion.rss import collect_rss, load_feeds
from pipeline.ingestion.topic import build_matcher
from pipeline.ingestion.types import RawArticle
from pipeline.language.detect import resolve_language

MIN_SUMMARY_CHARS = 80


def collect_sources(monitor: Monitor, run: MonitoringRun, report: Reporter) -> tuple[list[RawArticle], dict]:
    report("collect", 0.0, "Reading publisher news feeds")
    items, rss_stats = collect_rss(
        load_feeds(monitor.languages),
        build_matcher(monitor.topic, monitor.hindi_keywords),
        run.window_start,
        run.window_end,
        cache_dir=get_settings().data_dir / "cache" / "rss",
        on_progress=lambda i, n: report("collect", 0.3 * i / n, f"Read {i}/{n} feeds"),
    )
    return items, {"rss": rss_stats}


def ingest(session: Session, run: MonitoringRun, monitor: Monitor, report: Reporter) -> None:
    settings = get_settings()
    cache = settings.data_dir / "cache"
    stats: Counter = Counter()

    raw, source_stats = collect_sources(monitor, run, report)
    stats["collected"] = len(raw)
    if not raw:
        raise InsufficientCoverage("No headlines in the news feeds matched this topic in the selected time window")
    articles, stats["url_duplicates"] = dedup_urls(raw)

    report("fetch_bodies", 0.3, f"Fetching {len(articles)} article pages")
    fetch_bodies(
        articles,
        cache_dir=cache / "bodies",
        on_progress=lambda i, n: report("fetch_bodies", 0.3 + 0.5 * i / n, f"Fetched {i}/{n} pages"),
    )

    report("clean", 0.8, "Cleaning and detecting language")
    kept: list[tuple[RawArticle, str]] = []
    for a in articles:
        a.title = clean_text(a.title)
        a.body = clean_body(a.body) or None
        if a.body and is_malformed(a.body, min_letters=100):
            a.body, a.body_status = None, "failed"
        if a.body is None and a.summary and len(a.summary) >= MIN_SUMMARY_CHARS:
            # page unreachable (paywall, bot block): the feed's summary is better than nothing
            a.body, a.body_status = a.summary, "summary"
        if is_malformed(a.title):
            stats["malformed"] += 1
            continue
        lang = resolve_language(a.title, a.body, a.language_hint)
        if lang not in monitor.languages:
            stats["other_language"] += 1
            continue
        kept.append((a, lang))

    report("store", 0.9, f"Storing {len(kept)} articles")
    dup_of = headline_duplicates([a for a, _ in kept])
    rows = [_to_row(session, run, a, lang) for a, lang in kept]
    session.add_all(rows)
    session.flush()
    for row, canonical in zip(rows, dup_of):
        if canonical is not None:
            row.duplicate_of = rows[canonical].id
            row.dedup_reason = "headline"
            stats["headline_duplicates"] += 1

    stats["stored"] = len(rows)
    stats["bodies_ok"] = sum(r.body_status == "ok" for r in rows)
    stats["unique_sources"] = len({r.source_id for r in rows if r.duplicate_of is None and r.source_id})
    by_language = Counter(r.language for r in rows if r.duplicate_of is None)
    run.stats = {
        **(run.stats or {}),
        **dict(stats),
        "by_language": dict(by_language),
        "by_origin": dict(Counter(r.origin for r in rows if r.duplicate_of is None)),
        "sources": source_stats,
    }
    session.commit()


def _to_row(session: Session, run: MonitoringRun, a: RawArticle, lang: str) -> Article:
    return Article(
        run_id=run.id,
        source=_get_source(session, a.domain, a.source_country),
        url=a.url,
        normalized_url=normalize_url(a.url),
        title=a.title,
        body=a.body,
        body_status=a.body_status,
        language=lang,
        declared_language=a.language_hint,
        origin=a.origin,
        published_at=a.seen_at,
    )


def _get_source(session: Session, domain: str, country: str | None) -> Source | None:
    if not domain:
        return None
    domain = domain.lower().removeprefix("www.")
    source = session.scalar(select(Source).where(Source.domain == domain))
    if source is None:
        source = Source(domain=domain, country=country)
        session.add(source)
        session.flush()
    return source
