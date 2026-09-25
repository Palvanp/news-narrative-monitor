"""Stage 3: cluster articles into narratives, then compute keywords, observed
metrics and evidence for each narrative."""

from collections import Counter

import numpy as np
from sqlalchemy import delete, select
from sqlalchemy.orm import Session, selectinload

from backend.config import get_settings
from backend.models import Article, ArticleEntity, ArticleNarrative, Monitor, MonitoringRun, Narrative
from backend.services.progress import InsufficientCoverage, Reporter
from pipeline.clustering.cluster import (
    MIN_NARRATIVE_ARTICLES,
    centroid,
    cluster_embeddings,
    cohesion,
    drop_incoherent,
    remove_language_offsets,
)
from pipeline.clustering.keywords import ctfidf_keywords
from pipeline import models
from pipeline.evidence.select import best_sentence, representatives, split_sentences
from pipeline.temporal.stats import Item, narrative_stats

REPRESENTATIVES_PER_NARRATIVE = 8
TOP_ENTITIES = 8


def active_articles(session: Session, run_id: int) -> list[Article]:
    """Canonical (non-duplicate), embedded articles of a run."""
    return list(
        session.scalars(
            select(Article)
            .where(Article.run_id == run_id, Article.duplicate_of.is_(None))
            .options(
                selectinload(Article.embedding),
                selectinload(Article.sentiment),
                selectinload(Article.source),
                selectinload(Article.entities).selectinload(ArticleEntity.entity),
            )
            .order_by(Article.published_at, Article.id)
        )
    )


def top_entities(articles: list[Article], k: int = TOP_ENTITIES) -> list[dict]:
    """Entities ranked by how many of the articles mention them."""
    counts: Counter = Counter()
    info = {}
    for a in articles:
        for ae in a.entities:
            counts[ae.entity_id] += 1
            info[ae.entity_id] = ae.entity
    return [
        {"id": eid, "name": info[eid].canonical_name, "type": info[eid].type, "articles": n}
        for eid, n in counts.most_common(k)
    ]


def analyze(session: Session, run: MonitoringRun, monitor: Monitor, report: Reporter) -> None:
    settings = get_settings()
    session.execute(delete(Narrative).where(Narrative.run_id == run.id))  # idempotent re-analysis

    articles = [a for a in active_articles(session, run.id) if a.embedding is not None]
    relevant = [a for a in articles if a.relevance is None or a.relevance >= settings.relevance_min]
    run.stats = {**(run.stats or {}), "relevant": len(relevant), "below_relevance": len(articles) - len(relevant)}
    if len(relevant) < MIN_NARRATIVE_ARTICLES:
        raise InsufficientCoverage(
            f"Only {len(relevant)} of {len(articles)} matching articles were relevant enough to the topic"
        )

    report("cluster", 0.0, f"Clustering {len(relevant)} articles")
    raw = np.stack([a.embedding.vector for a in relevant])
    # clustering, similarity and representatives use language-centered vectors so
    # English and Hindi reports of one story group together (see cluster.py)
    vectors = remove_language_offsets(raw, [a.language for a in relevant])
    labels, _ = cluster_embeddings(vectors)
    labels = drop_incoherent(raw, labels)
    texts = [f"{a.title} {(a.body or '')[:1000]}" for a in relevant]
    keywords = ctfidf_keywords(texts, labels.tolist())

    clusters = sorted({int(lbl) for lbl in labels if lbl >= 0}, key=lambda c: -int((labels == c).sum()))
    run.stats = {**run.stats, "unclustered": int((labels < 0).sum()), "narratives": len(clusters)}
    if not clusters:
        raise InsufficientCoverage(
            f"{len(relevant)} relevant articles were found, but they don't share a common storyline "
            "(no group of related articles was tight enough to be a narrative)"
        )
    report("evidence", 0.3, f"Found {len(clusters)} narratives; selecting evidence")

    encoder = models.encoder()
    for n, c in enumerate(clusters):
        idx = np.flatnonzero(labels == c)
        members = [relevant[i] for i in idx]
        member_vecs = vectors[idx]
        center = centroid(member_vecs)
        # sentence embeddings aren't centered; within one article every sentence
        # shares its language, so ranking them against the raw centroid is fair
        raw_center = centroid(raw[idx])
        sims = member_vecs @ center

        stats = narrative_stats(
            [
                Item(
                    a.published_at,
                    a.language,
                    a.source.domain if a.source else None,
                    a.sentiment.label if a.sentiment else None,
                )
                for a in members
            ],
            run.window_start,
            run.window_end,
        )
        stats["top_entities"] = top_entities(members)
        stats["mean_similarity"] = round(float(sims.mean()), 3)
        stats["cohesion"] = round(cohesion(raw[idx]), 3)

        reps = set(
            representatives(
                member_vecs,
                center,
                [a.source.domain if a.source else None for a in members],
                k=REPRESENTATIVES_PER_NARRATIVE,
            )
        )
        evidence: dict[int, str | None] = {}
        for i in reps:
            sentences = split_sentences(members[i].body or "", members[i].title)
            if sentences:
                evidence[i] = best_sentence(sentences, encoder.encode(sentences), raw_center)

        kw = keywords.get(c, [])
        narrative = Narrative(
            run_id=run.id,
            cluster_label=c,
            # until the LLM names it: the headline closest to the narrative's centre
            label=members[int(np.argmax(sims))].title[:160],
            label_source="headline",
            keywords=kw,
            centroid=center,
            stats=stats,
        )
        narrative.articles = [
            ArticleNarrative(
                article_id=a.id,
                similarity=float(sims[i]),
                is_representative=i in reps,
                evidence_text=evidence.get(i),
            )
            for i, a in enumerate(members)
        ]
        session.add(narrative)
        report("evidence", 0.3 + 0.7 * (n + 1) / len(clusters), f"Narrative {n + 1}/{len(clusters)}")

    session.commit()
