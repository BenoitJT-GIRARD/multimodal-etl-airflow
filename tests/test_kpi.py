"""Tests unitaires du calcul des KPI."""

from __future__ import annotations

from datetime import UTC, datetime

import pandas as pd

from multimodal_etl.kpi import (
    SEUILS,
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
            "access_method": ["flux_rss", "flux_rss", "api_rest", "telechargement_kaggle"],
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
        "images": {"tentees": 5, "reussies": 4, "octets": 2 * 1024 * 1024},
    }


# --------------------------------------------------------------------------- #
# Qualité
# --------------------------------------------------------------------------- #
def test_quality_kpis() -> None:
    qualite = quality_kpis(_sample_df(), {"total_brut": 5, "doublons": 1})

    assert qualite["taux_validite_pct"] == 80.0  # 4 valides / 5 collectées
    assert qualite["taux_association_texte_image_pct"] == 75.0  # 3 images / 4
    assert qualite["taux_labellise_pct"] == 25.0  # 1 label / 4
    assert qualite["taux_date_connue_pct"] == 75.0  # 3 dates connues / 4


def test_quality_kpis_on_an_empty_dataset() -> None:
    qualite = quality_kpis(pd.DataFrame(), {})
    assert qualite["taux_validite_pct"] == 0.0


# --------------------------------------------------------------------------- #
# Volume et diversité
# --------------------------------------------------------------------------- #
def test_volume_kpis_measure_the_concentration() -> None:
    volume = volume_kpis(_sample_df())

    assert volume["nb_publications"] == 4
    assert volume["nb_sources"] == 3
    # Deux publications sur quatre viennent de la même source.
    assert volume["part_source_dominante_pct"] == 50.0
    assert volume["repartition_methodes_acces"]["flux_rss"] == 2


# --------------------------------------------------------------------------- #
# Fraîcheur
# --------------------------------------------------------------------------- #
def test_freshness_kpis_compute_a_median_age() -> None:
    reference = datetime(2026, 8, 20, 20, 0, tzinfo=UTC)
    fraicheur = freshness_kpis(_sample_df(), maintenant=reference)

    # Âges : 12 h, 36 h et 250 h -> médiane à 36 h ; la publication sans date est ignorée.
    assert fraicheur["age_median_heures"] == 36.0
    assert fraicheur["publications_datees"] == 3
    assert fraicheur["part_moins_24h_pct"] == 33.3


def test_freshness_kpis_without_any_date() -> None:
    df = pd.DataFrame({"published_at": [None, None]})
    assert freshness_kpis(df)["age_median_heures"] == 0.0


# --------------------------------------------------------------------------- #
# Performance et coût
# --------------------------------------------------------------------------- #
def test_performance_kpis() -> None:
    performance = performance_kpis(_sample_run())

    assert performance["duree_totale_sec"] == 2.0
    assert performance["debit_publications_par_sec"] == 2.5  # 5 collectées / 2 s
    assert performance["appels_api_consommes"] == 1
    assert performance["poids_images_mo"] == 2.0
    assert performance["taux_images_telechargees_pct"] == 80.0  # 4 obtenues / 5 tentées
    assert performance["taux_nouveaute_pct"] == 80.0  # 4 nouvelles / 5 collectées


def test_performance_kpis_without_a_run() -> None:
    assert performance_kpis({})["duree_totale_sec"] == 0.0


# --------------------------------------------------------------------------- #
# Seuils du plan de monitoring
# --------------------------------------------------------------------------- #
def test_status_for_an_indicator_to_maximise() -> None:
    assert status_for("taux_validite_pct", 92) == "vert"
    assert status_for("taux_validite_pct", 50) == "orange"
    assert status_for("taux_validite_pct", 30) == "rouge"


def test_status_for_an_indicator_to_minimise() -> None:
    assert status_for("duree_totale_sec", 20) == "vert"
    assert status_for("duree_totale_sec", 120) == "orange"
    assert status_for("duree_totale_sec", 600) == "rouge"


def test_evaluate_thresholds_covers_the_monitored_indicators() -> None:
    kpis = compute_kpis(_sample_df(), {"total_brut": 5, "doublons": 1}, _sample_run())
    evaluations = evaluate_thresholds(kpis)

    indicateurs = {evaluation["indicateur"] for evaluation in evaluations}
    assert indicateurs == set(SEUILS)
    assert all(
        evaluation["statut"] in {"vert", "orange", "rouge"} for evaluation in evaluations
    )


def test_every_threshold_is_justified() -> None:
    # Un seuil sans justification ne peut pas être défendu devant l'équipe.
    for nom, seuil in SEUILS.items():
        assert seuil.justification, f"seuil sans justification : {nom}"
        assert seuil.sens in {"haut", "bas"}


def test_compute_kpis_structure() -> None:
    kpis = compute_kpis(_sample_df(), {"total_brut": 4}, _sample_run())
    assert set(kpis) == {"qualite", "volume", "fraicheur", "performance"}
