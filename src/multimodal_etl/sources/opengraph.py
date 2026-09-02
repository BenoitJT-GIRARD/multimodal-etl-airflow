"""Enrichissement multimodal — récupération de l'image d'un article.

Certaines sources fournissent un texte labellisé mais **aucune image** : les CSV
de FakeNewsNet, par exemple, ne contiennent que l'identifiant, le titre et l'URL
de l'article. Pour rendre ces publications exploitables par un modèle multimodal,
on va lire l'image que l'éditeur déclare lui-même dans les métadonnées
`Open Graph <https://ogp.me/>`_ de sa page (balise ``og:image``).

Ce n'est pas du scraping de contenu : la balise ``og:image`` est précisément
publiée par l'éditeur pour que les réseaux sociaux et les agrégateurs affichent
son article. On ne lit qu'elle, et une seule fois par publication.
"""

from __future__ import annotations

import requests
from bs4 import BeautifulSoup

from multimodal_etl.config import ExtractionConfig
from multimodal_etl.logging_setup import get_logger

logger = get_logger(__name__)


def normalise_url(url: str) -> str:
    """Ajoute le schéma HTTP aux URL qui n'en ont pas (fréquent dans FakeNewsNet)."""
    url = url.strip()
    if not url:
        return ""
    if url.startswith(("http://", "https://")):
        return url
    return f"https://{url}"


def read_open_graph_image(url: str, config: ExtractionConfig) -> str:
    """Renvoie l'URL de l'image ``og:image`` d'une page, ou une chaîne clear.

    Toute erreur (page disparue, délai dépassé, HTML inattendu) est journalisée et
    renvoie une chaîne clear : une publication sans image sera simplement écartée
    plus loin, sans jamais interrompre l'extraction.
    """
    url = normalise_url(url)
    if not url:
        return ""

    try:
        reponse = requests.get(
            url,
            timeout=config.request_timeout,
            headers={"User-Agent": config.user_agent},
        )
        reponse.raise_for_status()
    except requests.RequestException as exc:
        logger.debug("Open Graph : page inaccessible (%s) : %s", url[:70], exc)
        return ""

    soup = BeautifulSoup(reponse.text, "lxml")
    balise = soup.find("meta", property="og:image")
    if balise is None or not balise.get("content"):
        return ""
    return str(balise["content"]).strip()


def enrich_publications(
    records: list[dict[str, object]], config: ExtractionConfig
) -> dict[str, int]:
    """Complète les publications dépourvues d'image en lisant leurs métadonnées.

    Le nombre de pages interrogées est plafonné par
    ``config.max_enrichissements_open_graph`` : chaque enrichissement coûte une
    requête HTTP, et on veut garder une exécution de pipeline courte.
    """
    compteurs = {"tentees": 0, "trouvees": 0}

    for record in records:
        if record.get("image_url"):
            continue
        if compteurs["tentees"] >= config.max_enrichissements_open_graph:
            break

        compteurs["tentees"] += 1
        image_url = read_open_graph_image(str(record.get("url", "")), config)
        if image_url:
            record["image_url"] = image_url
            record["image_source"] = "open_graph"
            compteurs["trouvees"] += 1

    if compteurs["tentees"]:
        logger.info(
            "Open Graph : %d images retrouvées sur %d articles consultés",
            compteurs["trouvees"],
            compteurs["tentees"],
        )
    return compteurs
