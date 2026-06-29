"""Journalisation centralisee du pipeline.

La mission demande explicitement d'« ajouter des logs » (etape 2) et d'« utiliser
Logging pour journaliser chaque transformation » (etape 3). On configure donc une
fois pour toutes le module standard ``logging`` : sortie console + fichier horodate
dans ``logs/``. Chaque module recupere son logger via :func:`get_logger`.
"""

from __future__ import annotations

import logging
import sys
from logging import Logger

from multimodal_etl.config import LOGS_DIR

_LOG_FORMAT = "%(asctime)s | %(levelname)-7s | %(name)s | %(message)s"
_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"
_configured = False


def setup_logging(level: int = logging.INFO, logfile: str = "multimodal_etl.log") -> None:
    """Configure la journalisation racine (console + fichier).

    Idempotent : un seul appel reel, les suivants sont ignores. On l'appelle au
    debut de chaque script / notebook / tache Airflow.
    """
    global _configured
    if _configured:
        return

    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    formatter = logging.Formatter(_LOG_FORMAT, datefmt=_DATE_FORMAT)

    console = logging.StreamHandler(stream=sys.stdout)
    console.setFormatter(formatter)

    file_handler = logging.FileHandler(LOGS_DIR / logfile, encoding="utf-8")
    file_handler.setFormatter(formatter)

    root = logging.getLogger()
    root.setLevel(level)
    root.handlers.clear()
    root.addHandler(console)
    root.addHandler(file_handler)
    _configured = True


def get_logger(name: str) -> Logger:
    """Renvoie un logger nomme, en s'assurant que la configuration est en place."""
    if not _configured:
        setup_logging()
    return logging.getLogger(name)
