"""Connector 1 — RSS feeds of news sites.

RSS feeds are **official** sources, free and without an API key: they are the multimodal
backbone of the pipeline (title + summary + image). We download the feed with ``requests``,
under the configured timeout, parse it with ``feedparser``, then use a few dedicated
functions to pull out the associated image — the trickiest part, because it can sit in
several different places of an RSS entry.
"""

from __future__ import annotations

import io

import feedparser
import requests
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

    The feed is downloaded with ``requests``, so the request has the timeout every other HTTP
    call of the pipeline has, and is then handed to ``feedparser``. A request that fails, or
    an HTTP error status, raises ``requests.RequestException``, and :func:`fetch_all_rss`
    turns it into the outcome of the source.
    """
    logger.info("RSS: reading feed '%s' (%s)", source_name, url)
    response = requests.get(
        url, timeout=config.request_timeout, headers={"User-Agent": config.user_agent}
    )
    response.raise_for_status()

    # Wrapped in BytesIO: feedparser treats a bare string as a URL or a file path to open.
    # The two headers are the ones it would have read itself, for the character encoding and
    # for resolving relative links.
    headers = {"content-location": response.url}
    if response.headers.get("Content-Type"):
        headers["content-type"] = response.headers["Content-Type"]
    feed = feedparser.parse(io.BytesIO(response.content), response_headers=headers)

    if feed.bozo:
        logger.warning("RSS: feed '%s' is malformed (%s)", source_name, feed.get("bozo_exception"))

    entries = feed.entries[: config.max_items_per_source]
    records = [_parse_entry(entry, source_name) for entry in entries]
    logger.info("RSS: %d publications collected from '%s'", len(records), source_name)
    return records


def fetch_all_rss(config: ExtractionConfig) -> list[dict[str, object]]:
    """Walk every configured RSS feed and concatenate the results.

    A feed that cannot be read is logged and skipped, and the other feeds are still read.
    If every feed came back without a publication and at least one of them failed, the
    earliest error is raised again; the extract step then counts the source as failed, not
    as empty.
    """
    records: list[dict[str, object]] = []
    failures: list[requests.RequestException] = []
    for source_name, url in config.rss_feeds:
        try:
            records.extend(fetch_rss_feed(source_name, url, config))
        except requests.RequestException as exc:
            logger.error("RSS: could not read feed '%s': %s", source_name, exc)
            failures.append(exc)

    if failures and not records:
        raise failures[0]

    logger.info(
        "RSS: %d publications in total across %d feeds", len(records), len(config.rss_feeds)
    )
    return records
