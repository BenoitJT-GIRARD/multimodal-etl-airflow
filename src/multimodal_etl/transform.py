"""Step T — transform (cleaning, validation, normalisation).

A reproducible, logged pipeline turning the raw publications into a clean, structured
dataset that conforms to :mod:`multimodal_etl.schema`. It is laid out in three explicit
movements — **read**, **process**, **export** — and broken into small functions
(``clean_text``, ``validate_image``, ...) so that every transformation stays readable,
testable and traced in the logs.
"""

from __future__ import annotations

import html
import json
import re
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd
import tldextract
from bs4 import BeautifulSoup

from multimodal_etl.config import PROCESSED_DIR, TransformConfig, absolute_path, ensure_dirs
from multimodal_etl.logging_setup import get_logger
from multimodal_etl.schema import COLUMNS, Publication, generate_id, generate_source_id

logger = get_logger(__name__)

_WHITESPACE = re.compile(r"\s+")
# A Unix timestamp, integer or float: '1425138660' as well as '1425138660.0'.
_IS_TIMESTAMP = re.compile(r"\d{9,11}(\.\d+)?")


# --------------------------------------------------------------------------- #
# Single-purpose transformation functions
# --------------------------------------------------------------------------- #
def clean_text(text: str) -> str:
    """Clean a text: strip the HTML, decode the entities, normalise the whitespace."""
    if not text:
        return ""
    without_html = BeautifulSoup(text, "lxml").get_text(separator=" ")
    decoded = html.unescape(without_html)
    return _WHITESPACE.sub(" ", decoded).strip()


def validate_image(image_path: str) -> bool:
    """Check that the announced image file really exists on disk.

    This is the check that **guarantees the text-image pairing**: the extract step has
    already downloaded and validated the image with Pillow; here we verify the file is
    still there at the moment the dataset gets built. The path is relative to the project
    root, so we resolve it before testing.
    """
    if not image_path:
        return False
    return absolute_path(image_path).is_file()


def extract_domain(url: str) -> str:
    """Pull the registered domain name out of a URL (a reliability signal)."""
    if not url:
        return ""
    extracted = tldextract.extract(url)
    return extracted.registered_domain or extracted.domain or ""


def normalise_label(label: object) -> str | None:
    """Harmonise the ground-truth label: 'real', 'fake' or None."""
    if not label:
        return None
    value = str(label).strip().lower()
    if value in {"real", "true", "vrai"}:
        return "real"
    if value in {"fake", "false", "faux"}:
        return "fake"
    return "unverified"


def normalise_language(language: object) -> str:
    """Bring a language back to its two-letter ISO 639-1 code.

    The sources do not agree: RSS declares ``en``, NewsData.io returns ``english``, others
    use ``en-GB``. Without harmonising, a filter by language would let half the
    English-language publications through.
    """
    value = str(language or "").strip().lower()
    if not value:
        return "en"

    names = {"english": "en", "french": "fr", "francais": "fr", "spanish": "es", "german": "de"}
    if value in names:
        return names[value]
    # Regional variants: 'en-gb' and 'en_us' name the same language.
    return value.replace("_", "-").split("-")[0][:2]


def normalise_date(raw_date: object) -> str | None:
    """Convert a publication date into an ISO 8601 string, or None when unreadable.

    The sources do not share a format — RFC 822 for RSS, ISO for the APIs, a Unix
    timestamp for some datasets — so everything is brought to the same one, without which
    the freshness KPI could not be computed.
    """
    if not raw_date:
        return None
    text = str(raw_date).strip()
    if not text:
        return None

    # Unix timestamp: Fakeddit exposes a numeric created_utc, sometimes written as a
    # float ('1425138660.0').
    if _IS_TIMESTAMP.fullmatch(text):
        try:
            return datetime.fromtimestamp(float(text), tz=UTC).isoformat(timespec="seconds")
        except (ValueError, OSError, OverflowError):
            return None

    timestamp = pd.to_datetime(text, errors="coerce", utc=True, format="mixed")
    if pd.isna(timestamp):
        return None
    return timestamp.isoformat(timespec="seconds")


