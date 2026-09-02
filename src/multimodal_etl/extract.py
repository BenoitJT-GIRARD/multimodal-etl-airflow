"""Step E — extract (collecting the raw data).

This module drives the source connectors, downloads the associated images, then saves the
raw result as JSON under ``data/raw/``. It runs **without manual intervention**: each
source is isolated in its own try/except, so a source that is down never stops the others
from working.

The output format is **JSON** rather than CSV: a multimodal publication pairs a text with
an **image file path**, and JSON keeps that structure unambiguous (CSV would be enough for
text alone).
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from multimodal_etl.config import RAW_DIR, ExtractionConfig, ImageConfig, ensure_dirs
from multimodal_etl.images import download_images
from multimodal_etl.logging_setup import get_logger
from multimodal_etl.sources import fakenewsnet, kaggle_fakeddit, newsdata, rss

logger = get_logger(__name__)

# Connector table: logical name -> extraction function. Adding a source to the pipeline
# means writing a module under `sources/` and one line here.
_CONNECTORS = {
    "rss": rss.fetch_all_rss,
    "newsdata": newsdata.fetch_newsdata,
    "fakenewsnet": fakenewsnet.fetch_fakenewsnet,
    "kaggle_fakeddit": kaggle_fakeddit.fetch_fakeddit,
}


def _timestamp() -> str:
    """Compact timestamp, used to name the output files."""
    return datetime.now(UTC).strftime("%Y%m%d_%H%M%S")


def collect_sources(config: ExtractionConfig | None = None) -> tuple[list[dict], dict[str, int]]:
    """Run every connector and return the raw publications and the per-source tally.

    The tally — number of publications per connector, ``-1`` on failure — feeds the
    "failed sources" KPI of the monitoring plan.
    """
    config = config or ExtractionConfig()
    ensure_dirs()

    publications: list[dict] = []
    tally: dict[str, int] = {}

    for name, connector in _CONNECTORS.items():
        logger.info("Extract: starting source '%s'", name)
        try:
            collected = connector(config)
        except Exception as exc:
            logger.error("Extract: source '%s' failed: %s", name, exc)
            tally[name] = -1
            continue
        logger.info("Extract: source '%s' -> %d publications", name, len(collected))
        tally[name] = len(collected)
        publications.extend(collected)

    logger.info("Extract: %d raw publications in total", len(publications))
    return publications, tally


def failed_sources(tally: dict[str, int]) -> int:
    """Count the sources that are genuinely down, for the monitoring plan's alert.

    A source that is deliberately **turned off** is not an outage: NewsData.io only runs
    when an API key is supplied, and its absence must not raise an alert. Without that
    distinction, a healthy pipeline would go amber as soon as it ran without a key.
    """
    disabled = set() if newsdata.is_enabled() else {"newsdata"}
    return sum(1 for name, count in tally.items() if count <= 0 and name not in disabled)


def extract_all(config: ExtractionConfig | None = None) -> list[dict]:
    """Collect the publications of every source, images included."""
    publications, _ = collect_sources(config)
    download_images(publications, ImageConfig())
    return publications


def save_raw(records: list[dict], path: Path | None = None) -> Path:
    """Save the raw publications as JSON and return the path of the file."""
    ensure_dirs()
    path = path or RAW_DIR / f"raw_publications_{_timestamp()}.json"
    with path.open("w", encoding="utf-8") as handle:
        json.dump(records, handle, ensure_ascii=False, indent=2)
    logger.info("Extract: %d publications written to %s", len(records), path)
    return path


def run_extraction(config: ExtractionConfig | None = None) -> tuple[Path, dict[str, object]]:
    """The whole extract pipeline: collect, images, then the JSON save.

    Returns the path of the raw file and a report of the run — the per-source tally and
    the image download statistics — which the KPIs consume.
    """
    publications, tally = collect_sources(config)
    image_counts = download_images(publications, ImageConfig())
    path = save_raw(publications)

    report: dict[str, object] = {
        "publications_extraites": len(publications),
        "bilan_sources": tally,
        "failed_sources": failed_sources(tally),
        "images": image_counts,
        "fichier_brut": str(path),
    }
    return path, report
