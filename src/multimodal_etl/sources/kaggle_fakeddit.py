"""Connector 4 — Fakeddit, a multimodal dataset hosted on Kaggle.

Fakeddit (Nakamura *et al.*, 2020) gathers more than a million Reddit publications pairing
**a title and an image**, with three levels of labels (binary, 3 classes, 6 classes). It
is the source closest to the use case: unlike FakeNewsNet, it is natively multimodal.

Downloading a Kaggle dataset requires an account and an API key. Rather than add a
dependency and one more secret to the pipeline, we do what a company does with a frozen
reference dataset: **the file is downloaded once, by hand**, then dropped into
``data/raw/kaggle/``. The connector only reads it.

When the file is absent, the connector falls back to a **versioned demonstration sample**
(``data/samples/fakeddit_sample.tsv``): made-up contents, the same column structure as the
real dataset, royalty-free images. The pipeline therefore stays runnable by anyone,
straight away.
"""

from __future__ import annotations

import csv
from pathlib import Path

from multimodal_etl.config import RAW_DIR, SAMPLES_DIR, ExtractionConfig
from multimodal_etl.logging_setup import get_logger

logger = get_logger(__name__)

KAGGLE_DIR = RAW_DIR / "kaggle"
SAMPLE_FILE = SAMPLES_DIR / "fakeddit_sample.tsv"

# Fakeddit encodes the ground truth in the 2_way_label column: 1 = genuine.
_LABELS = {"1": "real", "0": "fake"}


def pick_file() -> tuple[Path, bool] | None:
    """Choose the data source: the real Kaggle dataset if present, else the sample.

    Returns the path and a boolean saying whether this is the real dataset.
    """
    if KAGGLE_DIR.exists():
        files = sorted(KAGGLE_DIR.glob("*.tsv"))
        if files:
            logger.info("Fakeddit: Kaggle dataset detected (%s)", files[0].name)
            return files[0], True

    if SAMPLE_FILE.exists():
        logger.info("Fakeddit: Kaggle dataset absent, falling back to %s", SAMPLE_FILE.name)
        return SAMPLE_FILE, False

    return None


def read_tsv(path: Path) -> list[dict[str, str]]:
    """Read a Fakeddit file (tab-separated values)."""
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle, delimiter="\t"))


def _build_record(row: dict[str, str]) -> dict[str, object]:
    """Turn a Fakeddit row into a normalised raw dictionary."""
    title = row.get("clean_title") or row.get("title") or ""
    image_url = row.get("image_url", "").strip()
    return {
        # Fakeddit is one single source, whatever the originating subreddit: splitting by
        # subreddit would fragment the distributions into fifteen or so rows of no use for
        # monitoring.
        "source": "fakeddit",
        "source_type": "dataset",
        "access_method": "telechargement_kaggle",
        "title": title,
        # Fakeddit publishes no article body: the title is the text signal.
        "text": title,
        # Fakeddit identifies each publication by its Reddit id: we rebuild the permalink,
        # which serves as the traceability and deduplication key.
        "url": f"https://redd.it/{row.get('id', '')}",
        "image_url": image_url,
        "image_source": "native" if image_url else "aucune",
        "published_at": row.get("created_utc", ""),
        "language": "en",
        "label": _LABELS.get(row.get("2_way_label", "").strip(), "unverified"),
        "label_source": "fakeddit",
    }


def fetch_fakeddit(config: ExtractionConfig) -> list[dict[str, object]]:
    """Load the multimodal Fakeddit publications."""
    choice = pick_file()
    if choice is None:
        logger.warning(
            "Fakeddit: no data available. Drop the .tsv file into %s "
            "(the procedure is in the exploration report).",
            KAGGLE_DIR,
        )
        return []

    path, is_real = choice
    rows = read_tsv(path)

    # The real dataset keeps only the publications that are genuinely multimodal.
    with_image = [row for row in rows if row.get("image_url", "").strip()]
    kept = with_image[: config.max_items_per_source]

    records = [_build_record(row) for row in kept]
    logger.info(
        "Fakeddit: %d publications loaded from %s (%s)",
        len(records),
        path.name,
        "real Kaggle dataset" if is_real else "demonstration sample",
    )
    return records
