"""Airflow DAG orchestrating the multimodal ETL pipeline.

The DAG runs Extract, Transform and Load, then consolidates the run metrics and clears
the working area. It **calls the package directly**: every ``PythonOperator`` invokes one
step of :mod:`multimodal_etl.pipeline`, and no business logic is written here.

**The tasks are independent.** Nothing travels through XCom; the hand-off is the working area
:mod:`multimodal_etl.transit` describes, which is what lets any single task be replayed alone ::

    airflow tasks test multimodal_etl transform 2026-09-15

``docs/runbook.md`` shows one being replayed after ``cleanup`` had emptied that area.

The package is importable because the compose file puts the mounted source tree on
``PYTHONPATH``. A ``sys.path`` insert here would do the same thing and hide where the decision
was taken; the environment variable is next to the mount that makes it true.

Running it locally: see ``docs/runbook.md``.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from airflow import DAG

# The import path for PythonOperator moved between Airflow 2.x and 3.x.
try:
    from airflow.operators.python import PythonOperator
except ImportError:  # pragma: no cover - Airflow 3.x
    from airflow.providers.standard.operators.python import PythonOperator

from multimodal_etl.pipeline import (
    run_cleanup,
    run_extract,
    run_load,
    run_metrics,
    run_transform,
)


def task_metrics() -> dict:
    """Consolidate the run metrics, recording that the run came from Airflow."""
    return run_metrics(orchestrator="airflow")


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
