"""Connector 1 — RSS feeds of news sites.

RSS feeds are **official** sources, free and without an API key: they are the multimodal
backbone of the pipeline (title + summary + image). We read the feed with ``feedparser``,
then use a few dedicated functions to pull out the associated image — the trickiest part,
because it can sit in several different places of an RSS entry.
"""

from __future__ import annotations

import feedparser
from bs4 import BeautifulSoup

from multimodal_etl.config import ExtractionConfig
from multimodal_etl.logging_setup import get_logger

logger = get_logger(__name__)


def extract_image_from_entry(entry: feedparser.FeedParserDict) -> str:
    """Look for the image URL of an RSS entry in the usual places.

    Search order: ``media_content`` -> ``media_thumbnail`` -> ``enclosures`` -> an
    ``<img>`` tag in the HTML summary. Returns an empty string when nothing is found
    (the publication is dropped later on if an image is required).
    """
    # 1. Media RSS tags: <media:content url="...">
    for media in entry.get("media_content", []):
        url = media.get("url", "")
        if url:
            return url

    # 2. Thumbnails: <media:thumbnail url="...">
    for thumb in entry.get("media_thumbnail", []):
        url = thumb.get("url", "")
        if url:
            return url

    # 3. Attachments: <enclosure type="image/..." url="...">
    for enclosure in entry.get("enclosures", []):
        if enclosure.get("type", "").startswith("image") and enclosure.get("href"):
            return enclosure["href"]

    # 4. First <img> tag in the HTML summary.
    summary = entry.get("summary", "")
    if summary:
        soup = BeautifulSoup(summary, "lxml")
        img = soup.find("img")
        if img and img.get("src"):
            return img["src"]

    return ""


def _parse_entry(entry: feedparser.FeedParserDict, source_name: str) -> dict[str, object]:
    """Turn a feedparser entry into a normalised raw dictionary."""
    image_url = extract_image_from_entry(entry)
    return {
        "source": f"rss:{source_name}",
        "source_type": "rss",
        "access_method": "rss_feed",
        "title": entry.get("title", ""),
        "text": entry.get("summary", ""),
        "url": entry.get("link", ""),
        "image_url": image_url,
        "image_source": "native" if image_url else "none",
        "published_at": entry.get("published", ""),
        "language": "en",
        # General news feeds carry no true/false label.
        "label": None,
        "label_source": None,
    }


def fetch_rss_feed(source_name: str, url: str, config: ExtractionConfig) -> list[dict[str, object]]:
    """Fetch and parse a single RSS feed.

    Connection and parsing are wrapped in a try/except: an unreachable feed never
    interrupts the pipeline, it is simply logged.
    """
    logger.info("RSS: reading feed '%s' (%s)", source_name, url)
    try:
        feed = feedparser.parse(url, agent=config.user_agent)
    except Exception as exc:
        logger.error("RSS: could not read feed '%s': %s", source_name, exc)
        return []

    if feed.bozo:
        logger.warning("RSS: feed '%s' is malformed (%s)", source_name, feed.get("bozo_exception"))

    entries = feed.entries[: config.max_items_per_source]
    records = [_parse_entry(entry, source_name) for entry in entries]
    logger.info("RSS: %d publications collected from '%s'", len(records), source_name)
    return records


def fetch_all_rss(config: ExtractionConfig) -> list[dict[str, object]]:
    """Walk every configured RSS feed and concatenate the results."""
    records: list[dict[str, object]] = []
    for source_name, url in config.rss_feeds:
        records.extend(fetch_rss_feed(source_name, url, config))
    logger.info(
        "RSS: %d publications in total across %d feeds", len(records), len(config.rss_feeds)
    )
    return records
