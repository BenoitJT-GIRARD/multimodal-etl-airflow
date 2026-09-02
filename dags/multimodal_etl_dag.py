"""DAG Airflow — orchestration du pipeline ETL Multimodal ETL.

Le DAG automatise le flux **Extract → Transform → Load**, puis consolide les
métriques et fait le ménage. Il **reprend directement les fonctions** du package
``multimodal_etl`` : chaque ``PythonOperator`` appelle une étape de
:mod:`multimodal_etl.pipeline`, sans logique métier écrite ici.

**Les tâches sont indépendantes.** Aucune donnée ne transite par XCom : chaque
étape écrit son résultat dans ``data/interim/`` et l'étape suivante relit ce
fichier. On peut donc rejouer n'importe quelle tâche seule ::

    airflow tasks test multimodal_etl transformation 2026-08-20

Si le fichier de transit n'existe plus, l'étape reprend le dernier artefact
archivé. La tâche finale ``nettoyage`` vide la zone de transit une fois les
fichiers consommés.

Exécution locale : voir ``docs/runbook_airflow.md``.
"""

from __future__ import annotations

import sys
from datetime import datetime, timedelta
from pathlib import Path

from airflow import DAG

# PythonOperator : le chemin d'import a changé entre Airflow 2.x et 3.x.
try:
    from airflow.operators.python import PythonOperator
except ImportError:  # pragma: no cover - Airflow 3.x
    from airflow.providers.standard.operators.python import PythonOperator

# Rend le package multimodal_etl importable depuis le conteneur (src monté par Docker).
PROJECT_SRC = Path("/opt/airflow/project/src")
if PROJECT_SRC.exists() and str(PROJECT_SRC) not in sys.path:
    sys.path.insert(0, str(PROJECT_SRC))

from multimodal_etl.pipeline import (
    run_cleanup,
    run_extract,
    run_load,
    run_metrics,
    run_transform,
)


def task_metrics() -> dict:
    """Consolide les mesures en précisant que l'exécution vient d'Airflow."""
    return run_metrics(orchestrateur="airflow")


default_args = {
    "owner": "multimodal_etl",
    "retries": 1,
    "retry_delay": timedelta(minutes=2),
}

with DAG(
    dag_id="multimodal_etl",
    description="Extraction, transformation et chargement de données multimodales (fake news).",
    default_args=default_args,
    start_date=datetime(2026, 1, 1),
    schedule="@daily",  # planification quotidienne pour garder le dataset frais
    catchup=False,
    tags=["multimodal_etl", "etl", "multimodal", "fake-news"],
) as dag:
    extraction = PythonOperator(
        task_id="extraction",
        python_callable=run_extract,
        doc_md="Collecte les publications des 4 sources et télécharge leurs images.",
    )
    transformation = PythonOperator(
        task_id="transformation",
        python_callable=run_transform,
        doc_md="Nettoie, valide et normalise les publications en un dataset propre.",
    )
    chargement = PythonOperator(
        task_id="chargement",
        python_callable=run_load,
        doc_md="Charge les nouvelles publications dans la base relationnelle.",
    )
    metriques = PythonOperator(
        task_id="metriques",
        python_callable=task_metrics,
        doc_md="Consolide durées et volumes en une fiche d'exécution pour les KPI.",
    )
    nettoyage = PythonOperator(
        task_id="nettoyage",
        python_callable=run_cleanup,
        doc_md="Vide la zone de transit une fois les fichiers temporaires consommés.",
    )

    extraction >> transformation >> chargement >> metriques >> nettoyage
