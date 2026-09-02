"""Tests unitaires de l'orchestration de l'extraction."""

from __future__ import annotations

from multimodal_etl import extract
from multimodal_etl.config import ExtractionConfig


def test_a_failing_source_does_not_stop_the_others(monkeypatch) -> None:
    def failing_connector(config: ExtractionConfig) -> list[dict]:
        raise RuntimeError("service indisponible")

    monkeypatch.setattr(
        extract,
        "_CONNECTEURS",
        {
            "qui_marche": lambda config: [{"title": "a"}, {"title": "b"}],
            "en_panne": failing_connector,
        },
    )

    publications, bilan = extract.collect_sources(ExtractionConfig())

    assert len(publications) == 2
    assert bilan == {"qui_marche": 2, "en_panne": -1}


def test_failed_sources_counts_the_outages(monkeypatch) -> None:
    monkeypatch.setattr(extract.newsdata, "is_enabled", lambda: True)
    assert extract.failed_sources({"rss": 40, "newsdata": 0, "fakenewsnet": -1}) == 2


def test_a_disabled_source_is_not_an_outage(monkeypatch) -> None:
    # Sans clé d'API, NewsData.io ne s'active pas : ce n'est pas un incident.
    monkeypatch.setattr(extract.newsdata, "is_enabled", lambda: False)
    assert extract.failed_sources({"rss": 40, "newsdata": 0}) == 0
