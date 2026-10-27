"""Connector 2 — the NewsData.io API.

NewsData.io exposes a REST endpoint returning news articles as JSON, with an
``image_url`` field that is directly usable (multimodal data). The source only turns on
when a ``NEWSDATA_API_KEY`` is present in the environment: without a key the connector
disables itself cleanly and the pipeline carries on with the other sources.
"""

from __future__ import annotations

import os

import requests

from multimodal_etl.config import ExtractionConfig
from multimodal_etl.logging_setup import get_logger

logger = get_logger(__name__)


def is_enabled() -> bool:
    """Say whether the API key is available, i.e. whether the source can run."""
    return bool(os.environ.get("NEWSDATA_API_KEY", "").strip())


def _parse_article(article: dict[str, object]) -> dict[str, object]:
    """Turn a NewsData.io article into a normalised raw dictionary."""
    image_url = article.get("image_url") or ""
    return {
        "source": "newsdata",
        "source_type": "api",
        "access_method": "rest_api",
        "title": article.get("title") or "",
        "text": article.get("description") or article.get("content") or "",
        "url": article.get("link") or "",
        "image_url": image_url,
        "image_source": "native" if image_url else "none",
        "published_at": article.get("pubDate") or "",
        "language": article.get("language") or "en",
        # NewsData.io provides no reliable true/false label.
        "label": None,
        "label_source": None,
    }


def fetch_newsdata(config: ExtractionConfig) -> list[dict[str, object]]:
    """Query the NewsData.io API and return the articles that carry an image.

    Call limits are handled explicitly: we read a single page — the free tier caps a
    request at 10 articles and enforces a daily quota — and we set a timeout. A failure is
    raised for the extract step to classify: a network error or an HTTP error status as a
    ``requests.RequestException`` (the extract step reads a 429 status as a spent quota), an
    answer that is not JSON as ``requests.exceptions.JSONDecodeError``, and a payload that
    reports an error as a ``ValueError``.
    """
    api_key = os.environ.get("NEWSDATA_API_KEY", "").strip()
    if not api_key:
        logger.info("NewsData.io: no API key, source skipped.")
        return []

    params = {
        "language": config.newsdata_language,
        "image": 1,  # only ask for articles that have an image (multimodal)
    }
    logger.info("NewsData.io: calling the API (%s)", config.newsdata_endpoint)
    # The key goes in the X-ACCESS-KEY header, which the API documents as its recommended
    # method. Passed as the `apikey` query parameter, it was part of the URL that requests
    # quotes in every HTTP error, and the extract step writes that message to the logs.
    response = requests.get(
        config.newsdata_endpoint,
        params=params,
        timeout=config.request_timeout,
        headers={"User-Agent": config.user_agent, "X-ACCESS-KEY": api_key},
    )
    response.raise_for_status()

    payload = response.json()
    if payload.get("status") != "success":
        raise ValueError(f"NewsData.io reported an error: {payload.get('results')}")

    articles = payload.get("results", [])[: config.max_items_per_source]
    records = [_parse_article(article) for article in articles]
    logger.info("NewsData.io: %d articles collected", len(records))
    return records
