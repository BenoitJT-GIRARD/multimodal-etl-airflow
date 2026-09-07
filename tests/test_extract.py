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
    assert tally["works"] == {"count": 2, "cause": "ok"}
    assert tally["down"] == {"count": -1, "cause": "malformed"}


def test_failed_sources_counts_the_outages(monkeypatch) -> None:
    monkeypatch.setattr(extract.newsdata, "is_enabled", lambda: True)
    tally = {
        "rss": {"count": 40, "cause": "ok"},
        "newsdata": {"count": -1, "cause": "quota"},
        "fakenewsnet": {"count": -1, "cause": "network"},
    }
    assert extract.failed_sources(tally) == 2


def test_a_disabled_source_is_not_an_outage(monkeypatch) -> None:
    # Without an API key NewsData.io does not turn on: that is not an incident.
    monkeypatch.setattr(extract.newsdata, "is_enabled", lambda: False)
    monkeypatch.setattr(
        extract,
        "_CONNECTORS",
        {"rss": lambda config: [{"title": "a"}], "newsdata": lambda config: []},
    )

    _, tally = extract.collect_sources(ExtractionConfig())

    assert tally["newsdata"]["cause"] == "disabled"
    assert extract.failed_sources(tally) == 0


def test_a_source_that_answers_with_nothing_is_not_an_outage_either(monkeypatch) -> None:
    # An RSS feed that published nothing today is quiet, not broken. It is still worth
    # telling apart from a healthy one, which is what the cause is for.
    monkeypatch.setattr(extract, "_CONNECTORS", {"rss": lambda config: []})

    _, tally = extract.collect_sources(ExtractionConfig())

    assert tally["rss"]["cause"] == "empty"
    assert extract.failed_sources(tally) == 0
