"""Runs the Nazar pipeline for a monitoring run and records progress on the run row."""

import logging
import threading
import traceback
from datetime import datetime, timezone

from sqlalchemy.orm import sessionmaker

from backend.db import SessionLocal
from backend.models import MonitoringRun
from backend.services.analyze import analyze
from backend.services.enrich import enrich
from backend.services.ingest import ingest
from backend.services.naming import name_narratives
from backend.services.progress import Reporter
from backend.services.runs import create_run  # noqa: F401  (re-exported for the CLI)
from pipeline.embeddings.encoder import release_shared_encoders

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
        try:
            lo = 0.0
            for stage, share in STAGES:
                stage(session, run, run.monitor, report.span(lo, lo + share))
                lo += share
            run.status = "completed"
            report("done", 1.0)
        except Exception as exc:
            log.exception("run %s failed", run_id)
            session.rollback()
            run.status = "failed"
            run.error = "".join(traceback.format_exception_only(exc)).strip()
            run.message = traceback.format_exc()[-2000:]
        finally:
            release_shared_encoders()
            run.finished_at = datetime.now(timezone.utc)
            session.commit()
