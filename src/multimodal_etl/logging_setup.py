"""Central logging setup for the pipeline.

The standard ``logging`` module is configured once and for all: console output plus a
timestamped file under ``logs/``. Every module gets its logger through
:func:`get_logger`.
"""

from __future__ import annotations

import logging
import sys
from logging import Logger

from multimodal_etl.config import LOGS_DIR

_FORMAT = "%(asctime)s | %(levelname)-7s | %(name)s | %(message)s"
_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"
_configured = False


def setup_logging(level: int = logging.INFO, logfile: str = "multimodal_etl.log") -> None:
    """Configure the root logger (console + file).

    Idempotent: only the first call does anything, later ones are ignored. It is called
    at the start of every script, notebook and Airflow task.
    """
    global _configured
    if _configured:
        return

    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    formatter = logging.Formatter(_FORMAT, datefmt=_DATE_FORMAT)

    console = logging.StreamHandler(stream=sys.stdout)
    console.setFormatter(formatter)

    to_file = logging.FileHandler(LOGS_DIR / logfile, encoding="utf-8")
    to_file.setFormatter(formatter)

    root = logging.getLogger()
    root.setLevel(level)
    root.handlers.clear()
    root.addHandler(console)
    root.addHandler(to_file)
    _configured = True


def get_logger(name: str) -> Logger:
    """Return a named logger, making sure the configuration is in place."""
    if not _configured:
        setup_logging()
    return logging.getLogger(name)
