"""The five pipeline steps, written so that each can run on its own.

One function per step. These are **exactly the functions** called by the command-line
scripts, by the notebooks and by the ``PythonOperator`` instances of the Airflow DAG:
there is a single copy of the logic.

Every step follows the same contract, and it is that contract which makes the tasks
independent of one another:

1. it reads its input from the **working area** (:mod:`multimodal_etl.transit`), falling
   back to the last archived artefact if the temporary file is gone;
2. it archives its own result under ``data/raw/`` or ``data/processed/``;
3. it drops a working copy into the working area for the next step;
4. it times itself and writes a run record.

The last step, :func:`run_cleanup`, empties the working area once its files have been
consumed.
"""

from __future__ import annotations

import json
import time
from datetime import UTC, datetime

from multimodal_etl import transit
from multimodal_etl.config import (
    RUNS_DIR,
    ExtractionConfig,
    LoadConfig,
    TransformConfig,
    ensure_dirs,
    relative_path,
)
from multimodal_etl.extract import run_extraction
from multimodal_etl.load import count_publications, load_dataset
from multimodal_etl.logging_setup import get_logger
from multimodal_etl.sources import newsdata
from multimodal_etl.transform import run_transformation

logger = get_logger(__name__)


def _now() -> str:
    """Current instant as an ISO timestamp, in UTC."""
    return datetime.now(UTC).isoformat(timespec="seconds")


# --------------------------------------------------------------------------- #
# Step 1 — extract
# --------------------------------------------------------------------------- #
def run_extract(config: ExtractionConfig | None = None) -> dict[str, object]:
    """Collect publications from every source and download their images."""
    logger.info("=== STEP 1 — EXTRACT ===")
    ensure_dirs()
    started = time.perf_counter()

    archive, report = run_extraction(config or ExtractionConfig())
    transit.stage(archive, transit.EXTRACTION)

    metrics = {
        "at": _now(),
        "duration_sec": round(time.perf_counter() - started, 2),
        "archive": str(archive),
        # One API call is spent per run while the NewsData.io source is enabled.
        "api_calls": 1 if newsdata.is_enabled() else 0,
        **report,
    }
    transit.write_metrics("extract", metrics)
    return metrics


# --------------------------------------------------------------------------- #
# Step 2 — transform
# --------------------------------------------------------------------------- #
def run_transform(config: TransformConfig | None = None) -> dict[str, object]:
    """Clean, validate and normalise the raw publications into a tidy dataset."""
    logger.info("=== STEP 2 — TRANSFORM ===")
    ensure_dirs()
    source = transit.extraction_input()
    if source is None:
        raise FileNotFoundError("No extraction available: run the extract step first.")

    started = time.perf_counter()
    archive, stats = run_transformation(source, config or TransformConfig())
    transit.stage(archive, transit.DATASET)

    metrics = {
        "at": _now(),
        "duration_sec": round(time.perf_counter() - started, 2),
        "input": str(source),
        "archive": str(archive),
        "stats": stats,
    }
    transit.write_metrics("transform", metrics)
    return metrics


# --------------------------------------------------------------------------- #
# Step 3 — load
# --------------------------------------------------------------------------- #
def run_load(config: LoadConfig | None = None) -> dict[str, object]:
    """Insert the publications that are not already in the relational database."""
    logger.info("=== STEP 3 — LOAD ===")
    config = config or LoadConfig()
    source = transit.dataset_input()
    if source is None:
        raise FileNotFoundError("No dataset available: run the transform step first.")

    started = time.perf_counter()
    per_table = load_dataset(source, config)

    metrics = {
        "at": _now(),
        "duration_sec": round(time.perf_counter() - started, 2),
        "input": str(source),
        "per_table": per_table,
        "publications_added": per_table.get(config.table_name, 0),
        "publications_in_db": count_publications(config),
    }
    transit.write_metrics("load", metrics)
    return metrics


# --------------------------------------------------------------------------- #
# Step 4 — run metrics
# --------------------------------------------------------------------------- #
def run_metrics(orchestrator: str = "script") -> dict[str, object]:
    """Consolidate the metrics of the first three steps into one run record.

    That record is the only history the KPI dashboard needs: one per run, kept under
    ``data/processed/runs/``.
    """
    logger.info("=== STEP 4 — METRICS ===")
    extraction = transit.read_metrics("extract")
    transformation = transit.read_metrics("transform")
    loading = transit.read_metrics("load")

    images = extraction.get("images", {}) or {}
    run = {
        "run_at": _now(),
        "orchestrator": orchestrator,
        "durations_sec": {
            "extract": extraction.get("duration_sec", 0.0),
            "transform": transformation.get("duration_sec", 0.0),
            "load": loading.get("duration_sec", 0.0),
        },
        "rows_extracted": extraction.get("publications_extracted", 0),
        "rows_loaded": loading.get("publications_added", 0),
        "rows_in_db": loading.get("publications_in_db", 0),
        "api_calls": extraction.get("api_calls", 0),
        "per_source": extraction.get("per_source", {}),
        "failed_sources": extraction.get("failed_sources", 0),
        "images": images,
        "stats": transformation.get("stats", {}),
        "dataset_path": transformation.get("archive", ""),
    }

    RUNS_DIR.mkdir(parents=True, exist_ok=True)
    record = RUNS_DIR / f"run_{datetime.now(UTC).strftime('%Y%m%d_%H%M%S')}.json"
    record.write_text(json.dumps(run, ensure_ascii=False, indent=2), encoding="utf-8")
    logger.info("Metrics: run record written to %s", relative_path(record))

    run["file"] = str(record)
    return run


# --------------------------------------------------------------------------- #
# Step 5 — clear the working area
# --------------------------------------------------------------------------- #
def run_cleanup() -> dict[str, object]:
    """Delete the temporary files once every one of them has been consumed."""
    logger.info("=== STEP 5 — CLEANUP ===")
    removed = transit.clear()
    return {"files_removed": removed, "count": len(removed)}
