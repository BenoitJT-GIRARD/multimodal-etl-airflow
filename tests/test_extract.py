"""Unit tests of the extraction orchestration."""

from __future__ import annotations

from multimodal_etl import extract
from multimodal_etl.config import ExtractionConfig


def test_a_failing_source_does_not_stop_the_others(monkeypatch) -> None:
    def failing_connector(config: ExtractionConfig) -> list[dict]:
        raise RuntimeError("service unavailable")

    monkeypatch.setattr(
        extract,
        "_CONNECTORS",
        {
            "works": lambda config: [{"title": "a"}, {"title": "b"}],
            "down": failing_connector,
        },
    )

    publications, tally = extract.collect_sources(ExtractionConfig())

    assert len(publications) == 2
    assert tally == {"works": 2, "down": -1}


def test_failed_sources_counts_the_outages(monkeypatch) -> None:
    monkeypatch.setattr(extract.newsdata, "is_enabled", lambda: True)
    assert extract.failed_sources({"rss": 40, "newsdata": 0, "fakenewsnet": -1}) == 2


def test_a_disabled_source_is_not_an_outage(monkeypatch) -> None:
    # Without an API key NewsData.io does not turn on: that is not an incident.
    monkeypatch.setattr(extract.newsdata, "is_enabled", lambda: False)
    assert extract.failed_sources({"rss": 40, "newsdata": 0}) == 0
