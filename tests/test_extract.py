"""Tests unitaires de l'orchestration de l'extraction."""

from __future__ import annotations

from multimodal_etl import extract
from multimodal_etl.config import ExtractionConfig


def test_une_source_qui_echoue_n_arrete_pas_les_autres(monkeypatch) -> None:
    def connecteur_en_panne(config: ExtractionConfig) -> list[dict]:
        raise RuntimeError("service indisponible")

    monkeypatch.setattr(
        extract,
        "_CONNECTEURS",
        {
            "qui_marche": lambda config: [{"title": "a"}, {"title": "b"}],
            "en_panne": connecteur_en_panne,
        },
    )

    publications, bilan = extract.collecte_sources(ExtractionConfig())

    assert len(publications) == 2
    assert bilan == {"qui_marche": 2, "en_panne": -1}


def test_sources_en_echec_compte_les_pannes(monkeypatch) -> None:
    monkeypatch.setattr(extract.newsdata, "is_enabled", lambda: True)
    assert extract.failed_sources({"rss": 40, "newsdata": 0, "fakenewsnet": -1}) == 2


def test_une_source_desactivee_n_est_pas_une_panne(monkeypatch) -> None:
    # Sans clé d'API, NewsData.io ne s'active pas : ce n'est pas un incident.
    monkeypatch.setattr(extract.newsdata, "is_enabled", lambda: False)
    assert extract.failed_sources({"rss": 40, "newsdata": 0}) == 0
