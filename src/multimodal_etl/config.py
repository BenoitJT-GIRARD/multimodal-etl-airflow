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

from multimodal_etl.utils.paths import ROOT_DIR, VAR_DIR

# The root is FOUND, in one place, by `utils.paths`. Counting directories up from this file
# works from a checkout and writes into site-packages from a wheel, and the Airflow container
# mounts the project somewhere else again.
PROJECT_ROOT: Path = ROOT_DIR

def _env_path(name: str, default: Path) -> Path:
    """Read a directory from the environment, resolved against the project root if relative."""
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    candidate = Path(raw).expanduser()
    return candidate if candidate.is_absolute() else PROJECT_ROOT / candidate


# Where a run reads and writes. The default is `data/` beside the code; the Airflow container
# mounts something else, and a test that runs the pipeline for real needs a directory of its
# own, away from the one the reader's own runs have filled.
DATA_DIR: Path = _env_path("MULTIMODAL_ETL_DATA_DIR", PROJECT_ROOT / "data")
RAW_DIR: Path = DATA_DIR / "raw"
IMAGES_DIR: Path = RAW_DIR / "images"
PROCESSED_DIR: Path = DATA_DIR / "processed"
# One record per pipeline run: this is the history the dashboard reads.
RUNS_DIR: Path = PROCESSED_DIR / "runs"
# A committed INPUT, and not somewhere a run writes: the Fakeddit demonstration sample is
# versioned with the code. Hanging it off DATA_DIR sent a run with MULTIMODAL_ETL_DATA_DIR
# set looking for it in an empty directory, and the source reported nothing to collect.
SAMPLES_DIR: Path = PROJECT_ROOT / "data" / "samples"
DB_DIR: Path = DATA_DIR / "db"
# Under `var/`, the one root directory the vocabulary reserves for what a run leaves behind and
# no reader is meant to open. A `logs/` at the root sat beside `src/` and `docs/` as if it were
# something to read.
LOGS_DIR: Path = VAR_DIR / "logs"

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
        # Path outside the project: keep it as it is, and lose nothing.
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


#: The four connectors, in the order :mod:`multimodal_etl.extract` runs them.
SOURCE_NAMES: tuple[str, ...] = ("rss", "newsdata", "fakenewsnet", "kaggle_fakeddit")

DEFAULT_RSS_FEEDS: tuple[tuple[str, str], ...] = (
    ("the_guardian", "https://www.theguardian.com/world/rss"),
    ("bbc_news", "https://feeds.bbci.co.uk/news/world/rss.xml"),
    ("abc_news", "https://abcnews.go.com/abcnews/internationalheadlines"),
)


def _env_sources(name: str) -> tuple[str, ...]:
    """Which connectors to run, as a comma-separated list. Empty means all four.

    Replaying one source is a normal operation: a feed came back after an outage and the
    other three have nothing to add. Doing it used to mean editing the connector table.
    """
    raw = os.environ.get(name, "").strip()
    if not raw:
        return SOURCE_NAMES
    wanted = [piece.strip() for piece in raw.split(",") if piece.strip()]
    unknown = [piece for piece in wanted if piece not in SOURCE_NAMES]
    if unknown:
        raise ValueError(
            f"{name}: unknown source(s) {', '.join(unknown)}. "
            f"Known sources: {', '.join(SOURCE_NAMES)}."
        )
    return tuple(wanted)


def _env_feeds(name: str, default: tuple[tuple[str, str], ...]) -> tuple[tuple[str, str], ...]:
    """Read `name=url,name=url` from the environment, falling back to the shipped feeds."""
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    feeds: list[tuple[str, str]] = []
    for piece in raw.split(","):
        label, separator, url = piece.partition("=")
        if not separator or not url.strip():
            raise ValueError(f"{name}: expected `label=url`, got {piece.strip()!r}.")
        feeds.append((label.strip(), url.strip()))
    return tuple(feeds)


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
    # Which connectors run. All four by default; a comma-separated list replays a subset.
    enabled_sources: tuple[str, ...] = field(
        default_factory=lambda: _env_sources("MULTIMODAL_ETL_SOURCES")
    )
    # Multimodal RSS feeds (title + summary + image) — official sources, no key needed.
    # `MULTIMODAL_ETL_RSS_FEEDS=label=url,label=url` points the connector somewhere else.
    rss_feeds: tuple[tuple[str, str], ...] = field(
        default_factory=lambda: _env_feeds("MULTIMODAL_ETL_RSS_FEEDS", DEFAULT_RSS_FEEDS)
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
    # SAMPLES_DIR is deliberately absent. Creating a directory is a decision to write in it,
    # and the sample is read: if it is gone, the run has to break where it is expected.
    for directory in (
        RAW_DIR,
        IMAGES_DIR,
        PROCESSED_DIR,
        RUNS_DIR,
        DB_DIR,
        LOGS_DIR,
        INTERIM_DIR,
    ):
        directory.mkdir(parents=True, exist_ok=True)
