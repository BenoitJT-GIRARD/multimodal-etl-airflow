"""Unit tests of the KPI computation."""

from __future__ import annotations

from datetime import UTC, datetime

import pandas as pd

from multimodal_etl.kpi import (
    THRESHOLDS,
    compute_kpis,
    evaluate_thresholds,
    freshness_kpis,
    performance_kpis,
    quality_kpis,
    status_for,
    volume_kpis,
)


def _sample_df() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "source": ["rss:bbc", "rss:bbc", "newsdata", "fakeddit:news"],
            "access_method": ["rss_feed", "rss_feed", "rest_api", "kaggle_download"],
            "language": ["en", "en", "en", "en"],
            "has_image": [True, True, False, True],
            "label": [None, None, None, "fake"],
            "text_length": [100, 200, 150, 50],
            "published_at": [
                "2026-08-20T08:00:00+00:00",
                "2026-08-19T08:00:00+00:00",
                "2026-08-10T08:00:00+00:00",
                None,
            ],
        }
    )


def _sample_run() -> dict:
    return {
        "durations_sec": {"extract": 1.0, "transform": 0.5, "load": 0.5},
        "rows_extracted": 5,
        "rows_loaded": 4,
        "rows_in_db": 40,
        "api_calls": 1,
        "failed_sources": 0,
        "images": {"attempted": 5, "succeeded": 4, "bytes": 2 * 1024 * 1024},
    }


# --------------------------------------------------------------------------- #
# Qualité
# --------------------------------------------------------------------------- #
def test_quality_kpis() -> None:
    quality = quality_kpis(_sample_df(), {"raw_total": 5, "duplicates": 1})

    assert quality["validity_rate_pct"] == 80.0  # 4 valid out of 5 collected
    assert quality["text_image_pairing_pct"] == 75.0  # 3 images / 4
    assert quality["labelled_rate_pct"] == 25.0  # 1 label / 4
    assert quality["dated_rate_pct"] == 75.0  # 3 known dates out of 4


def test_quality_kpis_on_an_empty_dataset() -> None:
    quality = quality_kpis(pd.DataFrame(), {})
    assert quality["validity_rate_pct"] == 0.0


# --------------------------------------------------------------------------- #
# Volume et diversité
# --------------------------------------------------------------------------- #
def test_volume_kpis_measure_the_concentration() -> None:
    volume = volume_kpis(_sample_df())

    assert volume["publications"] == 4
    assert volume["sources"] == 3
    # Two publications out of four come from the same source.
    assert volume["dominant_source_share_pct"] == 50.0
    assert volume["by_access_method"]["rss_feed"] == 2


# --------------------------------------------------------------------------- #
# Fraîcheur
# --------------------------------------------------------------------------- #
def test_freshness_kpis_compute_a_median_age() -> None:
    reference = datetime(2026, 8, 20, 20, 0, tzinfo=UTC)
    freshness = freshness_kpis(_sample_df(), now=reference)

    # Ages: 12 h, 36 h and 250 h -> median at 36 h; the undated publication is ignored.
    assert freshness["median_age_hours"] == 36.0
    assert freshness["dated_publications"] == 3
    assert freshness["under_24h_pct"] == 33.3


def test_freshness_kpis_without_any_date() -> None:
    df = pd.DataFrame({"published_at": [None, None]})
    assert freshness_kpis(df)["median_age_hours"] == 0.0


# --------------------------------------------------------------------------- #
# Performance et coût
# --------------------------------------------------------------------------- #
def test_performance_kpis() -> None:
    performance = performance_kpis(_sample_run())

    assert performance["total_duration_sec"] == 2.0
    assert performance["publications_per_sec"] == 2.5  # 5 collectées / 2 s
    assert performance["api_calls_spent"] == 1
    assert performance["image_weight_mb"] == 2.0
    assert performance["images_downloaded_pct"] == 80.0  # 4 obtenues / 5 tentées
    assert performance["new_rate_pct"] == 80.0  # 4 nouvelles / 5 collectées


def test_performance_kpis_without_a_run() -> None:
    assert performance_kpis({})["total_duration_sec"] == 0.0


# --------------------------------------------------------------------------- #
# Thresholds of the monitoring plan
# --------------------------------------------------------------------------- #
def test_status_for_an_indicator_to_maximise() -> None:
    assert status_for("validity_rate_pct", 92) == "green"
    assert status_for("validity_rate_pct", 50) == "amber"
    assert status_for("validity_rate_pct", 30) == "red"


def test_status_for_an_indicator_to_minimise() -> None:
    assert status_for("total_duration_sec", 20) == "green"
    assert status_for("total_duration_sec", 120) == "amber"
    assert status_for("total_duration_sec", 600) == "red"


def test_evaluate_thresholds_covers_the_monitored_indicators() -> None:
    kpis = compute_kpis(_sample_df(), {"raw_total": 5, "duplicates": 1}, _sample_run())
    evaluations = evaluate_thresholds(kpis)

    indicateurs = {evaluation["indicator"] for evaluation in evaluations}
    assert indicateurs == set(THRESHOLDS)
    assert all(evaluation["status"] in {"green", "amber", "red"} for evaluation in evaluations)


def test_every_threshold_is_justified() -> None:
    # A threshold with no rationale cannot be defended to the team.
    for name, threshold in THRESHOLDS.items():
        assert threshold.justification, f"threshold with no rationale: {name}"
        assert threshold.direction in {"higher_is_better", "lower_is_better"}


def test_compute_kpis_structure() -> None:
    kpis = compute_kpis(_sample_df(), {"raw_total": 4}, _sample_run())
    assert set(kpis) == {"quality", "volume", "freshness", "performance"}