# --------------------------------------------------------------------------- #
# Building one normalised publication
# --------------------------------------------------------------------------- #
def build_publication(
    raw: dict[str, object], config: TransformConfig, ingested_at: str
) -> Publication | None:
    """Turn a raw record into a :class:`Publication`, or None when it is invalid.

    A publication is dropped when: the title is empty, the text is too short, or — in
    strict multimodal mode — there is no image file. That is what guarantees the
    text-image pairing the use case expects.
    """
    title = clean_text(str(raw.get("title", "")))
    text = clean_text(str(raw.get("text", "")))
    url = str(raw.get("url", "")).strip()
    image_url = str(raw.get("image_url", "")).strip()
    image_path = str(raw.get("image_path", "")).strip()

    if not title:
        return None
    if len(text) < config.min_text_length:
        return None

    has_image = validate_image(image_path)
    if config.require_image and not has_image:
        return None

    source = str(raw.get("source", "inconnu"))
    return Publication(
        id=generate_id(url, title),
        source_id=generate_source_id(source),
        source=source,
        source_type=str(raw.get("source_type", "inconnu")),
        access_method=str(raw.get("access_method", "inconnu")),
        domain=extract_domain(url),
        title=title,
        text=text,
        text_length=len(text),
        image_url=image_url,
        image_path=image_path if has_image else "",
        image_source=str(raw.get("image_source", "aucune")) if has_image else "aucune",
        has_image=has_image,
        url=url,
        language=normalise_language(raw.get("language")),
        ingested_at=ingested_at,
        published_at=normalise_date(raw.get("published_at")),
        label=normalise_label(raw.get("label")),
        label_source=(str(raw.get("label_source")) if raw.get("label_source") else None),
    )


# --------------------------------------------------------------------------- #
# Pipeline: read -> process -> export
# --------------------------------------------------------------------------- #
def read_raw(path: Path) -> list[dict[str, object]]:
    """Step 1 — read: load the raw publications from a JSON file."""
    logger.info("Transform: reading raw file %s", path)
    with path.open("r", encoding="utf-8") as handle:
        records = json.load(handle)
    logger.info("Transform: %d raw publications read", len(records))
    return records


def process(
    records: list[dict[str, object]], config: TransformConfig
) -> tuple[pd.DataFrame, dict[str, int]]:
    """Step 2 — process: clean, validate, normalise, deduplicate.

    Returns the final DataFrame together with a dictionary of statistics, used by the KPIs
    and the monitoring.
    """
    ingested_at = datetime.now(UTC).isoformat(timespec="seconds")
    raw_total = len(records)

    publications = [build_publication(raw, config, ingested_at) for raw in records]
    valid = [pub for pub in publications if pub is not None]
    logger.info("Transform: %d/%d publications valid after cleaning", len(valid), raw_total)

    rows = [pub.to_row() for pub in valid]
    df = pd.DataFrame(rows, columns=list(COLUMNS))

    before_dedup = len(df)
    df = df.drop_duplicates(subset="id").reset_index(drop=True)
    logger.info("Transform: %d duplicates removed", before_dedup - len(df))

    stats = {
        "total_brut": raw_total,
        "total_valide": len(df),
        "rejetes": int(raw_total - len(valid)),
        "doublons": int(before_dedup - len(df)),
        "avec_image": int(df["has_image"].sum()) if not df.empty else 0,
        "labellisees": int(df["label"].notna().sum()) if not df.empty else 0,
        "images_natives": int((df["image_source"] == "native").sum()) if not df.empty else 0,
        "images_open_graph": int((df["image_source"] == "open_graph").sum()) if not df.empty else 0,
    }
    return df, stats


def export_dataset(
    df: pd.DataFrame,
    config: TransformConfig,
    stats: dict[str, int] | None = None,
    path: Path | None = None,
) -> Path:
    """Step 3 — export: write the clean dataset and its statistics.

    The statistics are always written next to the dataset, under the same name: the
    dashboard always loads the pair, never an orphan dataset.
    """
    ensure_dirs()
    timestamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
    extension = "parquet" if config.output_format == "parquet" else "csv"
    path = path or PROCESSED_DIR / f"publications_{timestamp}.{extension}"

    if extension == "parquet":
        df.to_parquet(path, index=False)
    else:
        df.to_csv(path, index=False, encoding="utf-8")
    logger.info("Transform: dataset of %d rows exported to %s", len(df), path)

    stats_path = path.with_name(path.stem + "_stats.json")
    with stats_path.open("w", encoding="utf-8") as handle:
        json.dump(stats or {}, handle, ensure_ascii=False, indent=2)
    logger.info("Transform: statistics written to %s", stats_path)
    return path


def run_transformation(
    raw_path: Path,
    config: TransformConfig | None = None,
    output_path: Path | None = None,
) -> tuple[Path, dict[str, int]]:
    """The whole transform pipeline: read -> process -> export.

    Returns the path of the transformed dataset and the statistics of the run.
    """
    config = config or TransformConfig()
    records = read_raw(raw_path)
    df, stats = process(records, config)
    output = export_dataset(df, config, stats, output_path)
    return output, stats
