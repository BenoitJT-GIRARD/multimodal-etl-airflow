"""Multimodal enrichment — fetching an article's image.

Some sources supply labelled text but **no image**: the FakeNewsNet CSVs, for one, hold
nothing but the identifier, the title and the article URL. To make those publications
usable by a multimodal model, we read the image the publisher declares itself in the
`Open Graph <https://ogp.me/>`_ metadata of its page (the ``og:image`` tag).

This is not content scraping: the ``og:image`` tag is published precisely so that social
networks and aggregators can display the article. We read that tag and nothing else, once
per publication.
"""

from __future__ import annotations

import requests
from bs4 import BeautifulSoup

from multimodal_etl.config import ExtractionConfig
from multimodal_etl.logging_setup import get_logger

logger = get_logger(__name__)


def normalise_url(url: str) -> str:
    """Add the HTTP scheme to URLs that lack one (common in FakeNewsNet)."""
    url = url.strip()
    if not url:
        return ""
    if url.startswith(("http://", "https://")):
        return url
    return f"https://{url}"


def read_open_graph_image(url: str, config: ExtractionConfig) -> str:
    """Return the ``og:image`` URL of a page, or an empty string.

    Every error — page gone, timeout, unexpected HTML — is logged and returns an empty
    string: a publication without an image is simply dropped further down, and the
    extraction is never interrupted.
    """
    url = normalise_url(url)
    if not url:
        return ""

    try:
        response = requests.get(
            url,
            timeout=config.request_timeout,
            headers={"User-Agent": config.user_agent},
        )
        response.raise_for_status()
    except requests.RequestException as exc:
        logger.debug("Open Graph: page unreachable (%s): %s", url[:70], exc)
        return ""

    soup = BeautifulSoup(response.text, "lxml")
    tag = soup.find("meta", property="og:image")
    if tag is None or not tag.get("content"):
        return ""
    return str(tag["content"]).strip()


def enrich_publications(
    records: list[dict[str, object]], config: ExtractionConfig
) -> dict[str, int]:
    """Fill in the publications that have no image by reading their metadata.

    The number of pages queried is capped by ``config.max_open_graph_enrichments``: every
    enrichment costs one HTTP request, and we want a pipeline run to stay short.
    """
    counts = {"tentees": 0, "trouvees": 0}

    for record in records:
        if record.get("image_url"):
            continue
        if counts["tentees"] >= config.max_open_graph_enrichments:
            break

        counts["tentees"] += 1
        image_url = read_open_graph_image(str(record.get("url", "")), config)
        if image_url:
            record["image_url"] = image_url
            record["image_source"] = "open_graph"
            counts["trouvees"] += 1

    if counts["tentees"]:
        logger.info(
            "Open Graph: %d images recovered across %d articles visited",
            counts["trouvees"],
            counts["tentees"],
        )
    return counts
