"""Runs the Nazar pipeline for a monitoring run and records progress on the run row."""

import logging
import threading
import time
import traceback
from datetime import datetime, timezone

from sqlalchemy.orm import sessionmaker

from backend.config import get_settings
from backend.db import SessionLocal
from backend.models import MonitoringRun
from backend.services.analyze import analyze
from backend.services.enrich import enrich
from backend.services.ingest import ingest
from backend.services.naming import name_narratives
from backend.services.progress import InsufficientCoverage, Reporter
from backend.services.runs import create_run  # noqa: F401  (re-exported for the CLI)
from pipeline.models import release_models

log = logging.getLogger(__name__)

# One pipeline at a time: the models need most of the GPU and RAM. Later runs
# stay "pending" until the current one finishes.
_pipeline_lock = threading.Lock()

# (stage function, share of the progress bar)
STAGES = [(ingest, 0.35), (enrich, 0.3), (analyze, 0.15), (name_narratives, 0.2)]


def execute_run(run_id: int, session_factory: sessionmaker = SessionLocal) -> None:
    with _pipeline_lock, session_factory() as session:
        run = session.get(MonitoringRun, run_id)
        run.status = "running"
        run.started_at = datetime.now(timezone.utc)
        run.error = None
        session.commit()
        report = Reporter(session, run)
        timings: dict[str, float] = {}
        monitor = run.monitor
        log.info("[run %s] started: %r, last %sh, languages %s", run.id, monitor.topic, monitor.time_range_hours, monitor.languages)
        try:
            lo = 0.0
            for stage, share in STAGES:
                started = time.perf_counter()
                try:
                    stage(session, run, monitor, report.span(lo, lo + share))
                finally:
                    timings[stage.__name__] = round(time.perf_counter() - started, 1)
                    log.info("[run %s] stage %-16s took %5.1fs", run.id, stage.__name__, timings[stage.__name__])
                lo += share
            run.status = "completed"
            run.stats = {**(run.stats or {}), "outcome": "narratives"}
            report("done", 1.0)
        except InsufficientCoverage as exc:
            # a legitimate result, not an error: keep what the stages recorded
            run.status = "completed"
            run.stats = {**(run.stats or {}), "outcome": "insufficient_coverage"}
            report("done", 1.0, str(exc))
        except Exception as exc:
            log.exception("[run %s] failed", run_id)
            session.rollback()
            run.status = "failed"
            run.error = "".join(traceback.format_exception_only(exc)).strip()
            run.message = traceback.format_exc()[-2000:]
        finally:
            if not get_settings().keep_models_loaded:
                release_models()
            run.finished_at = datetime.now(timezone.utc)
            run.stats = {**(run.stats or {}), "timings_s": timings}
            session.commit()
            log_summary(run)


def log_summary(run: MonitoringRun) -> None:
    """One readable block per run: where the articles went, and where the time went."""
    s = run.stats or {}
    rss = (s.get("sources") or {}).get("rss", {})
    funnel = [
        ("feeds read", rss.get("feeds_ok")),
        ("headlines", rss.get("headlines")),
        ("in time window", rss.get("in_window")),
        ("matched the topic", s.get("collected")),
        ("kept after cleaning", s.get("stored")),
        ("unique after dedup", s.get("enriched")),
        ("relevant", s.get("relevant")),
        ("narratives", s.get("narratives")),
    ]
    lines = [f"[run {run.id}] {run.status}" + (f" ({s['outcome']})" if s.get("outcome") else "")]
    lines += [f"    {name:<22} {value}" for name, value in funnel if value is not None]
    if s.get("by_language"):
        lines.append(f"    {'languages':<22} {s['by_language']}")
    timings = s.get("timings_s") or {}
    if timings:
        steps = ", ".join(f"{k} {v}s" for k, v in timings.items())
        lines.append(f"    {'time':<22} {steps}  (total {sum(timings.values()):.1f}s)")
    if run.error:
        lines.append(f"    error: {run.error}")
    elif run.message:
        lines.append(f"    note: {run.message}")
    log.info("\n".join(lines))
