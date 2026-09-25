"""Stage 1: collect from GDELT, fetch bodies, clean, deduplicate (URL/headline), detect language."""

from collections import Counter

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.config import get_settings
from backend.models import Article, Monitor, MonitoringRun, Source
from backend.services.progress import Reporter
from pipeline.cleaning.dedup import dedup_urls, headline_duplicates
from pipeline.cleaning.text import clean_body, clean_text, is_malformed
from pipeline.cleaning.urls import normalize_url
from pipeline.ingestion.bodies import fetch_bodies
from pipeline.ingestion.gdelt import GdeltClient, RawArticle, collect
from pipeline.language.detect import resolve_language


def ingest(session: Session, run: MonitoringRun, monitor: Monitor, report: Reporter) -> None:
    settings = get_settings()
    cache = settings.data_dir / "cache"
    stats: Counter = Counter()

    report("collect", 0.0, "Querying GDELT")
    raw = collect(
        GdeltClient(cache_dir=cache / "gdelt"),
        topic=monitor.topic,
        languages=monitor.languages,
        end=run.window_end,
        hours=monitor.time_range_hours,
        hindi_keywords=monitor.hindi_keywords,
        on_progress=lambda i, n, r: report("collect", 0.3 * (i - 1) / n, f"GDELT query {i}/{n} ({r} requests)"),
    )
    stats["collected"] = len(raw)
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
        if is_malformed(a.title):
            stats["malformed"] += 1
            continue
        lang = resolve_language(a.title, a.body, a.gdelt_language)
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
    by_language = Counter(r.language for r in rows if r.duplicate_of is None)
    run.stats = {**(run.stats or {}), **dict(stats), "by_language": dict(by_language)}
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
        gdelt_language=a.gdelt_language,
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
