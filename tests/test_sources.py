"""Unit tests of the source connectors."""

from __future__ import annotations

from pathlib import Path

import feedparser

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
    flux = feedparser.parse(FLUX_RSS_EXEMPLE)
    monkeypatch.setattr(rss.feedparser, "parse", lambda *a, **k: flux)
    records = rss.fetch_rss_feed("presse_test", "https://exemple", ExtractionConfig())

    assert len(records) == 2
    premier = records[0]
    assert premier["source"] == "rss:presse_test"
    assert premier["access_method"] == "rss_feed"
    assert premier["image_source"] == "native"
    assert records[1]["image_source"] == "none"


def test_fetch_rss_feed_survives_an_unreachable_feed(monkeypatch) -> None:
    def fails(*args, **kwargs):
        raise OSError("réseau indisponible")

    monkeypatch.setattr(rss.feedparser, "parse", fails)
    assert rss.fetch_rss_feed("presse_test", "https://exemple", ExtractionConfig()) == []


# --------------------------------------------------------------------------- #
# API NewsData.io
# --------------------------------------------------------------------------- #
def test_newsdata_is_skipped_without_a_key(monkeypatch) -> None:
    monkeypatch.delenv("NEWSDATA_API_KEY", raising=False)
    assert newsdata.is_enabled() is False
    assert newsdata.fetch_newsdata(ExtractionConfig()) == []


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
