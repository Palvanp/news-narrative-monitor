"""Logging for the API server and the CLI: readable lines in the terminal and the
same lines in data/logs/nazar.log (rotated), so a run can be followed live with

    Get-Content data\\logs\\nazar.log -Wait        (PowerShell)
    tail -f data/logs/nazar.log                    (bash)
"""

import logging
import logging.handlers

from backend.config import get_settings

FORMAT = "%(asctime)s %(levelname)-7s %(name)-24s %(message)s"
DATEFMT = "%H:%M:%S"
NOISY = ("httpx", "httpcore", "trafilatura", "htmldate", "urllib3", "filelock", "numba", "huggingface_hub", "sentence_transformers", "transformers")

_configured = False


def setup_logging(level: int = logging.INFO) -> None:
    global _configured
    if _configured:
        return
    log_dir = get_settings().data_dir / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)

    formatter = logging.Formatter(FORMAT, DATEFMT)
    console = logging.StreamHandler()
    console.setFormatter(formatter)
    file = logging.handlers.RotatingFileHandler(log_dir / "nazar.log", maxBytes=5_000_000, backupCount=3, encoding="utf-8")
    file.setFormatter(logging.Formatter("%(asctime)s %(levelname)-7s %(name)-24s %(message)s"))

    for name in ("backend", "pipeline"):
        logger = logging.getLogger(name)
        logger.setLevel(level)
        logger.addHandler(console)
        logger.addHandler(file)
        logger.propagate = False
    for name in NOISY:
        logging.getLogger(name).setLevel(logging.WARNING)
    _configured = True
