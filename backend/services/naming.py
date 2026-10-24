"""Stage 4: LLM narrative labels. Skipped (keyword labels kept) if the LLM is unreachable."""

import logging

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from backend.config import get_settings
from backend.models import ArticleNarrative, LLMCache, Monitor, MonitoringRun, Narrative
from backend.services.progress import Reporter
from pipeline.llm import GroqClient, LLMClient, LLMError, LLMUnavailable
from pipeline.narratives.naming import Headline, name_narrative

log = logging.getLogger(__name__)


class DbCache:
    def __init__(self, session: Session):
        self.session = session

    def get(self, key: str) -> str | None:
        row = self.session.get(LLMCache, key)
        return row.response if row else None

    def put(self, key: str, model: str, response: str) -> None:
        self.session.merge(LLMCache(prompt_hash=key, model=model, response=response))
        self.session.commit()


def make_client(cache: DbCache | None = None) -> LLMClient:
    settings = get_settings()
    return GroqClient(settings.groq_api_key, settings.groq_url, cache=cache, max_prompt_tokens=settings.groq_max_prompt_tokens)


def llm_client(session: Session) -> LLMClient:
    return make_client(DbCache(session))


def name_narratives(session: Session, run: MonitoringRun, monitor: Monitor, report: Reporter) -> None:
    settings = get_settings()
    narratives = list(
        session.scalars(
            select(Narrative)
            .where(Narrative.run_id == run.id)
            .options(selectinload(Narrative.articles).selectinload(ArticleNarrative.article))
            .order_by(Narrative.id)
        )
    )
    client = llm_client(session)
    if not narratives:
        return
    if not client.available():
        run.stats = {**(run.stats or {}), "llm": "unavailable"}
        report("naming", 1.0, f"{client.unavailable_hint} Kept keyword labels.")
        return

    named = 0
    for n, narrative in enumerate(narratives):
        report("naming", n / len(narratives), f"Naming narrative {n + 1}/{len(narratives)}")
        reps = sorted((an for an in narrative.articles if an.is_representative), key=lambda an: -an.similarity)
        headlines = [
            Headline(
                title=an.article.title,
                language=an.article.language or "?",
                source=an.article.source.domain if an.article.source else None,
                published_at=an.article.published_at.isoformat(),
            )
            for an in reps
        ]
        stats = narrative.stats
        try:
            result = name_narrative(
                client,
                settings.llm_naming_model,
                monitor.topic,
                headlines,
                narrative.keywords,
                [e["name"] for e in stats.get("top_entities", [])],
                stats.get("first_seen") or "",
                stats.get("last_seen") or "",
            )
        except LLMUnavailable:
            log.warning("LLM became unreachable; remaining narratives keep keyword labels")
            break
        except LLMError as exc:
            log.warning("naming failed for narrative %s: %s", narrative.id, exc)
            continue
        narrative.label = result.label.strip()
        narrative.summary = result.summary.strip()
        narrative.label_source = "llm"
        session.commit()
        named += 1

    run.stats = {**(run.stats or {}), "llm": "ok", "llm_named": named}
    session.commit()
    report("naming", 1.0, f"Named {named}/{len(narratives)} narratives")
