"""Tests unitaires du calcul des KPI."""

from __future__ import annotations

import pandas as pd

from multimodal_etl.kpi import compute_kpis, kpis_performance, kpis_qualite


def _df_exemple() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "source": ["rss:bbc", "rss:bbc", "newsdata", "fakenewsnet:politifact"],
            "language": ["en", "en", "en", "en"],
            "has_image": [True, True, False, True],
            "label": [None, None, None, "fake"],
            "text_length": [100, 200, 150, 50],
        }
    )


def test_kpis_qualite() -> None:
    df = _df_exemple()
    stats = {"total_brut": 5, "doublons": 1}
    q = kpis_qualite(df, stats)
    assert q["taux_validite_pct"] == 80.0  # 4 valides / 5 bruts
    assert q["taux_association_texte_image_pct"] == 75.0  # 3 images / 4
    assert q["taux_labellise_pct"] == 25.0  # 1 label / 4


def test_kpis_performance() -> None:
    run = {
        "durations_sec": {"extract": 1.0, "transform": 0.5, "load": 0.5},
        "rows_loaded": 4,
        "api_calls": 1,
    }
    p = kpis_performance(run)
    assert p["duree_totale_sec"] == 2.0
    assert p["debit_publications_par_sec"] == 2.0
    assert p["appels_api_consommes"] == 1


def test_compute_kpis_structure() -> None:
    kpis = compute_kpis(_df_exemple(), {"total_brut": 4}, {"durations_sec": {}, "rows_loaded": 4})
    assert set(kpis.keys()) == {"qualite", "volume", "performance"}
    assert kpis["volume"]["nb_publications"] == 4
