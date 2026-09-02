"""Tests unitaires du calcul des KPI."""

from __future__ import annotations

from datetime import UTC, datetime

import pandas as pd

from multimodal_etl.kpi import (
    SEUILS,
    compute_kpis,
    evalue_seuils,
    kpis_fraicheur,
    kpis_performance,
    kpis_qualite,
    kpis_volume,
    statut,
)


def _df_exemple() -> pd.DataFrame:
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


def _run_exemple() -> dict:
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
def test_kpis_qualite() -> None:
    qualite = kpis_qualite(_df_exemple(), {"total_brut": 5, "doublons": 1})

    assert qualite["taux_validite_pct"] == 80.0  # 4 valides / 5 collectées
    assert qualite["taux_association_texte_image_pct"] == 75.0  # 3 images / 4
    assert qualite["taux_labellise_pct"] == 25.0  # 1 label / 4
    assert qualite["taux_date_connue_pct"] == 75.0  # 3 dates connues / 4


def test_kpis_qualite_sur_un_jeu_vide() -> None:
    qualite = kpis_qualite(pd.DataFrame(), {})
    assert qualite["taux_validite_pct"] == 0.0


# --------------------------------------------------------------------------- #
# Volume et diversité
# --------------------------------------------------------------------------- #
def test_kpis_volume_mesure_la_concentration() -> None:
    volume = kpis_volume(_df_exemple())

    assert volume["nb_publications"] == 4
    assert volume["nb_sources"] == 3
    # Deux publications sur quatre viennent de la même source.
    assert volume["part_source_dominante_pct"] == 50.0
    assert volume["repartition_methodes_acces"]["flux_rss"] == 2


# --------------------------------------------------------------------------- #
# Fraîcheur
# --------------------------------------------------------------------------- #
def test_kpis_fraicheur_calcule_un_age_median() -> None:
    reference = datetime(2026, 8, 20, 20, 0, tzinfo=UTC)
    fraicheur = kpis_fraicheur(_df_exemple(), maintenant=reference)

    # Âges : 12 h, 36 h et 250 h -> médiane à 36 h ; la publication sans date est ignorée.
    assert fraicheur["age_median_heures"] == 36.0
    assert fraicheur["publications_datees"] == 3
    assert fraicheur["part_moins_24h_pct"] == 33.3


def test_kpis_fraicheur_sans_aucune_date() -> None:
    df = pd.DataFrame({"published_at": [None, None]})
    assert kpis_fraicheur(df)["age_median_heures"] == 0.0


# --------------------------------------------------------------------------- #
# Performance et coût
# --------------------------------------------------------------------------- #
def test_kpis_performance() -> None:
    performance = kpis_performance(_run_exemple())

    assert performance["duree_totale_sec"] == 2.0
    assert performance["debit_publications_par_sec"] == 2.5  # 5 collectées / 2 s
    assert performance["appels_api_consommes"] == 1
    assert performance["poids_images_mo"] == 2.0
    assert performance["taux_images_telechargees_pct"] == 80.0  # 4 obtenues / 5 tentées
    assert performance["taux_nouveaute_pct"] == 80.0  # 4 nouvelles / 5 collectées


def test_kpis_performance_sans_execution() -> None:
    assert kpis_performance({})["duree_totale_sec"] == 0.0


# --------------------------------------------------------------------------- #
# Seuils du plan de monitoring
# --------------------------------------------------------------------------- #
def test_statut_sur_un_indicateur_a_maximiser() -> None:
    assert statut("taux_validite_pct", 92) == "vert"
    assert statut("taux_validite_pct", 50) == "orange"
    assert statut("taux_validite_pct", 30) == "rouge"


def test_statut_sur_un_indicateur_a_minimiser() -> None:
    assert statut("duree_totale_sec", 20) == "vert"
    assert statut("duree_totale_sec", 120) == "orange"
    assert statut("duree_totale_sec", 600) == "rouge"


def test_evalue_seuils_couvre_les_indicateurs_surveilles() -> None:
    kpis = compute_kpis(_df_exemple(), {"total_brut": 5, "doublons": 1}, _run_exemple())
    evaluations = evalue_seuils(kpis)

    indicateurs = {evaluation["indicateur"] for evaluation in evaluations}
    assert indicateurs == set(SEUILS)
    assert all(evaluation["statut"] in {"vert", "orange", "rouge"} for evaluation in evaluations)


def test_chaque_seuil_est_justifie() -> None:
    # Un seuil sans justification ne peut pas être défendu devant l'équipe.
    for nom, seuil in SEUILS.items():
        assert seuil.justification, f"seuil sans justification : {nom}"
        assert seuil.sens in {"haut", "bas"}


def test_compute_kpis_structure() -> None:
    kpis = compute_kpis(_df_exemple(), {"total_brut": 4}, _run_exemple())
    assert set(kpis) == {"qualite", "volume", "fraicheur", "performance"}
