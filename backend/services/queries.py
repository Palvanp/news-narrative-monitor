"""Read-side helpers shared by the API routes."""

import numpy as np
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.models import Article, MonitoringRun, Narrative
from backend.schemas import EntityOut, NarrativeCard


def latest_run(session: Session, monitor_id: int, completed_only: bool = False) -> MonitoringRun | None:
    query = select(MonitoringRun).where(MonitoringRun.monitor_id == monitor_id)
    if completed_only:
        query = query.where(MonitoringRun.status == "completed")
    return session.scalar(query.order_by(MonitoringRun.id.desc()).limit(1))


def narrative_card(n: Narrative) -> NarrativeCard:
    s = n.stats or {}
    return NarrativeCard(
        id=n.id,
        run_id=n.run_id,
        label=n.label,
        label_source=n.label_source,
        summary=n.summary,
        keywords=n.keywords or [],
        volume=s.get("volume", 0),
        growth_pct=s.get("growth_pct"),
        is_new=bool(s.get("is_new")),
        sentiment=s.get("sentiment", {}),
        languages=s.get("languages", {}),
        unique_sources=s.get("unique_sources", 0),
        spikes=s.get("spikes", []),
        top_entities=[EntityOut(**e) for e in s.get("top_entities", [])],
    )


def run_narratives(session: Session, run_id: int) -> list[Narrative]:
    narratives = list(session.scalars(select(Narrative).where(Narrative.run_id == run_id)))
    return sorted(narratives, key=lambda n: -(n.stats or {}).get("volume", 0))


def related_narratives(session: Session, narrative: Narrative, k: int = 3) -> list[tuple[Narrative, float]]:
    """Other narratives in the same run, by centroid cosine similarity.

    A run has at most a few dozen narratives, so this is computed in numpy on
    every backend rather than with a vector index.
    """
    if narrative.centroid is None:
        return []
    others = [n for n in run_narratives(session, narrative.run_id) if n.id != narrative.id and n.centroid is not None]
    if not others:
        return []
    sims = np.stack([o.centroid for o in others]) @ narrative.centroid
    order = np.argsort(sims)[::-1][:k]
    return [(others[i], float(sims[i])) for i in order]


def syndication_counts(session: Session, article_ids: list[int]) -> dict[int, int]:
    """How many duplicate copies point at each canonical article."""
    if not article_ids:
        return {}
    rows = session.execute(
        select(Article.duplicate_of, func.count())
        .where(Article.duplicate_of.in_(article_ids))
        .group_by(Article.duplicate_of)
    )
    return dict(rows.all())
