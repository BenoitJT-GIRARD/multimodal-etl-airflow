"""Journalisation centralisée du pipeline.

On configure une fois pour toutes le module standard ``logging`` : sortie console
+ fichier horodaté dans ``logs/``. Chaque module récupère son logger via
:func:`get_logger`.
"""

from __future__ import annotations

import logging
import sys
from logging import Logger

from multimodal_etl.config import LOGS_DIR

_FORMAT = "%(asctime)s | %(levelname)-7s | %(name)s | %(message)s"
_FORMAT_DATE = "%Y-%m-%d %H:%M:%S"
_configure = False


def setup_logging(level: int = logging.INFO, logfile: str = "multimodal_etl.log") -> None:
    """Configure la journalisation racine (console + fichier).

    Idempotent : un seul appel réel, les suivants sont ignorés. On l'appelle au
    début de chaque script, notebook ou tâche Airflow.
    """
    global _configure
    if _configure:
        return

    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    formateur = logging.Formatter(_FORMAT, datefmt=_FORMAT_DATE)

    console = logging.StreamHandler(stream=sys.stdout)
    console.setFormatter(formateur)

    fichier = logging.FileHandler(LOGS_DIR / logfile, encoding="utf-8")
    fichier.setFormatter(formateur)

    racine = logging.getLogger()
    racine.setLevel(level)
    racine.handlers.clear()
    racine.addHandler(console)
    racine.addHandler(fichier)
    _configure = True


def get_logger(name: str) -> Logger:
    """Renvoie un logger nommé, en s'assurant que la configuration est en place."""
    if not _configure:
        setup_logging()
    return logging.getLogger(name)
