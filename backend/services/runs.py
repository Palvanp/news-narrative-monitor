from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from backend.models import Monitor, MonitoringRun


def create_run(session: Session, monitor: Monitor) -> MonitoringRun:
    end = datetime.now(timezone.utc).replace(second=0, microsecond=0)
    run = MonitoringRun(
        monitor_id=monitor.id,
        window_start=end - timedelta(hours=monitor.time_range_hours),
        window_end=end,
    )
    session.add(run)
    session.commit()
    return run
