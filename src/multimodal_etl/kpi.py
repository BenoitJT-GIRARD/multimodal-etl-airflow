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

    libelle: str
    sens: str  # "haut": the bigger the better; "bas": the other way round
    vert: float
    orange: float
    justification: str


# Alert thresholds — the single source of truth, shared by the dashboard and the
# monitoring plan.
THRESHOLDS: dict[str, Threshold] = {
    "taux_validite_pct": Threshold(
        "Validity rate",
        "haut",
        60,
        45,
        "Set on the observed behaviour (around 65%): a rejection almost always comes from "
        "an image being unavailable, which is normal. Below 45%, a source has changed its "
        "format.",
    ),
    "taux_association_texte_image_pct": Threshold(
        "Text-image pairing",
        "haut",
        90,
        75,
        "This is the very definition of the dataset: without an image the publication is useless.",
    ),
    "taux_images_telechargees_pct": Threshold(
        "Images downloaded",
        "haut",
        80,
        60,
        "Measures media availability: an announced URL is not the same as a file obtained.",
    ),
    "taux_doublons_pct": Threshold(
        "Duplicate rate",
        "bas",
        5,
        15,
        "A climbing rate signals over-ingestion, or an identifier that has become unstable.",
    ),
    "part_source_dominante_pct": Threshold(
        "Share of the dominant source",
        "bas",
        50,
        70,
        "A dataset captured by a single source passes its bias on to the model.",
    ),
    "age_median_heures": Threshold(
        "Median age",
        "bas",
        48,
        168,
        "A fake-news detector has to see recent news, not archives.",
    ),
    "nb_publications": Threshold(
        "Volume ingested",
        "haut",
        80,
        40,
        "A collapsing volume gives away a source that is down.",
    ),
    "duree_totale_sec": Threshold(
        "Total duration",
        "bas",
        90,
        300,
        "Beyond that, the daily execution window ends up being exceeded.",
    ),
    "failed_sources": Threshold(
        "Failed sources",
        "bas",
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
    raw_total = stats.get("total_brut", 0)
    valid_total = len(df)
    if df.empty:
        return {
            "taux_validite_pct": 0.0,
            "taux_association_texte_image_pct": 0.0,
            "taux_labellise_pct": 0.0,
            "taux_doublons_pct": 0.0,
            "taux_date_connue_pct": 0.0,
            "longueur_texte_moyenne": 0.0,
        }

    return {
        "taux_validite_pct": _percentage(valid_total, raw_total),
        "taux_association_texte_image_pct": _percentage(int(df["has_image"].sum()), valid_total),
        "taux_labellise_pct": _percentage(int(df["label"].notna().sum()), valid_total),
        "taux_doublons_pct": _percentage(stats.get("doublons", 0), max(raw_total, 1)),
        # Without a publication date, neither the freshness nor the time-based features can
        # be computed: this is a completeness check in its own right.
        "taux_date_connue_pct": _percentage(int(df["published_at"].notna().sum()), valid_total),
        "longueur_texte_moyenne": round(float(df["text_length"].mean()), 1),
    }


def volume_kpis(df: pd.DataFrame) -> dict[str, object]:
    """Volume and diversity: how many publications, and where they come from."""
    if df.empty:
        return {
            "nb_publications": 0,
            "nb_sources": 0,
            "part_source_dominante_pct": 0.0,
            "repartition_sources": {},
            "repartition_langues": {},
            "repartition_methodes_acces": {},
        }

    distribution = df["source"].value_counts()
    return {
        "nb_publications": len(df),
        "nb_sources": int(df["source"].nunique()),
        # A dataset dominated by a single source inherits its editorial bias: so we watch
        # the concentration, not only the volume.
        "part_source_dominante_pct": _percentage(int(distribution.iloc[0]), len(df)),
        "repartition_sources": distribution.to_dict(),
        "repartition_langues": df["language"].value_counts().to_dict(),
        "repartition_methodes_acces": df["access_method"].value_counts().to_dict(),
    }


def freshness_kpis(df: pd.DataFrame, now: datetime | None = None) -> dict[str, float]:
    """Freshness: how old are the publications we have just ingested."""
    empty = {"age_median_heures": 0.0, "part_moins_24h_pct": 0.0, "publications_datees": 0}
    if df.empty or "published_at" not in df.columns:
        return empty

    dates = pd.to_datetime(df["published_at"], errors="coerce", utc=True, format="mixed").dropna()
    if dates.empty:
        return empty

    reference = now or datetime.now(UTC)
    ages_hours = (pd.Timestamp(reference) - dates).dt.total_seconds() / 3600

    return {
        "age_median_heures": round(float(ages_hours.median()), 1),
        "part_moins_24h_pct": _percentage(int((ages_hours <= 24).sum()), len(ages_hours)),
        "publications_datees": len(ages_hours),
    }


def performance_kpis(run: dict[str, object]) -> dict[str, float]:
    """Speed, cost and reliability of the run."""
    durations = run.get("durations_sec", {}) if run else {}
    total_duration = round(sum(float(value) for value in durations.values()), 2)
    loaded = int(run.get("rows_loaded", 0)) if run else 0
    extracted = int(run.get("rows_extracted", 0)) if run else 0
    images = run.get("images", {}) if run else {}

    return {
        "duree_extraction_sec": round(float(durations.get("extract", 0.0)), 2),
        "duree_transformation_sec": round(float(durations.get("transform", 0.0)), 2),
        "duree_chargement_sec": round(float(durations.get("load", 0.0)), 2),
        "duree_totale_sec": total_duration,
        "debit_publications_par_sec": (
            round(extracted / total_duration, 1) if total_duration else 0.0
        ),
        # Cost: API calls spent from the quota, and disk taken up by the images.
        "appels_api_consommes": int(run.get("api_calls", 0)) if run else 0,
        "poids_images_mo": round(float(images.get("octets", 0)) / (1024 * 1024), 2),
        "taux_images_telechargees_pct": _percentage(
            float(images.get("reussies", 0)), float(images.get("tentees", 0))
        ),
        # Share of this run's publications that are genuinely new in the database: this is
        # what a daily run really adds to the dataset.
        "taux_nouveaute_pct": _percentage(loaded, extracted),
        "publications_ajoutees": loaded,
        "publications_en_base": int(run.get("rows_in_db", 0)) if run else 0,
        "failed_sources": int(run.get("failed_sources", 0)) if run else 0,
    }


def compute_kpis(
    df: pd.DataFrame, stats: dict[str, int], run: dict[str, object]
) -> dict[str, object]:
    """Aggregate the four families of indicators into a single dictionary."""
    return {
        "qualite": quality_kpis(df, stats),
        "volume": volume_kpis(df),
        "fraicheur": freshness_kpis(df),
        "performance": performance_kpis(run),
    }


# --------------------------------------------------------------------------- #
# Checking against the monitoring plan's thresholds
# --------------------------------------------------------------------------- #
def status_for(indicator: str, value: float) -> str:
    """Classify a value as 'vert', 'orange' or 'rouge' against its threshold."""
    threshold = THRESHOLDS[indicator]
    if threshold.sens == "haut":
        if value >= threshold.vert:
            return "vert"
        return "orange" if value >= threshold.orange else "rouge"

    if value <= threshold.vert:
        return "vert"
    return "orange" if value <= threshold.orange else "rouge"


def evaluate_thresholds(kpis: dict[str, object]) -> list[dict[str, object]]:
    """Check every monitored indicator against its threshold and return its status."""
    values: dict[str, float] = {}
    for family in kpis.values():
        for name, value in family.items():
            if name in THRESHOLDS and isinstance(value, int | float):
                values[name] = float(value)

    return [
        {
            "indicateur": name,
            "libelle": THRESHOLDS[name].libelle,
            "valeur": value,
            "statut": status_for(name, value),
            "attendu": (
                f"≥ {THRESHOLDS[name].vert:g}"
                if THRESHOLDS[name].sens == "haut"
                else f"≤ {THRESHOLDS[name].vert:g}"
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
                "orchestrateur": run.get("orchestrateur", "script"),
                "publications_extraites": run.get("rows_extracted", 0),
                "publications_ajoutees": run.get("rows_loaded", 0),
                "publications_en_base": run.get("rows_in_db", 0),
                "duree_totale_sec": round(sum(float(v) for v in durations.values()), 2),
                "taux_validite_pct": _percentage(
                    stats.get("total_valide", 0), stats.get("total_brut", 0)
                ),
                "failed_sources": run.get("failed_sources", 0),
            }
        )

    if not rows:
        return pd.DataFrame()

    history = pd.DataFrame(rows)
    history["date"] = pd.to_datetime(history["date"], errors="coerce", utc=True)
    return history
