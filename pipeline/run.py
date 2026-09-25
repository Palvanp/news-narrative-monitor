"""Command-line pipeline run, without the API or UI.

    uv run python -m pipeline.run --topic "India-US trade negotiations" --hours 24
"""

import argparse
import json
import logging
import sys

from backend.db import SessionLocal, init_db
from backend.models import Monitor, MonitoringRun
from backend.services.runner import create_run, execute_run


def main() -> int:
    parser = argparse.ArgumentParser(description="Run a Nazar monitor from the command line")
    parser.add_argument("--topic", required=True)
    parser.add_argument("--hours", type=int, default=24)
    parser.add_argument("--languages", default="en,hi")
    parser.add_argument("--hindi-keywords", default=None)
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    for noisy in ("httpx", "trafilatura", "htmldate"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
    init_db()

    with SessionLocal() as session:
        monitor = Monitor(
            topic=args.topic,
            hindi_keywords=args.hindi_keywords,
            languages=[lang.strip() for lang in args.languages.split(",") if lang.strip()],
            time_range_hours=args.hours,
        )
        session.add(monitor)
        session.commit()
        run_id = create_run(session, monitor).id

    execute_run(run_id)

    with SessionLocal() as session:
        run = session.get(MonitoringRun, run_id)
        print(json.dumps({"run_id": run.id, "status": run.status, "error": run.error, "stats": run.stats}, indent=2))
        return 0 if run.status == "completed" else 1


if __name__ == "__main__":
    sys.exit(main())
