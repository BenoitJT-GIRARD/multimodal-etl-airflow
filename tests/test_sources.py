"""Tests unitaires des connecteurs de sources."""

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
def test_extraction_image_depuis_media_content() -> None:
    flux = feedparser.parse(FLUX_RSS_EXEMPLE)
    assert rss.extract_image_from_entry(flux.entries[0]) == "https://presse.example.com/photo.jpg"


def test_extraction_image_absente_renvoie_une_chaine_vide() -> None:
    flux = feedparser.parse(FLUX_RSS_EXEMPLE)
    assert rss.extract_image_from_entry(flux.entries[1]) == ""


def test_extraction_image_depuis_une_balise_img_du_resume() -> None:
    entree = feedparser.util.FeedParserDict(
        summary='<p>Texte <img src="https://presse.example.com/inline.png"/></p>'
    )
    assert rss.extract_image_from_entry(entree) == "https://presse.example.com/inline.png"


def test_fetch_rss_feed_normalise_les_champs(monkeypatch) -> None:
    flux = feedparser.parse(FLUX_RSS_EXEMPLE)
    monkeypatch.setattr(rss.feedparser, "parse", lambda *a, **k: flux)
    records = rss.fetch_rss_feed("presse_test", "https://exemple", ExtractionConfig())

    assert len(records) == 2
    premier = records[0]
    assert premier["source"] == "rss:presse_test"
    assert premier["access_method"] == "flux_rss"
    assert premier["image_source"] == "native"
    assert records[1]["image_source"] == "aucune"


def test_fetch_rss_feed_survit_a_un_flux_injoignable(monkeypatch) -> None:
    def echoue(*args, **kwargs):
        raise OSError("réseau indisponible")

    monkeypatch.setattr(rss.feedparser, "parse", echoue)
    assert rss.fetch_rss_feed("presse_test", "https://exemple", ExtractionConfig()) == []


# --------------------------------------------------------------------------- #
# API NewsData.io
# --------------------------------------------------------------------------- #
def test_newsdata_est_ignore_sans_cle(monkeypatch) -> None:
    monkeypatch.delenv("NEWSDATA_API_KEY", raising=False)
    assert newsdata.is_enabled() is False
    assert newsdata.fetch_newsdata(ExtractionConfig()) == []


# --------------------------------------------------------------------------- #
# FakeNewsNet (GitHub)
# --------------------------------------------------------------------------- #
def test_nom_source_deduit_organisme_et_label() -> None:
    assert fakenewsnet._nom_source("politifact_fake.csv") == ("politifact", "fake")
    assert fakenewsnet._nom_source("gossipcop_real.csv") == ("gossipcop", "real")


def test_lit_csv_supporte_les_champs_tres_longs(tmp_path: Path) -> None:
    # La colonne tweet_ids du jeu réel dépasse la limite par défaut du module csv.
    tweets = "\t".join(str(i) for i in range(60_000))
    chemin = tmp_path / "politifact_fake.csv"
    chemin.write_text(
        f'id,news_url,title,tweet_ids\np1,exemple.com/a,"Un titre","{tweets}"\n', encoding="utf-8"
    )

    lignes = fakenewsnet.lit_csv(chemin)

    assert len(lignes) == 1
    assert lignes[0]["title"] == "Un titre"


def test_construit_record_fakenewsnet_ajoute_le_schema_et_le_label() -> None:
    ligne = {"news_url": "exemple.com/article", "title": "Un titre"}
    record = fakenewsnet._construit_record(ligne, "politifact", "fake")

    assert record["source"] == "fakenewsnet:politifact"
    assert record["access_method"] == "telechargement_github"
    assert record["url"] == "https://exemple.com/article"
    assert record["label"] == "fake"
    assert record["image_url"] == ""  # l'image sera cherchée via Open Graph


