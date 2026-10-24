from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from backend.db import get_session
from backend.models import Article, ArticleNarrative, Brief, Monitor, MonitoringRun, Narrative
from backend.schemas import (
    BriefOut,
    EvidenceItem,
    MonitorCreate,
    MonitorOut,
    NarrativeCard,
    NarrativeDetail,
    RelatedNarrative,
    RunOut,
    Timeline,
    TimelineSeries,
    Trending,
)
from backend.services import queries
from backend.services.runs import create_run

router = APIRouter()


def _start_run(run_id: int) -> None:
    # Imported lazily: the runner pulls in the ML stack, which the API doesn't need at startup.
    from backend.services.runner import execute_run

    execute_run(run_id)


def _start_brief(brief_id: int) -> None:
    from backend.services.briefs import execute_brief

    execute_brief(brief_id)


def _new_run(session: Session, monitor: Monitor, background: BackgroundTasks) -> MonitoringRun:
    run = create_run(session, monitor)
    background.add_task(_start_run, run.id)
    return run


def _monitor_out(session: Session, monitor: Monitor) -> MonitorOut:
    out = MonitorOut.model_validate(monitor)
    run = queries.latest_run(session, monitor.id)
    out.latest_run = RunOut.model_validate(run) if run else None
    return out


def _get(session: Session, model, id_: int):
    obj = session.get(model, id_)
    if obj is None:
        raise HTTPException(404, f"{model.__name__} {id_} not found")
    return obj


def _completed_run(session: Session, monitor_id: int) -> MonitoringRun:
    run = queries.latest_run(session, monitor_id, completed_only=True)
    if run is None:
        raise HTTPException(409, "This monitor has no completed run yet")
    return run


@router.post("/monitors", response_model=MonitorOut, status_code=201)
def create_monitor(body: MonitorCreate, background: BackgroundTasks, session: Session = Depends(get_session)):
    monitor = Monitor(**body.model_dump())
    session.add(monitor)
    session.commit()
    _new_run(session, monitor, background)
    return _monitor_out(session, monitor)


@router.get("/monitors", response_model=list[MonitorOut])
def list_monitors(session: Session = Depends(get_session)):
    monitors = session.scalars(select(Monitor).order_by(Monitor.id.desc()))
    return [_monitor_out(session, m) for m in monitors]


@router.get("/monitors/{monitor_id}", response_model=MonitorOut)
def get_monitor(monitor_id: int, session: Session = Depends(get_session)):
    return _monitor_out(session, _get(session, Monitor, monitor_id))


@router.post("/monitors/{monitor_id}/run", response_model=RunOut, status_code=202)
def rerun_monitor(monitor_id: int, background: BackgroundTasks, session: Session = Depends(get_session)):
    monitor = _get(session, Monitor, monitor_id)
    active = queries.latest_run(session, monitor_id)
    if active and active.status in ("pending", "running"):
        raise HTTPException(409, f"Run {active.id} is still {active.status}")
    return _new_run(session, monitor, background)


@router.get("/trending", response_model=Trending)
def trending():
    """Topics with enough current coverage in English and Hindi to form narratives."""
    from backend.services.trending import get_trending

    return get_trending()


@router.get("/runs/{run_id}", response_model=RunOut)
def get_run(run_id: int, session: Session = Depends(get_session)):
    return _get(session, MonitoringRun, run_id)


@router.get("/monitors/{monitor_id}/narratives", response_model=list[NarrativeCard])
def monitor_narratives(monitor_id: int, session: Session = Depends(get_session)):
    _get(session, Monitor, monitor_id)
    run = _completed_run(session, monitor_id)
    return [queries.narrative_card(n) for n in queries.run_narratives(session, run.id)]


@router.get("/monitors/{monitor_id}/timeline", response_model=Timeline)
def monitor_timeline(monitor_id: int, session: Session = Depends(get_session)):
    _get(session, Monitor, monitor_id)
    run = _completed_run(session, monitor_id)
    narratives = queries.run_narratives(session, run.id)
    edges = narratives[0].stats["timeline"]["edges"] if narratives else []
    series = [
        TimelineSeries(narrative_id=n.id, label=n.label, counts=n.stats["timeline"]["counts"]) for n in narratives
    ]
    return Timeline(run_id=run.id, edges=edges, series=series)


@router.get("/narratives/{narrative_id}", response_model=NarrativeDetail)
def get_narrative(narrative_id: int, session: Session = Depends(get_session)):
    narrative = _get(session, Narrative, narrative_id)
    run = session.get(MonitoringRun, narrative.run_id)
    card = queries.narrative_card(narrative)
    return NarrativeDetail(**card.model_dump(), monitor_id=run.monitor_id, topic=run.monitor.topic, stats=narrative.stats)


@router.get("/narratives/{narrative_id}/evidence", response_model=list[EvidenceItem])
def narrative_evidence(narrative_id: int, limit: int = 50, session: Session = Depends(get_session)):
    _get(session, Narrative, narrative_id)
    links = list(
        session.scalars(
            select(ArticleNarrative)
            .where(ArticleNarrative.narrative_id == narrative_id)
            .options(
                selectinload(ArticleNarrative.article).selectinload(Article.source),
                selectinload(ArticleNarrative.article).selectinload(Article.sentiment),
            )
        )
    )
    links.sort(key=lambda an: (not an.is_representative, -an.similarity))
    links = links[:limit]
    copies = queries.syndication_counts(session, [an.article_id for an in links])
    return [
        EvidenceItem(
            article_id=an.article.id,
            title=an.article.title,
            url=an.article.url,
            source=an.article.source.domain if an.article.source else None,
            language=an.article.language,
            published_at=an.article.published_at,
            sentiment=an.article.sentiment.label if an.article.sentiment else None,
            similarity=round(an.similarity, 3),
            is_representative=an.is_representative,
            evidence_text=an.evidence_text,
            syndicated_copies=copies.get(an.article_id, 0),
        )
        for an in links
    ]


@router.get("/narratives/{narrative_id}/related", response_model=list[RelatedNarrative])
def narrative_related(narrative_id: int, session: Session = Depends(get_session)):
    narrative = _get(session, Narrative, narrative_id)
    return [
        RelatedNarrative(id=n.id, label=n.label, similarity=round(sim, 3))
        for n, sim in queries.related_narratives(session, narrative)
    ]


@router.post("/monitors/{monitor_id}/brief", response_model=BriefOut, status_code=202)
def create_brief(monitor_id: int, background: BackgroundTasks, session: Session = Depends(get_session)):
    from backend.services.briefs import create_brief as new_brief

    _get(session, Monitor, monitor_id)
    brief = new_brief(session, _completed_run(session, monitor_id))
    background.add_task(_start_brief, brief.id)
    return brief


@router.get("/monitors/{monitor_id}/brief", response_model=BriefOut)
def latest_brief(monitor_id: int, session: Session = Depends(get_session)):
    _get(session, Monitor, monitor_id)
    brief = session.scalar(
        select(Brief)
        .join(MonitoringRun, Brief.run_id == MonitoringRun.id)
        .where(MonitoringRun.monitor_id == monitor_id)
        .order_by(Brief.id.desc())
        .limit(1)
    )
    if brief is None:
        raise HTTPException(404, "No brief generated for this monitor yet")
    return brief


@router.get("/briefs/{brief_id}", response_model=BriefOut)
def get_brief(brief_id: int, session: Session = Depends(get_session)):
    return _get(session, Brief, brief_id)
