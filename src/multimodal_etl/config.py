"""Central configuration of the pipeline.

Every path and every adjustable parameter lives here, as ``frozen`` (immutable)
dataclasses. The scripts, the notebooks and the Airflow DAG import these objects rather
than hard-coding constants: that is what makes the pipeline **reproducible** and
**tunable**.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

# Project root = two levels above this file (src/multimodal_etl/config.py).
PROJECT_ROOT: Path = Path(__file__).resolve().parents[2]

DATA_DIR: Path = PROJECT_ROOT / "data"
RAW_DIR: Path = DATA_DIR / "raw"
IMAGES_DIR: Path = RAW_DIR / "images"
PROCESSED_DIR: Path = DATA_DIR / "processed"
# One record per pipeline run: this is the history the dashboard reads.
RUNS_DIR: Path = PROCESSED_DIR / "runs"
SAMPLES_DIR: Path = DATA_DIR / "samples"
DB_DIR: Path = DATA_DIR / "db"
LOGS_DIR: Path = PROJECT_ROOT / "logs"

# Working area: files handed from one Airflow task to the next. See transit.py.
INTERIM_DIR: Path = DATA_DIR / "interim"


def relative_path(path: Path) -> str:
    """Express a path relative to the project root.

    Paths stored in the dataset have to stay valid somewhere other than the machine that
    produced them: the pipeline runs locally as well as inside the Airflow container,
    where the project root sits elsewhere. So we record ``data/raw/images/xxx.jpg`` and
    never an absolute path.
    """
    try:
        return path.resolve().relative_to(PROJECT_ROOT).as_posix()
    except ValueError:
        # Path outside the project: keep it as it is rather than lose it.
        return path.as_posix()


def absolute_path(path: str) -> Path:
    """Find the real file back from a project-relative path."""
    candidate = Path(path)
    return candidate if candidate.is_absolute() else PROJECT_ROOT / candidate


def _env_int(name: str, default: int) -> int:
    """Read an integer environment variable, falling back to a default."""
    raw = os.environ.get(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        return int(raw)
    except ValueError:
        return default


@dataclass(frozen=True)
class ExtractionConfig:
    """Parameters of the extract step (E)."""

    # Largest number of items collected per source (a guard against API quotas).
    max_items_per_source: int = field(
        default_factory=lambda: _env_int("MULTIMODAL_ETL_MAX_ITEMS_PER_SOURCE", 50)
    )
    # Timeout, in seconds, for every network request.
    request_timeout: int = field(
        default_factory=lambda: _env_int("MULTIMODAL_ETL_REQUEST_TIMEOUT", 15)
    )
    # User-Agent header: the minimum courtesy owed to the servers being queried.
    user_agent: str = "Multimodal ETL-bot/0.1 (+https://github.com/multimodal_etl)"
    # Multimodal RSS feeds (title + summary + image) — official sources, no key needed.
    rss_feeds: tuple[tuple[str, str], ...] = (
        ("the_guardian", "https://www.theguardian.com/world/rss"),
        ("bbc_news", "https://feeds.bbci.co.uk/news/world/rss.xml"),
        ("abc_news", "https://abcnews.go.com/abcnews/internationalheadlines"),
    )
    # NewsData.io API settings (the source turns on when a key is supplied).
    newsdata_endpoint: str = "https://newsdata.io/api/1/news"
    newsdata_language: str = "en"
    # FakeNewsNet: labelled CSVs published on the official GitHub repository.
    fakenewsnet_base_url: str = (
        "https://raw.githubusercontent.com/KaiDMML/FakeNewsNet/master/dataset"
    )
    fakenewsnet_files: tuple[str, ...] = (
        "politifact_fake.csv",
        "politifact_real.csv",
        "gossipcop_fake.csv",
        "gossipcop_real.csv",
    )
    # Those CSVs carry no image, so we go and fetch one from the article's Open Graph
    # metadata. That costs one HTTP request per publication, hence the cap: it keeps a
    # run short.
    max_open_graph_enrichments: int = field(
        default_factory=lambda: _env_int("MULTIMODAL_ETL_MAX_OPEN_GRAPH", 40)
    )


@dataclass(frozen=True)
class ImageConfig:
    """Parameters of the image download (the "vision" half of the multimodal data)."""

    # Largest number of images downloaded per run (keeps time and disk under control).
    # The cap has to stay above the collected volume — roughly 180 publications with the
    # default settings — otherwise the sources processed last get no image at all and
    # drop out of the dataset.
    max_images: int = field(default_factory=lambda: _env_int("MULTIMODAL_ETL_MAX_IMAGES", 250))
    # Timeout, in seconds, of a single image download.
    request_timeout: int = field(
        default_factory=lambda: _env_int("MULTIMODAL_ETL_REQUEST_TIMEOUT", 15)
    )
    # Largest accepted size for an image file, in megabytes.
    max_size_mb: float = 5.0
    # Accepted MIME types (checked before anything is written to disk).
    accepted_mime_types: tuple[str, ...] = ("image/jpeg", "image/png", "image/webp", "image/gif")
    user_agent: str = "Multimodal ETL-bot/0.1 (+https://github.com/multimodal_etl)"


@dataclass(frozen=True)
class TransformConfig:
    """Parameters of the transform step (T)."""

    # Shortest text, in characters, for a publication to be usable.
    min_text_length: int = 30
    # When True, a publication with no downloaded image is dropped (strict multimodal).
    require_image: bool = True
    # Export format of the transformed dataset.
    output_format: str = "parquet"  # "parquet" or "csv"


@dataclass(frozen=True)
class LoadConfig:
    """Parameters of the load step (L)."""

    # SQLAlchemy URL of the target database. Empty -> local SQLite
    # (data/db/multimodal_etl.db).
    db_url: str = field(default_factory=lambda: os.environ.get("MULTIMODAL_ETL_DB_URL", "").strip())
    # The flat table, ready for model training.
    table_name: str = "publications"

    @property
    def resolved_url(self) -> str:
        """Return the connection URL actually in use (local SQLite by default)."""
        if self.db_url:
            return self.db_url
        return f"sqlite:///{(DB_DIR / 'multimodal_etl.db').as_posix()}"


def ensure_dirs() -> None:
    """Create the working directories if they do not exist yet."""
    for directory in (
        RAW_DIR,
        IMAGES_DIR,
        PROCESSED_DIR,
        RUNS_DIR,
        SAMPLES_DIR,
        DB_DIR,
        LOGS_DIR,
        INTERIM_DIR,
    ):
        directory.mkdir(parents=True, exist_ok=True)