# --------------------------------------------------------------------------- #
# Enrichissement Open Graph
# --------------------------------------------------------------------------- #
def test_normalise_url_ajoute_le_schema() -> None:
    assert opengraph.normalise_url("exemple.com/a") == "https://exemple.com/a"
    assert opengraph.normalise_url("https://exemple.com/a") == "https://exemple.com/a"
    assert opengraph.normalise_url("  ") == ""


def test_enrichit_publications_respecte_le_plafond(monkeypatch) -> None:
    monkeypatch.setattr(
        opengraph, "lit_image_open_graph", lambda url, config: "https://site.com/og.jpg"
    )
    records = [{"url": f"https://site.com/{i}", "image_url": ""} for i in range(5)]

    compteurs = opengraph.enrichit_publications(
        records, ExtractionConfig(max_enrichissements_open_graph=2)
    )

    assert compteurs == {"tentees": 2, "trouvees": 2}
    assert records[0]["image_source"] == "open_graph"
    assert records[4]["image_url"] == ""


def test_enrichit_publications_ignore_celles_qui_ont_deja_une_image(monkeypatch) -> None:
    monkeypatch.setattr(opengraph, "lit_image_open_graph", lambda url, config: "https://og.jpg")
    records = [{"url": "https://site.com/a", "image_url": "https://deja.jpg"}]

    compteurs = opengraph.enrichit_publications(records, ExtractionConfig())

    assert compteurs["tentees"] == 0
    assert records[0]["image_url"] == "https://deja.jpg"


# --------------------------------------------------------------------------- #
# Fakeddit (Kaggle)
# --------------------------------------------------------------------------- #
def test_fakeddit_lit_l_echantillon_versionne(tmp_path: Path, monkeypatch) -> None:
    # Le dossier Kaggle est vidé pour que le test ne dépende pas de la présence du
    # jeu réel sur la machine : c'est bien le repli sur l'échantillon qu'on vérifie.
    monkeypatch.setattr(kaggle_fakeddit, "DOSSIER_KAGGLE", tmp_path / "vide")

    records = kaggle_fakeddit.fetch_fakeddit(ExtractionConfig(max_items_per_source=5))

    assert len(records) == 5
    assert records[0]["source"] == "fakeddit"
    assert records[0]["access_method"] == "telechargement_kaggle"
    assert records[0]["image_url"].startswith("https://upload.wikimedia.org/")
    assert records[0]["label"] in {"real", "fake"}
    assert records[0]["url"].startswith("https://redd.it/")


def test_fakeddit_prefere_le_jeu_kaggle_reel(tmp_path: Path, monkeypatch) -> None:
    dossier = tmp_path / "kaggle"
    dossier.mkdir()
    (dossier / "all_samples.tsv").write_text(
        "id\tclean_title\timage_url\thasImage\tsubreddit\t2_way_label\n"
        "abc123\tUn titre reel\thttps://site.com/i.jpg\tTrue\tnews\t1\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(kaggle_fakeddit, "DOSSIER_KAGGLE", dossier)

    records = kaggle_fakeddit.fetch_fakeddit(ExtractionConfig())

    assert len(records) == 1
    assert records[0]["title"] == "Un titre reel"
    assert records[0]["label"] == "real"


def test_fakeddit_ecarte_les_lignes_sans_image(tmp_path: Path, monkeypatch) -> None:
    dossier = tmp_path / "kaggle"
    dossier.mkdir()
    (dossier / "all_samples.tsv").write_text(
        "id\tclean_title\timage_url\thasImage\tsubreddit\t2_way_label\n"
        "a\tAvec image\thttps://site.com/i.jpg\tTrue\tnews\t1\n"
        "b\tSans image\t\tFalse\tnews\t0\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(kaggle_fakeddit, "DOSSIER_KAGGLE", dossier)

    records = kaggle_fakeddit.fetch_fakeddit(ExtractionConfig())

    assert [r["title"] for r in records] == ["Avec image"]
