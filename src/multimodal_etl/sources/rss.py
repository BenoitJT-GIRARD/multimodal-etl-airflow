"""Connecteur 1 — flux RSS de sites de presse.

Les flux RSS sont des sources **officielles**, gratuites et sans clé d'API : ils
constituent le socle multimodal du pipeline (titre + résumé + image). On utilise
``feedparser`` pour lire le flux, puis quelques fonctions dédiées pour en extraire
l'image associée (la partie la plus délicate, car elle peut se trouver à plusieurs
endroits de l'entrée RSS).
"""

from __future__ import annotations

import feedparser
from bs4 import BeautifulSoup

from multimodal_etl.config import ExtractionConfig
from multimodal_etl.logging_setup import get_logger

logger = get_logger(__name__)


def extract_image_from_entry(entry: feedparser.FeedParserDict) -> str:
    """Cherche l'URL d'image d'une entree RSS aux endroits usuels.

    Ordre de recherche : ``media_content`` -> ``media_thumbnail`` -> ``enclosures``
    -> balise ``<img>`` dans le resume HTML. Renvoie une chaine vide si rien n'est
    trouve (la publication sera ecartee plus tard si l'image est obligatoire).
    """
    # 1. Balises Media RSS : <media:content url="...">
    for media in entry.get("media_content", []):
        url = media.get("url", "")
        if url:
            return url

    # 2. Vignettes : <media:thumbnail url="...">
    for thumb in entry.get("media_thumbnail", []):
        url = thumb.get("url", "")
        if url:
            return url

    # 3. Pieces jointes : <enclosure type="image/..." url="...">
    for enclosure in entry.get("enclosures", []):
        if enclosure.get("type", "").startswith("image") and enclosure.get("href"):
            return enclosure["href"]

    # 4. Premiere balise <img> dans le resume HTML.
    summary = entry.get("summary", "")
    if summary:
        soup = BeautifulSoup(summary, "lxml")
        img = soup.find("img")
        if img and img.get("src"):
            return img["src"]

    return ""


def _parse_entry(entry: feedparser.FeedParserDict, source_name: str) -> dict[str, object]:
    """Transforme une entrée feedparser en dictionnaire brut normalisé."""
    image_url = extract_image_from_entry(entry)
    return {
        "source": f"rss:{source_name}",
        "source_type": "rss",
        "access_method": "flux_rss",
        "title": entry.get("title", ""),
        "text": entry.get("summary", ""),
        "url": entry.get("link", ""),
        "image_url": image_url,
        "image_source": "native" if image_url else "aucune",
        "published_at": entry.get("published", ""),
        "language": "en",
        # Les flux de presse généraliste ne sont pas labellisés vrai/faux.
        "label": None,
        "label_source": None,
    }


def fetch_rss_feed(source_name: str, url: str, config: ExtractionConfig) -> list[dict[str, object]]:
    """Recupere et parse un flux RSS unique.

    La connexion et le parsing sont encapsules dans un try/except : un flux
    indisponible n'interrompt jamais le pipeline, il est simplement journalise.
    """
    logger.info("RSS : lecture du flux '%s' (%s)", source_name, url)
    try:
        feed = feedparser.parse(url, agent=config.user_agent)
    except Exception as exc:
        logger.error("RSS : echec de lecture du flux '%s' : %s", source_name, exc)
        return []

    if feed.bozo:
        logger.warning("RSS : flux '%s' mal forme (%s)", source_name, feed.get("bozo_exception"))

    entries = feed.entries[: config.max_items_per_source]
    records = [_parse_entry(entry, source_name) for entry in entries]
    logger.info("RSS : %d publications recuperees depuis '%s'", len(records), source_name)
    return records


def fetch_all_rss(config: ExtractionConfig) -> list[dict[str, object]]:
    """Parcourt tous les flux RSS configures et concatene les resultats."""
    records: list[dict[str, object]] = []
    for source_name, url in config.rss_feeds:
        records.extend(fetch_rss_feed(source_name, url, config))
    logger.info("RSS : total de %d publications sur %d flux", len(records), len(config.rss_feeds))
    return records
