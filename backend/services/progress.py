import logging

from sqlalchemy.orm import Session

from backend.models import MonitoringRun

log = logging.getLogger(__name__)


class InsufficientCoverage(Exception):
    """Not enough relevant, coherent coverage to report narratives. A run that
    stops here completes normally with this explanation instead of failing."""


class Reporter:
    """Writes stage/progress to the run row so the UI can poll it.

    `span(lo, hi)` gives a child reporter whose 0..1 progress maps onto lo..hi
    of the parent, so each stage reports its own progress from 0 to 1.
    """

    def __init__(self, session: Session, run: MonitoringRun, lo: float = 0.0, hi: float = 1.0):
        self.session = session
        self.run = run
        self.lo = lo
        self.hi = hi

    def span(self, lo: float, hi: float) -> "Reporter":
        width = self.hi - self.lo
        return Reporter(self.session, self.run, self.lo + lo * width, self.lo + hi * width)

    def __call__(self, stage: str, progress: float, message: str | None = None) -> None:
        overall = self.lo + min(max(progress, 0.0), 1.0) * (self.hi - self.lo)
        self.run.stage = stage
        self.run.progress = round(overall, 3)
        self.run.message = message
        self.session.commit()
        log.info("[run %s] %s %.0f%% %s", self.run.id, stage, overall * 100, message or "")
