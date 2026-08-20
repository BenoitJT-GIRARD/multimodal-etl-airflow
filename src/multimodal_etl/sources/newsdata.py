"""Connecteur 2 — API NewsData.io.

NewsData.io expose un point d'API REST renvoyant des articles d'actualite au
format JSON, avec un champ ``image_url`` directement exploitable (donnee
multimodale). La source n'est activee que si une cle ``NEWSDATA_API_KEY`` est
presente dans l'environnement : sans cle, le connecteur se desactive proprement
et le pipeline continue avec les autres sources.
"""

from __future__ import annotations

import os

import requests

from multimodal_etl.config import ExtractionConfig
from multimodal_etl.logging_setup import get_logger

logger = get_logger(__name__)


def is_enabled() -> bool:
    """Indique si la cle API est disponible (source activable)."""
    return bool(os.environ.get("NEWSDATA_API_KEY", "").strip())


def _parse_article(article: dict[str, object]) -> dict[str, object]:
    """Transforme un article NewsData.io en dictionnaire brut normalisé."""
    image_url = article.get("image_url") or ""
    return {
        "source": "newsdata",
        "source_type": "api",
        "access_method": "api_rest",
        "title": article.get("title") or "",
        "text": article.get("description") or article.get("content") or "",
        "url": article.get("link") or "",
        "image_url": image_url,
        "image_source": "native" if image_url else "aucune",
        "published_at": article.get("pubDate") or "",
        "language": article.get("language") or "en",
        # NewsData.io ne fournit pas de label vrai/faux fiable.
        "label": None,
        "label_source": None,
    }


def fetch_newsdata(config: ExtractionConfig) -> list[dict[str, object]]:
    """Interroge l'API NewsData.io et renvoie les articles porteurs d'image.

    Gestion explicite des limites d'appel : on lit une seule page (le palier
    gratuit est limite a 10 articles par requete et a un quota journalier), on
    pose un timeout, et on capture toute erreur reseau ou HTTP.
    """
    api_key = os.environ.get("NEWSDATA_API_KEY", "").strip()
    if not api_key:
        logger.info("NewsData.io : aucune cle API, source ignoree.")
        return []

    params = {
        "apikey": api_key,
        "language": config.newsdata_language,
        "image": 1,  # ne demande que des articles avec image (multimodal)
    }
    logger.info("NewsData.io : appel de l'API (%s)", config.newsdata_endpoint)
    try:
        response = requests.get(
            config.newsdata_endpoint,
            params=params,
            timeout=config.request_timeout,
            headers={"User-Agent": config.user_agent},
        )
        response.raise_for_status()
    except requests.RequestException as exc:
        logger.error("NewsData.io : echec de l'appel API : %s", exc)
        return []

    payload = response.json()
    if payload.get("status") != "success":
        logger.warning("NewsData.io : reponse en erreur : %s", payload.get("results"))
        return []

    articles = payload.get("results", [])[: config.max_items_per_source]
    records = [_parse_article(article) for article in articles]
    logger.info("NewsData.io : %d articles recuperes", len(records))
    return records
