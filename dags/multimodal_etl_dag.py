"""DAG Airflow — orchestration du pipeline ETL.

Ce DAG automatise le flux **Extract -> Transform -> Load** des donnees multimodales.
Conformement aux recommandations de la mission, il **reprend directement les
fonctions** du package ``multimodal_etl`` (memes fonctions que le script de l'etape 3)
et les repartit en **taches distinctes**, reliees par des PythonOperator simples.
Les chemins de fichiers sont transmis d'une tache a l'autre via XCom.

Execution locale : voir ``docs/runbook_airflow.md`` (Airflow via Docker).
"""

from __future__ import annotations

import json
import sys
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path

from airflow import DAG

# PythonOperator : le chemin d'import a change entre Airflow 2.x et 3.x.
try:
    from airflow.operators.python import PythonOperator
except ImportError:  # pragma: no cover - Airflow 3.x
    from airflow.providers.standard.operators.python import PythonOperator

# Rend le package multimodal_etl importable depuis le conteneur (src monte par Docker).
PROJECT_SRC = Path("/opt/airflow/project/src")
if PROJECT_SRC.exists() and str(PROJECT_SRC) not in sys.path:
    sys.path.insert(0, str(PROJECT_SRC))

from multimodal_etl.config import (
    ExtractionConfig,
    LoadConfig,
    TransformConfig,
)
from multimodal_etl.extract import extract_all, save_raw
from multimodal_etl.kpi import RUNS_DIR
from multimodal_etl.load import run_load
from multimodal_etl.sources import newsdata
from multimodal_etl.transform import run_transformation


# --------------------------------------------------------------------------- #
# Fonctions des taches (callables des PythonOperator)
# --------------------------------------------------------------------------- #
def tache_extract(**context) -> str:
    """Tache E : collecte les publications brutes et renvoie le chemin du JSON."""
    debut = time.perf_counter()
    records = extract_all(ExtractionConfig())
    raw_path = save_raw(records)
    ti = context["ti"]
    ti.xcom_push(key="duree_extract", value=time.perf_counter() - debut)
    ti.xcom_push(key="rows_extracted", value=len(records))
    return str(raw_path)


def tache_transform(**context) -> str:
    """Tache T : nettoie/normalise et renvoie le chemin du dataset transforme."""
    ti = context["ti"]
    raw_path = Path(ti.xcom_pull(task_ids="extract"))
    debut = time.perf_counter()
    dataset_path, stats = run_transformation(raw_path, TransformConfig())
    ti.xcom_push(key="duree_transform", value=time.perf_counter() - debut)
    ti.xcom_push(key="stats", value=stats)
    return str(dataset_path)


def tache_load(**context) -> int:
    """Tache L : charge le dataset en base et renvoie le nombre de lignes."""
    ti = context["ti"]
    dataset_path = Path(ti.xcom_pull(task_ids="transform"))
    debut = time.perf_counter()
    rows = run_load(dataset_path, LoadConfig())
    ti.xcom_push(key="duree_load", value=time.perf_counter() - debut)
    ti.xcom_push(key="rows_loaded", value=rows)
    ti.xcom_push(key="dataset_path", value=str(dataset_path))
    return rows


def tache_metriques(**context) -> str:
    """Tache supplementaire : consolide les metriques d'execution pour les KPI."""
    ti = context["ti"]
    durations = {
        "extract": ti.xcom_pull(task_ids="extract", key="duree_extract") or 0.0,
        "transform": ti.xcom_pull(task_ids="transform", key="duree_transform") or 0.0,
        "load": ti.xcom_pull(task_ids="load", key="duree_load") or 0.0,
    }
    run = {
        "run_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "durations_sec": durations,
        "rows_extracted": ti.xcom_pull(task_ids="extract", key="rows_extracted") or 0,
        "rows_loaded": ti.xcom_pull(task_ids="load", key="rows_loaded") or 0,
        "api_calls": 1 if newsdata.is_enabled() else 0,
        "stats": ti.xcom_pull(task_ids="transform", key="stats") or {},
        "dataset_path": ti.xcom_pull(task_ids="load", key="dataset_path"),
        "orchestrateur": "airflow",
    }
    RUNS_DIR.mkdir(parents=True, exist_ok=True)
    run_file = RUNS_DIR / f"run_airflow_{datetime.now(UTC).strftime('%Y%m%d_%H%M%S')}.json"
    run_file.write_text(json.dumps(run, ensure_ascii=False, indent=2), encoding="utf-8")
    return str(run_file)


# --------------------------------------------------------------------------- #
# Definition du DAG
# --------------------------------------------------------------------------- #
default_args = {
    "owner": "multimodal_etl",
    "retries": 1,
    "retry_delay": timedelta(minutes=2),
}

with DAG(
    dag_id="multimodal_etl",
    description="Extraction, transformation et chargement de donnees multimodales (fake news).",
    default_args=default_args,
    start_date=datetime(2026, 1, 1),
    schedule="@daily",  # planification quotidienne pour garder le dataset frais
    catchup=False,
    tags=["multimodal_etl", "etl", "multimodal", "fake-news"],
) as dag:
    extract = PythonOperator(task_id="extract", python_callable=tache_extract)
    transform = PythonOperator(task_id="transform", python_callable=tache_transform)
    load = PythonOperator(task_id="load", python_callable=tache_load)
    metriques = PythonOperator(task_id="metriques", python_callable=tache_metriques)

    # Dependances : E -> T -> L -> metriques
    extract >> transform >> load >> metriques
