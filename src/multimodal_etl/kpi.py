"""Key performance indicators of the ETL pipeline.

This module computes the indicators — data **accuracy**, **speed** and **cost** — and adds
what the use case actually makes critical: how many images are really available, how fresh
the dataset is, how diverse its sources are, and what each run genuinely adds.

Every indicator is here because it triggers an action when it drifts; the dashboard
displays them and the monitoring plan sets the thresholds. Those thresholds are defined
**once**, here, in :data:`THRESHOLDS`: the document and the application therefore cannot
contradict each other.

The computing functions are pure — data in, dictionary out — which makes them simple to
test and to display.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import NamedTuple

import pandas as pd

from multimodal_etl.config import PROCESSED_DIR, RUNS_DIR


class Threshold(NamedTuple):
    """Alert threshold of an indicator, as defined in the monitoring plan."""

    label: str
    direction: str  # "higher_is_better", or "lower_is_better" for the other way round
    green: float
    amber: float
    justification: str


# Alert thresholds — the single source of truth, shared by the dashboard and the
# monitoring plan.
THRESHOLDS: dict[str, Threshold] = {
    "validity_rate_pct": Threshold(
        "Validity rate",
        "higher_is_better",
        60,
        45,
        "Set on the observed behaviour (around 65%): a rejection almost always comes from "
        "an image being unavailable, which is normal. Below 45%, a source has changed its "
        "format.",
    ),
    "text_image_pairing_pct": Threshold(
        "Text-image pairing",
        "higher_is_better",
        90,
        75,
        "This is the very definition of the dataset: without an image the publication is useless.",
    ),
    "images_downloaded_pct": Threshold(
        "Images downloaded",
        "higher_is_better",
        80,
        60,
        "Measures media availability: an announced URL is not the same as a file obtained.",
    ),
    "duplicate_rate_pct": Threshold(
        "Duplicate rate",
        "lower_is_better",
        5,
        15,
        "A climbing rate signals over-ingestion, or an identifier that has become unstable.",
    ),
    "dominant_source_share_pct": Threshold(
        "Share of the dominant source",
        "lower_is_better",
        50,
        70,
        "A dataset captured by a single source passes its bias on to the model.",
    ),
    "median_age_hours": Threshold(
        "Median age",
        "lower_is_better",
        48,
        168,
        "A fake-news detector has to see recent news, not archives.",
    ),
    "publications": Threshold(
        "Volume ingested",
        "higher_is_better",
        80,
        40,
        "A collapsing volume gives away a source that is down.",
    ),
    "total_duration_sec": Threshold(
        "Total duration",
        "lower_is_better",
        90,
        300,
        "Beyond that, the daily execution window ends up being exceeded.",
    ),
    "failed_sources": Threshold(
        "Failed sources",
        "lower_is_better",
        0,
        1,
        "Two silent sources on the same day is an incident, not a network hiccup.",
    ),
}


def _percentage(part: float, total: float) -> float:
    """Return a rounded percentage, avoiding the division by zero."""
    if total <= 0:
        return 0.0
    return round(100.0 * part / total, 1)


# --------------------------------------------------------------------------- #
# Families of indicators
# --------------------------------------------------------------------------- #
def quality_kpis(df: pd.DataFrame, stats: dict[str, int]) -> dict[str, float]:
    """Data quality: what survives the cleaning, and what is usable."""
    raw_total = stats.get("raw_total", 0)
    valid_total = len(df)
    if df.empty:
        return {
            "validity_rate_pct": 0.0,
            "text_image_pairing_pct": 0.0,
            "labelled_rate_pct": 0.0,
            "duplicate_rate_pct": 0.0,
            "dated_rate_pct": 0.0,
            "mean_text_length": 0.0,
        }

    return {
        "validity_rate_pct": _percentage(valid_total, raw_total),
        "text_image_pairing_pct": _percentage(int(df["has_image"].sum()), valid_total),
        "labelled_rate_pct": _percentage(int(df["label"].notna().sum()), valid_total),
        "duplicate_rate_pct": _percentage(stats.get("duplicates", 0), max(raw_total, 1)),
        # Without a publication date, neither the freshness nor the time-based features can
        # be computed: this is a completeness check in its own right.
        "dated_rate_pct": _percentage(int(df["published_at"].notna().sum()), valid_total),
        "mean_text_length": round(float(df["text_length"].mean()), 1),
    }


def volume_kpis(df: pd.DataFrame) -> dict[str, object]:
    """Volume and diversity: how many publications, and where they come from."""
    if df.empty:
        return {
            "publications": 0,
            "sources": 0,
            "dominant_source_share_pct": 0.0,
            "by_source": {},
            "by_language": {},
            "by_access_method": {},
        }

    distribution = df["source"].value_counts()
    return {
        "publications": len(df),
        "sources": int(df["source"].nunique()),
        # A dataset dominated by a single source inherits its editorial bias: so we watch
        # the concentration, not only the volume.
        "dominant_source_share_pct": _percentage(int(distribution.iloc[0]), len(df)),
        "by_source": distribution.to_dict(),
        "by_language": df["language"].value_counts().to_dict(),
        "by_access_method": df["access_method"].value_counts().to_dict(),
    }


def freshness_kpis(df: pd.DataFrame, now: datetime | None = None) -> dict[str, float]:
    """Freshness: how old are the publications we have just ingested."""
    empty = {"median_age_hours": 0.0, "under_24h_pct": 0.0, "dated_publications": 0}
    if df.empty or "published_at" not in df.columns:
        return empty

    dates = pd.to_datetime(df["published_at"], errors="coerce", utc=True, format="mixed").dropna()
    if dates.empty:
        return empty

    reference = now or datetime.now(UTC)
    ages_hours = (pd.Timestamp(reference) - dates).dt.total_seconds() / 3600

    return {
        "median_age_hours": round(float(ages_hours.median()), 1),
        "under_24h_pct": _percentage(int((ages_hours <= 24).sum()), len(ages_hours)),
        "dated_publications": len(ages_hours),
    }


def performance_kpis(run: dict[str, object]) -> dict[str, float]:
    """Speed, cost and reliability of the run."""
    durations = run.get("durations_sec", {}) if run else {}
    total_duration = round(sum(float(value) for value in durations.values()), 2)
    loaded = int(run.get("rows_loaded", 0)) if run else 0
    extracted = int(run.get("rows_extracted", 0)) if run else 0
    images = run.get("images", {}) if run else {}

    return {
        "extract_duration_sec": round(float(durations.get("extract", 0.0)), 2),
        "transform_duration_sec": round(float(durations.get("transform", 0.0)), 2),
        "load_duration_sec": round(float(durations.get("load", 0.0)), 2),
        "total_duration_sec": total_duration,
        "publications_per_sec": (round(extracted / total_duration, 1) if total_duration else 0.0),
        # Cost: API calls spent from the quota, and disk taken up by the images.
        "api_calls_spent": int(run.get("api_calls", 0)) if run else 0,
        "image_weight_mb": round(float(images.get("bytes", 0)) / (1024 * 1024), 2),
        "images_downloaded_pct": _percentage(
            float(images.get("succeeded", 0)), float(images.get("attempted", 0))
        ),
        # Share of this run's publications that are genuinely new in the database: this is
        # what a daily run really adds to the dataset.
        "new_rate_pct": _percentage(loaded, extracted),
        "publications_added": loaded,
        "publications_in_db": int(run.get("rows_in_db", 0)) if run else 0,
        "failed_sources": int(run.get("failed_sources", 0)) if run else 0,
    }


def compute_kpis(
    df: pd.DataFrame, stats: dict[str, int], run: dict[str, object]
) -> dict[str, object]:
    """Aggregate the four families of indicators into a single dictionary."""
    return {
        "quality": quality_kpis(df, stats),
        "volume": volume_kpis(df),
        "freshness": freshness_kpis(df),
        "performance": performance_kpis(run),
    }


# --------------------------------------------------------------------------- #
# Checking against the monitoring plan's thresholds
# --------------------------------------------------------------------------- #
def status_for(indicator: str, value: float) -> str:
    """Classify a value as 'green', 'amber' or 'red' against its threshold."""
    threshold = THRESHOLDS[indicator]
    if threshold.direction == "higher_is_better":
        if value >= threshold.green:
            return "green"
        return "amber" if value >= threshold.amber else "red"

    if value <= threshold.green:
        return "green"
    return "amber" if value <= threshold.amber else "red"


def evaluate_thresholds(kpis: dict[str, object]) -> list[dict[str, object]]:
    """Check every monitored indicator against its threshold and return its status."""
    values: dict[str, float] = {}
    for family in kpis.values():
        for name, value in family.items():
            if name in THRESHOLDS and isinstance(value, int | float):
                values[name] = float(value)

    return [
        {
            "indicator": name,
            "label": THRESHOLDS[name].label,
            "value": value,
            "status": status_for(name, value),
            "expected": (
                f"≥ {THRESHOLDS[name].green:g}"
                if THRESHOLDS[name].direction == "higher_is_better"
                else f"≤ {THRESHOLDS[name].green:g}"
            ),
            "justification": THRESHOLDS[name].justification,
        }
        for name, value in values.items()
    ]


# --------------------------------------------------------------------------- #
# Loading the artefacts the pipeline produced
# --------------------------------------------------------------------------- #
def _available_datasets() -> list[Path]:
    """List the exported datasets, most recent first."""
    files = list(PROCESSED_DIR.glob("publications_*.parquet"))
    files += list(PROCESSED_DIR.glob("publications_*.csv"))
    return sorted(files, key=lambda p: (p.stat().st_mtime, p.name), reverse=True)


def _read_dataset(path: Path) -> pd.DataFrame:
    """Read an exported dataset, whatever its format."""
    return pd.read_parquet(path) if path.suffix == ".parquet" else pd.read_csv(path)


def load_latest_dataset() -> tuple[pd.DataFrame, dict[str, int], dict[str, object]]:
    """Load the most recent dataset **together with its statistics**.

    The statistics are written next to the dataset by the transform step. So we keep the
    most recent dataset that has its own: showing a dataset without its statistics would
    produce wrong indicators — a validity rate of 0%, for instance.
    """
    for path in _available_datasets():
        stats_path = path.with_name(path.stem + "_stats.json")
        if not stats_path.exists():
            continue
        df = _read_dataset(path)
        stats = json.loads(stats_path.read_text(encoding="utf-8"))
        return df, stats, latest_run()

    return pd.DataFrame(), {}, {}


def _run_records() -> list[Path]:
    """List the run records, most recent first."""
    if not RUNS_DIR.exists():
        return []
    return sorted(
        RUNS_DIR.glob("run_*.json"), key=lambda p: (p.stat().st_mtime, p.name), reverse=True
    )


def latest_run() -> dict[str, object]:
    """Return the record of the pipeline's last run."""
    records = _run_records()
    if not records:
        return {}
    return json.loads(records[0].read_text(encoding="utf-8"))


def run_history() -> pd.DataFrame:
    """Gather every past run into one chronological table.

    This is what lets us look at a trend rather than a snapshot: a validity rate of 80%
    does not read the same way depending on whether it is climbing or falling.
    """
    rows = []
    for record in reversed(_run_records()):
        run = json.loads(record.read_text(encoding="utf-8"))
        stats = run.get("stats", {})
        durations = run.get("durations_sec", {})
        rows.append(
            {
                "date": run.get("run_at", ""),
                "orchestrator": run.get("orchestrator", "script"),
                "publications_extracted": run.get("rows_extracted", 0),
                "publications_added": run.get("rows_loaded", 0),
                "publications_in_db": run.get("rows_in_db", 0),
                "total_duration_sec": round(sum(float(v) for v in durations.values()), 2),
                "validity_rate_pct": _percentage(
                    stats.get("valid_total", 0), stats.get("raw_total", 0)
                ),
                "failed_sources": run.get("failed_sources", 0),
            }
        )

    if not rows:
        return pd.DataFrame()

    history = pd.DataFrame(rows)
    history["date"] = pd.to_datetime(history["date"], errors="coerce", utc=True)
    return history
