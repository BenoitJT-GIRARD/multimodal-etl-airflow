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

import requests

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


# Why a source produced nothing. Only the first three are incidents: a source that is
# turned off, or that legitimately had nothing to give, is not a failure — and treating it
# as one would put a healthy pipeline permanently in the amber.
OK, QUOTA, NETWORK, MALFORMED, EMPTY, DISABLED = (
    "ok",
    "quota",
    "network",
    "malformed",
    "empty",
    "disabled",
)
INCIDENTS = frozenset({QUOTA, NETWORK, MALFORMED})

# Sources that can turn themselves off: their silence is a configuration choice.
_OPTIONAL = {"newsdata": newsdata.is_enabled}


def _cause_of(exc: Exception) -> str:
    """Name what went wrong, so a spent quota is not confused with a broken connector."""
    if isinstance(exc, requests.exceptions.HTTPError) and "429" in str(exc):
        return QUOTA
    if isinstance(exc, requests.exceptions.RequestException):
        return NETWORK
    return MALFORMED


def _timestamp() -> str:
    """Compact timestamp, used to name the output files."""
    return datetime.now(UTC).strftime("%Y%m%d_%H%M%S")


def collect_sources(
    config: ExtractionConfig | None = None,
) -> tuple[list[dict], dict[str, dict[str, object]]]:
    """Run every connector and return the raw publications and the per-source tally.

    Each entry of the tally carries a ``count`` — ``-1`` on failure — and a ``cause``
    saying **why** a source produced nothing. Counting without qualifying made a run that
    brought back three sources out of four look like a successful one.
    """
    config = config or ExtractionConfig()
    ensure_dirs()

    publications: list[dict] = []
    tally: dict[str, dict[str, object]] = {}

    for name, connector in _CONNECTORS.items():
        logger.info("Extract: starting source '%s'", name)
        try:
            collected = connector(config)
        except Exception as exc:
            cause = _cause_of(exc)
            logger.error("Extract: source '%s' failed (%s): %s", name, cause, exc)
            tally[name] = {"count": -1, "cause": cause}
            continue

        if collected:
            cause = OK
        elif not _OPTIONAL.get(name, lambda: True)():
            cause = DISABLED
        else:
            cause = EMPTY
        logger.info("Extract: source '%s' -> %d publications (%s)", name, len(collected), cause)
        tally[name] = {"count": len(collected), "cause": cause}
        publications.extend(collected)

    logger.info("Extract: %d raw publications in total", len(publications))
    return publications, tally


def failed_sources(tally: dict[str, dict[str, object]]) -> int:
    """Count the sources that are genuinely down, for the monitoring plan's alert.

    A source that is deliberately **turned off**, or that had nothing new to give, is not
    an outage: NewsData.io only runs when an API key is supplied, and its absence must not
    raise an alert. Without that distinction, a healthy pipeline would go amber as soon as
    it ran without a key.
    """
    return sum(1 for entry in tally.values() if entry.get("cause") in INCIDENTS)


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
        "publications_extracted": len(publications),
        "per_source": tally,
        "failed_sources": failed_sources(tally),
        "images": image_counts,
        "raw_file": str(path),
    }
    return path, report
