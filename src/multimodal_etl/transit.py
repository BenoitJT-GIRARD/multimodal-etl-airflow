"""Working area — the handoff between two pipeline steps.

Airflow lets you replay **any task of a DAG independently of the others**. For that to
be true here, no step receives its data from the previous one through memory: every step
**writes its result to disk**, under ``data/interim/``, and the next one **reads that
file back**.

Three practical consequences:

* a task can be replayed on its own, without replaying the ones before it;
* if the working file is gone, the step falls back to the last archived artefact
  (``data/raw/`` or ``data/processed/``): it stays runnable;
* a final DAG task **empties the working area** once the data has been consumed, so no
  temporary file is left lying around.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

from multimodal_etl.config import INTERIM_DIR, PROCESSED_DIR, RAW_DIR
from multimodal_etl.logging_setup import get_logger

logger = get_logger(__name__)

# Names of the files exchanged between steps. They are fixed: that is what lets a task
# find the input waiting for it without knowing anything about the run that produced it.
EXTRACTION = "extraction.json"
DATASET = "dataset.parquet"

# Metrics dropped by each step and read back by the "metrics" step.
METRICS_FILES = {
    "extract": "metrics_extract.json",
    "transform": "metrics_transform.json",
    "load": "metrics_load.json",
}


def path_for(name: str) -> Path:
    """Return the path of a file in the working area."""
    return INTERIM_DIR / name


def _latest_artefact(directory: Path, pattern: str) -> Path | None:
    """Return the most recent file of a directory matching a pattern.

    The file name breaks the tie between two artefacts written in the same second: every
    name the pipeline produces carries a sortable timestamp.
    """
    if not directory.exists():
        return None
    files = sorted(directory.glob(pattern), key=lambda p: (p.stat().st_mtime, p.name), reverse=True)
    return files[0] if files else None


def stage(artefact: Path, name: str) -> Path:
    """Copy an artefact produced by a step into the working area."""
    INTERIM_DIR.mkdir(parents=True, exist_ok=True)
    destination = path_for(name)
    shutil.copy2(artefact, destination)
    logger.info("Working area: '%s' staged for the next step", name)
    return destination


def write_metrics(step: str, metrics: dict[str, object]) -> Path:
    """Record the metrics of a step (duration, volumes) in the working area."""
    INTERIM_DIR.mkdir(parents=True, exist_ok=True)
    destination = path_for(METRICS_FILES[step])
    destination.write_text(
        json.dumps(metrics, ensure_ascii=False, indent=2, default=str), encoding="utf-8"
    )
    return destination


def read_metrics(step: str) -> dict[str, object]:
    """Read back the metrics of a step, or an empty dict when they are missing."""
    path = path_for(METRICS_FILES[step])
    if not path.exists():
        logger.warning("Working area: metrics missing for step '%s'", step)
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def extraction_input() -> Path | None:
    """Return the raw file to transform.

    The file staged by the extract task comes first; when it is absent — the task was
    replayed on its own, or the working area has already been cleared — we fall back to
    the last archived extraction.
    """
    path = path_for(EXTRACTION)
    if path.exists():
        return path

    fallback = _latest_artefact(RAW_DIR, "raw_publications_*.json")
    if fallback is not None:
        logger.warning(
            "Working area: '%s' missing, falling back to archive %s", EXTRACTION, fallback.name
        )
    return fallback


def dataset_input() -> Path | None:
    """Return the transformed dataset to load, with the same fallback mechanism."""
    path = path_for(DATASET)
    if path.exists():
        return path

    fallback = _latest_artefact(PROCESSED_DIR, "publications_*.parquet")
    if fallback is not None:
        logger.warning(
            "Working area: '%s' missing, falling back to archive %s", DATASET, fallback.name
        )
    return fallback


def clear() -> list[str]:
    """Delete every file of the working area and return their names."""
    if not INTERIM_DIR.exists():
        return []

    removed = []
    for path in sorted(INTERIM_DIR.iterdir()):
        if path.is_file():
            path.unlink()
            removed.append(path.name)

    logger.info("Working area: %d temporary files deleted", len(removed))
    return removed
