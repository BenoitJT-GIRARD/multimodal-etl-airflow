"""Airflow DAG orchestrating the multimodal ETL pipeline.

The DAG runs Extract, Transform and Load, then consolidates the run metrics and clears
the working area. It **calls the package directly**: every ``PythonOperator`` invokes one
step of :mod:`multimodal_etl.pipeline`, and no business logic is written here.

**The tasks are independent.** Nothing travels through XCom: each step writes its result
to ``data/interim/`` and the next one reads that file back. Any single task can therefore
be replayed on its own ::

    airflow tasks test multimodal_etl transform 2026-08-20

If the working file is gone, the step falls back to the last archived artefact. The final
``cleanup`` task empties the working area once its files have been consumed.

Running it locally: see ``docs/runbook_airflow.md``.
"""

from __future__ import annotations

import sys
from datetime import datetime, timedelta
from pathlib import Path

from airflow import DAG

# The import path for PythonOperator moved between Airflow 2.x and 3.x.
try:
    from airflow.operators.python import PythonOperator
except ImportError:  # pragma: no cover - Airflow 3.x
    from airflow.providers.standard.operators.python import PythonOperator

# Make the package importable from inside the container, where Docker mounts src.
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
    """Consolidate the run metrics, recording that the run came from Airflow."""
    return run_metrics(orchestrateur="airflow")


default_args = {
    "owner": "multimodal_etl",
    "retries": 1,
    "retry_delay": timedelta(minutes=2),
}

with DAG(
    dag_id="multimodal_etl",
    description="Extract, transform and load multimodal publications for misinformation research.",
    default_args=default_args,
    start_date=datetime(2026, 1, 1),
    schedule="@daily",  # daily, to keep the dataset fresh
    catchup=False,
    tags=["multimodal_etl", "etl", "multimodal", "misinformation"],
) as dag:
    extract = PythonOperator(
        task_id="extract",
        python_callable=run_extract,
        doc_md="Collect publications from the four sources and download their images.",
    )
    transform = PythonOperator(
        task_id="transform",
        python_callable=run_transform,
        doc_md="Clean, validate and normalise the publications into a tidy dataset.",
    )
    load = PythonOperator(
        task_id="load",
        python_callable=run_load,
        doc_md="Insert the publications that are not already in the relational database.",
    )
    metrics = PythonOperator(
        task_id="metrics",
        python_callable=task_metrics,
        doc_md="Consolidate durations and volumes into one run record for the KPI board.",
    )
    cleanup = PythonOperator(
        task_id="cleanup",
        python_callable=run_cleanup,
        doc_md="Empty the working area once its temporary files have been consumed.",
    )

    extract >> transform >> load >> metrics >> cleanup
