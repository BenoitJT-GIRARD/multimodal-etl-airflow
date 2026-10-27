"""Unit tests of the source connectors."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import feedparser
import pytest
import requests

from multimodal_etl.config import ExtractionConfig
from multimodal_etl.sources import fakenewsnet, kaggle_fakeddit, newsdata, opengraph, rss

FLUX_RSS_EXEMPLE = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:media="http://search.yahoo.com/mrss/">
  <channel>
    <item>
      <title>Un titre d'article</title>
      <link>https://presse.example.com/article-1</link>
      <description>&lt;p&gt;Un resume avec &lt;b&gt;du HTML&lt;/b&gt;.&lt;/p&gt;</description>
      <pubDate>Mon, 29 Jun 2026 10:00:00 GMT</pubDate>
      <media:content url="https://presse.example.com/photo.jpg" />
    </item>
    <item>
      <title>Un article sans image</title>
      <link>https://presse.example.com/article-2</link>
      <description>Un resume sans balise image.</description>
    </item>
  </channel>
</rss>
"""


def _response(url: str, status: int, body: bytes, content_type: str) -> requests.Response:
    """A real `requests.Response`, so `raise_for_status` and `json` behave as they do live."""
    response = requests.Response()
    response.status_code = status
    response.reason = "Too Many Requests" if status == 429 else "OK"
    response._content = body
    response.headers["Content-Type"] = content_type
    response.url = url
    return response


# --------------------------------------------------------------------------- #
# Flux RSS
# --------------------------------------------------------------------------- #
def test_image_extraction_from_media_content() -> None:
    flux = feedparser.parse(FLUX_RSS_EXEMPLE)
    assert rss.extract_image_from_entry(flux.entries[0]) == "https://presse.example.com/photo.jpg"


def test_image_extraction_returns_an_empty_string_when_absent() -> None:
    flux = feedparser.parse(FLUX_RSS_EXEMPLE)
    assert rss.extract_image_from_entry(flux.entries[1]) == ""


def test_image_extraction_from_an_img_tag_in_the_summary() -> None:
    entree = feedparser.util.FeedParserDict(
        summary='<p>Texte <img src="https://presse.example.com/inline.png"/></p>'
    )
    assert rss.extract_image_from_entry(entree) == "https://presse.example.com/inline.png"


def test_fetch_rss_feed_normalises_the_fields(monkeypatch) -> None:
    calls = []

    def get(url, **kwargs):
        calls.append(kwargs)
        return _response(url, 200, FLUX_RSS_EXEMPLE.encode(), "application/rss+xml")

    monkeypatch.setattr(rss.requests, "get", get)
    config = ExtractionConfig()
    records = rss.fetch_rss_feed("presse_test", "https://exemple.invalid/rss", config)

    assert len(records) == 2
    premier = records[0]
    assert premier["source"] == "rss:presse_test"
    assert premier["access_method"] == "rss_feed"
    assert premier["image_source"] == "native"
    assert records[1]["image_source"] == "none"
    # The feed is downloaded under the same timeout as every other request of the pipeline.
    assert calls[0]["timeout"] == config.request_timeout


def test_an_unreachable_feed_is_raised_when_no_other_feed_delivered(monkeypatch) -> None:
    def fails(url, **kwargs):
        raise requests.exceptions.ConnectionError("network unreachable")

    monkeypatch.setattr(rss.requests, "get", fails)
    config = replace(ExtractionConfig(), rss_feeds=(("presse_test", "https://exemple.invalid"),))

    with pytest.raises(requests.exceptions.ConnectionError):
        rss.fetch_all_rss(config)


def test_an_unreachable_feed_does_not_lose_the_other_feeds(monkeypatch) -> None:
    def get(url, **kwargs):
        if "down" in url:
            raise requests.exceptions.Timeout("timed out")
        return _response(url, 200, FLUX_RSS_EXEMPLE.encode(), "application/rss+xml")

    monkeypatch.setattr(rss.requests, "get", get)
    config = replace(
        ExtractionConfig(),
        rss_feeds=(("down", "https://down.invalid/rss"), ("up", "https://up.invalid/rss")),
    )

    records = rss.fetch_all_rss(config)

    assert {record["source"] for record in records} == {"rss:up"}


# --------------------------------------------------------------------------- #
# API NewsData.io
# --------------------------------------------------------------------------- #
def test_newsdata_is_skipped_without_a_key(monkeypatch) -> None:
    monkeypatch.delenv("NEWSDATA_API_KEY", raising=False)
    assert newsdata.is_enabled() is False
    assert newsdata.fetch_newsdata(ExtractionConfig()) == []


def test_newsdata_raises_a_spent_quota(monkeypatch) -> None:
    monkeypatch.setenv("NEWSDATA_API_KEY", "a-test-key")
    monkeypatch.setattr(
        newsdata.requests,
        "get",
        lambda url, **kwargs: _response(url, 429, b'{"status": "error"}', "application/json"),
    )

    with pytest.raises(requests.exceptions.HTTPError, match="429"):
        newsdata.fetch_newsdata(ExtractionConfig())


def test_newsdata_raises_a_payload_that_reports_an_error(monkeypatch) -> None:
    monkeypatch.setenv("NEWSDATA_API_KEY", "a-test-key")
    body = b'{"status": "error", "results": {"message": "unexpected"}}'
    monkeypatch.setattr(
        newsdata.requests,
        "get",
        lambda url, **kwargs: _response(url, 200, body, "application/json"),
    )

    with pytest.raises(ValueError, match="unexpected"):
        newsdata.fetch_newsdata(ExtractionConfig())


