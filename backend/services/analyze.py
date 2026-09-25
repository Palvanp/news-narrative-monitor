"""Stage 3: cluster articles into narratives, then compute keywords, observed
metrics and evidence for each narrative."""

from collections import Counter

import numpy as np
from sqlalchemy import delete, select
from sqlalchemy.orm import Session, selectinload

from backend.config import get_settings
from backend.models import Article, ArticleEntity, ArticleNarrative, Monitor, MonitoringRun, Narrative
from backend.services.progress import Reporter
from pipeline.clustering.cluster import centroid, cluster_embeddings
from pipeline.clustering.keywords import ctfidf_keywords
from pipeline.embeddings.encoder import Encoder
from pipeline.evidence.select import best_sentence, representatives, split_sentences
from pipeline.narratives.naming import keyword_label
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
    if len(relevant) < 3:
        raise RuntimeError(f"Only {len(relevant)} relevant articles; too few to find narratives")

    report("cluster", 0.0, f"Clustering {len(relevant)} articles")
    vectors = np.stack([a.embedding.vector for a in relevant])
    labels, _ = cluster_embeddings(vectors)
    texts = [f"{a.title} {(a.body or '')[:1000]}" for a in relevant]
    keywords = ctfidf_keywords(texts, labels.tolist())

    clusters = sorted({int(lbl) for lbl in labels if lbl >= 0}, key=lambda c: -int((labels == c).sum()))
    report("evidence", 0.3, f"Found {len(clusters)} narratives; selecting evidence")

    encoder = Encoder(settings.embedding_model)
    try:
        for n, c in enumerate(clusters):
            idx = np.flatnonzero(labels == c)
            members = [relevant[i] for i in idx]
            member_vecs = vectors[idx]
            center = centroid(member_vecs)
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
                sentences = split_sentences(members[i].body or "")
                if sentences:
                    evidence[i] = best_sentence(sentences, encoder.encode(sentences), center)

            kw = keywords.get(c, [])
            narrative = Narrative(
                run_id=run.id,
                cluster_label=c,
                label=keyword_label(kw, [e["name"] for e in stats["top_entities"]]),
                label_source="keywords",
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
    finally:
        encoder.close()

    run.stats = {
        **(run.stats or {}),
        "relevant": len(relevant),
        "narratives": len(clusters),
        "unclustered": int((labels < 0).sum()),
    }
    session.commit()
