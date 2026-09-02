"""Pipeline ETL complet, exécutable en une commande.

Enchaîne les cinq étapes — extraction, transformation, chargement, métriques et
nettoyage — dans le même ordre que le DAG Airflow, et **en appelant exactement les
mêmes fonctions**. C'est la version « script » de référence : elle sert à valider
le pipeline avant de l'orchestrer.

Usage :
    uv run python scripts/run_etl.py
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from dotenv import load_dotenv

load_dotenv(ROOT / ".env")

from multimodal_etl.logging_setup import get_logger, setup_logging
from multimodal_etl.pipeline import (
    run_cleanup,
    run_extract,
    run_load,
    run_metrics,
    run_transform,
)

logger = get_logger("multimodal_etl.etl")


def main() -> None:
    """Exécute l'ETL de bout en bout et affiche le bilan de l'exécution."""
    setup_logging()

    run_extract()
    run_transform()
    run_load()
    run = run_metrics(orchestrateur="script")
    run_cleanup()

    duree = sum(run["durations_sec"].values())
    logger.info("ETL terminé : %d nouvelles publications en %.2fs", run["rows_loaded"], duree)

    print(f"[ok] publications extraites  : {run['rows_extracted']}")
    print(f"[ok] nouvelles en base       : {run['rows_loaded']}")
    print(f"[ok] total accumulé en base  : {run['rows_in_db']}")
    print(f"[ok] durée totale            : {duree:.2f} s")
    print(f"[ok] fiche d'exécution       : {run['fichier']}")


if __name__ == "__main__":
    main()
