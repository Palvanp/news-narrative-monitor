"""Brief generation for a completed run (runs in the background; the UI polls)."""

import logging
import traceback

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload, sessionmaker

from backend.config import get_settings
from backend.db import SessionLocal
from backend.models import Article, ArticleNarrative, Brief, MonitoringRun, Narrative
from backend.services.naming import llm_client
from pipeline.generation.brief import EVIDENCE_PER_NARRATIVE, MAX_NARRATIVES, Evidence, NarrativeContext, generate

log = logging.getLogger(__name__)


def window_label(run: MonitoringRun) -> str:
    fmt = "%Y-%m-%d %H:%M"
    return f"{run.window_start.strftime(fmt)} to {run.window_end.strftime(fmt)} UTC"


def narrative_contexts(session: Session, run_id: int) -> list[NarrativeContext]:
    narratives = list(
        session.scalars(
            select(Narrative)
            .where(Narrative.run_id == run_id)
            .options(
                selectinload(Narrative.articles).selectinload(ArticleNarrative.article).selectinload(Article.source)
            )
        )
    )
    narratives.sort(key=lambda n: -n.stats.get("volume", 0))
    contexts, counter = [], 0
    for n in narratives[:MAX_NARRATIVES]:
        reps = sorted((an for an in n.articles if an.is_representative), key=lambda an: -an.similarity)
        evidence = []
        for an in reps[:EVIDENCE_PER_NARRATIVE]:
            counter += 1
            a = an.article
            evidence.append(
                Evidence(
                    id=f"E{counter}",
                    article_id=a.id,
                    narrative_id=n.id,
                    title=a.title,
                    source=a.source.domain if a.source else None,
                    language=a.language,
                    published_at=a.published_at.isoformat(),
                    url=a.url,
                    excerpt=an.evidence_text,
                )
            )
        contexts.append(NarrativeContext(n.id, n.label, n.summary, n.stats, evidence))
    return contexts


def create_brief(session: Session, run: MonitoringRun) -> Brief:
    brief = Brief(run_id=run.id, model=get_settings().llm_brief_model, status="pending")
    session.add(brief)
    session.commit()
    return brief


def execute_brief(brief_id: int, session_factory: sessionmaker = SessionLocal) -> None:
    with session_factory() as session:
        brief = session.get(Brief, brief_id)
        brief.status = "running"
        session.commit()
        try:
            run = session.get(MonitoringRun, brief.run_id)
            contexts = narrative_contexts(session, run.id)
            if not contexts:
                raise RuntimeError("This run has no narratives to brief")
            client = llm_client(session)
            if not client.available():
                raise RuntimeError(client.unavailable_hint)
            result = generate(client, brief.model, run.monitor.topic, window_label(run), contexts)
            brief.content = {"assessment": result["assessment"], "evidence": result["evidence"], "window": window_label(run)}
            brief.markdown = result["markdown"]
            brief.status = "completed"
        except Exception as exc:
            log.exception("brief %s failed", brief_id)
            session.rollback()
            brief.status = "failed"
            brief.error = "".join(traceback.format_exception_only(exc)).strip()
        session.commit()