# --------------------------------------------------------------------------- #
# FakeNewsNet (GitHub)
# --------------------------------------------------------------------------- #
def test_source_name_infers_the_organisation_and_the_label() -> None:
    assert fakenewsnet._source_name("politifact_fake.csv") == ("politifact", "fake")
    assert fakenewsnet._source_name("gossipcop_real.csv") == ("gossipcop", "real")


def test_read_csv_supports_very_long_fields(tmp_path: Path) -> None:
    # The real dataset's tweet_ids column exceeds the csv module's default limit.
    tweets = "\t".join(str(i) for i in range(60_000))
    path_for = tmp_path / "politifact_fake.csv"
    path_for.write_text(
        f'id,news_url,title,tweet_ids\np1,exemple.com/a,"Un titre","{tweets}"\n', encoding="utf-8"
    )

    lignes = fakenewsnet.read_csv(path_for)

    assert len(lignes) == 1
    assert lignes[0]["title"] == "Un titre"


def test_fakenewsnet_raises_when_every_download_failed(tmp_path: Path, monkeypatch) -> None:
    def fails(url, **kwargs):
        raise requests.exceptions.ConnectionError("network unreachable")

    monkeypatch.setattr(fakenewsnet, "CACHE_DIR", tmp_path / "fakenewsnet")
    monkeypatch.setattr(fakenewsnet.requests, "get", fails)

    with pytest.raises(requests.exceptions.ConnectionError):
        fakenewsnet.fetch_fakenewsnet(ExtractionConfig())


def test_build_fakenewsnet_record_adds_the_schema_and_the_label() -> None:
    ligne = {"news_url": "exemple.com/article", "title": "Un titre"}
    record = fakenewsnet._build_record(ligne, "politifact", "fake")

    assert record["source"] == "fakenewsnet:politifact"
    assert record["access_method"] == "github_download"
    assert record["url"] == "https://exemple.com/article"
    assert record["label"] == "fake"
    assert record["image_url"] == ""  # l'image sera cherchée via Open Graph


# --------------------------------------------------------------------------- #
# Enrichissement Open Graph
# --------------------------------------------------------------------------- #
def test_normalise_url_adds_the_scheme() -> None:
    assert opengraph.normalise_url("exemple.com/a") == "https://exemple.com/a"
    assert opengraph.normalise_url("https://exemple.com/a") == "https://exemple.com/a"
    assert opengraph.normalise_url("  ") == ""


def test_enrich_publications_respects_the_cap(monkeypatch) -> None:
    monkeypatch.setattr(
        opengraph, "read_open_graph_image", lambda url, config: "https://site.com/og.jpg"
    )
    records = [{"url": f"https://site.com/{i}", "image_url": ""} for i in range(5)]

    compteurs = opengraph.enrich_publications(
        records, ExtractionConfig(max_open_graph_enrichments=2)
    )

    assert compteurs == {"attempted": 2, "found": 2}
    assert records[0]["image_source"] == "open_graph"
    assert records[4]["image_url"] == ""


def test_enrich_publications_skips_those_that_already_have_an_image(monkeypatch) -> None:
    monkeypatch.setattr(opengraph, "read_open_graph_image", lambda url, config: "https://og.jpg")
    records = [{"url": "https://site.com/a", "image_url": "https://deja.jpg"}]

    compteurs = opengraph.enrich_publications(records, ExtractionConfig())

    assert compteurs["attempted"] == 0
    assert records[0]["image_url"] == "https://deja.jpg"


# --------------------------------------------------------------------------- #
# Fakeddit (Kaggle)
# --------------------------------------------------------------------------- #
def test_fakeddit_reads_the_versioned_sample(tmp_path: Path, monkeypatch) -> None:
    # The Kaggle folder is emptied so the test does not depend on the real dataset being
    # on the machine: what we check here is the fallback to the sample.
    monkeypatch.setattr(kaggle_fakeddit, "KAGGLE_DIR", tmp_path / "vide")

    records = kaggle_fakeddit.fetch_fakeddit(ExtractionConfig(max_items_per_source=5))

    assert len(records) == 5
    assert records[0]["source"] == "fakeddit"
    assert records[0]["access_method"] == "kaggle_download"
    assert records[0]["image_url"].startswith("https://upload.wikimedia.org/")
    assert records[0]["label"] in {"real", "fake"}
    assert records[0]["url"].startswith("https://redd.it/")


def test_fakeddit_prefers_the_real_kaggle_dataset(tmp_path: Path, monkeypatch) -> None:
    dossier = tmp_path / "kaggle"
    dossier.mkdir()
    (dossier / "all_samples.tsv").write_text(
        "id\tclean_title\timage_url\thasImage\tsubreddit\t2_way_label\n"
        "abc123\tUn titre reel\thttps://site.com/i.jpg\tTrue\tnews\t1\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(kaggle_fakeddit, "KAGGLE_DIR", dossier)

    records = kaggle_fakeddit.fetch_fakeddit(ExtractionConfig())

    assert len(records) == 1
    assert records[0]["title"] == "Un titre reel"
    assert records[0]["label"] == "real"


def test_fakeddit_discards_rows_without_an_image(tmp_path: Path, monkeypatch) -> None:
    dossier = tmp_path / "kaggle"
    dossier.mkdir()
    (dossier / "all_samples.tsv").write_text(
        "id\tclean_title\timage_url\thasImage\tsubreddit\t2_way_label\n"
        "a\tAvec image\thttps://site.com/i.jpg\tTrue\tnews\t1\n"
        "b\tSans image\t\tFalse\tnews\t0\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(kaggle_fakeddit, "KAGGLE_DIR", dossier)

    records = kaggle_fakeddit.fetch_fakeddit(ExtractionConfig())

    assert [r["title"] for r in records] == ["Avec image"]
