"""Connector 3 — FakeNewsNet, a labelled dataset hosted on GitHub.

FakeNewsNet (Shu *et al.*, 2018) is the academic reference for fake-news detection: every
publication carries a **ground-truth label** (``real`` / ``fake``) from PolitiFact or
GossipCop. The index files are published in the clear in the official GitHub repository,
so we fetch them **straight from GitHub**, with no authentication.

Two quirks are handled here, and both are typical of the job:

1. the CSVs contain **neither long text nor image** — only the identifier, the article URL
   and its title. The image is therefore recovered from the article's Open Graph metadata
   (see :mod:`multimodal_etl.sources.opengraph`);
2. the ``tweet_ids`` column can exceed the field size the ``csv`` module accepts by
   default: that limit has to be raised explicitly.
"""

from __future__ import annotations

import csv
import io
from pathlib import Path

import requests

from multimodal_etl.config import RAW_DIR, ExtractionConfig
from multimodal_etl.logging_setup import get_logger
from multimodal_etl.sources import opengraph

logger = get_logger(__name__)

# Cache directory: once the CSVs are downloaded, later runs are offline and strictly
# reproducible.
CACHE_DIR = RAW_DIR / "fakenewsnet"

# The tweet_ids column holds thousands of tab-separated identifiers: without this, the
# csv module raises "field larger than field limit".
csv.field_size_limit(10_000_000)


def _source_name(filename: str) -> tuple[str, str]:
    """Infer the fact-checking organisation and the label from the file name.

    ``politifact_fake.csv`` -> ``("politifact", "fake")``
    """
    stem = Path(filename).stem
    organisation, _, label = stem.partition("_")
    return organisation, label


def download_csv(filename: str, config: ExtractionConfig) -> Path | None:
    """Download a FakeNewsNet CSV from GitHub, or return the cached copy."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    destination = CACHE_DIR / filename

    if destination.exists():
        logger.info("FakeNewsNet: '%s' already cached", filename)
        return destination

    url = f"{config.fakenewsnet_base_url}/{filename}"
    logger.info("FakeNewsNet: downloading %s", url)
    try:
        response = requests.get(
            url, timeout=config.request_timeout, headers={"User-Agent": config.user_agent}
        )
        response.raise_for_status()
    except requests.RequestException as exc:
        logger.error("FakeNewsNet: download failed (%s): %s", filename, exc)
        return None

    destination.write_text(response.text, encoding="utf-8")
    logger.info("FakeNewsNet: '%s' saved (%d bytes)", filename, len(response.content))
    return destination


def read_csv(path: Path) -> list[dict[str, str]]:
    """Read a FakeNewsNet CSV into a list of dictionaries."""
    content = path.read_text(encoding="utf-8", errors="replace")
    return list(csv.DictReader(io.StringIO(content)))


def _build_record(row: dict[str, str], organisation: str, label: str) -> dict[str, object]:
    """Turn a FakeNewsNet row into a normalised raw dictionary."""
    return {
        "source": f"fakenewsnet:{organisation}",
        "source_type": "dataset",
        "access_method": "github_download",
        "title": row.get("title", ""),
        # The CSVs do not expose the article body: the title carries the text signal.
        "text": row.get("title", ""),
        "url": opengraph.normalise_url(row.get("news_url", "")),
        "image_url": "",
        "image_source": "none",
        "published_at": "",
        "language": "en",
        "label": label,
        "label_source": f"fakenewsnet:{organisation}",
    }


def fetch_fakenewsnet(config: ExtractionConfig) -> list[dict[str, object]]:
    """Load the labelled FakeNewsNet publications and recover their images.

    We take the same number of rows from each file, to keep a balance between ``real``
    and ``fake`` and between the two fact-checking organisations.
    """
    per_file = max(1, config.max_items_per_source // len(config.fakenewsnet_files))
    records: list[dict[str, object]] = []

    for filename in config.fakenewsnet_files:
        path = download_csv(filename, config)
        if path is None:
            continue

        organisation, label = _source_name(filename)
        rows = read_csv(path)[:per_file]
        records.extend(_build_record(row, organisation, label) for row in rows)
        logger.info("FakeNewsNet: %d rows read from %s", len(rows), filename)

    if not records:
        logger.warning("FakeNewsNet: no data collected.")
        return []

    # The CSVs carry no image: we go and fetch one from the publisher.
    opengraph.enrich_publications(records, config)

    logger.info("FakeNewsNet: %d labelled publications loaded", len(records))
    return records
