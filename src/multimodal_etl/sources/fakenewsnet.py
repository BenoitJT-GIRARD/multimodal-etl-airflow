"""Connecteur 3 — FakeNewsNet, jeu de données labellisé hébergé sur GitHub.

FakeNewsNet (Shu *et al.*, 2018) est la référence académique pour la détection de
fake news : chaque publication y porte un **label de vérité terrain** (``real`` /
``fake``) issu de PolitiFact ou de GossipCop. Les fichiers d'index sont publiés en
clair dans le dépôt GitHub officiel, on les récupère donc **directement depuis
GitHub**, sans authentification.

Deux particularités traitées ici, et elles sont typiques du métier :

1. les CSV ne contiennent **ni texte long ni image** — seulement l'identifiant,
   l'URL de l'article et son titre. L'image est donc retrouvée dans les
   métadonnées Open Graph de l'article (cf. :mod:`multimodal_etl.sources.opengraph`) ;
2. la colonne ``tweet_ids`` peut dépasser la taille de champ que le module ``csv``
   accepte par défaut : il faut relever explicitement cette limite.
"""

from __future__ import annotations

import csv
import io
from pathlib import Path

import requests

from multimodal_etl.config import RAW_DIR, ExtractionConfig
from multimodal_etl.logging_setup import get_logger
from multimodal_etl.sources import opengraph

logger = get_logger(__name__)

# Dossier de cache : une fois les CSV téléchargés, les exécutions suivantes sont
# hors-ligne et strictement reproductibles.
CACHE_DIR = RAW_DIR / "fakenewsnet"

# La colonne tweet_ids contient des milliers d'identifiants séparés par des
# tabulations : sans cela, le module csv lève « field larger than field limit ».
csv.field_size_limit(10_000_000)


def _nom_source(fichier: str) -> tuple[str, str]:
    """Déduit l'organisme de vérification et le label du nom de fichier.

    ``politifact_fake.csv`` -> ``("politifact", "fake")``
    """
    tige = Path(fichier).stem
    organisme, _, label = tige.partition("_")
    return organisme, label


def telecharge_csv(fichier: str, config: ExtractionConfig) -> Path | None:
    """Télécharge un CSV FakeNewsNet depuis GitHub, ou renvoie la copie en cache."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    destination = CACHE_DIR / fichier

    if destination.exists():
        logger.info("FakeNewsNet : '%s' déjà en cache", fichier)
        return destination

    url = f"{config.fakenewsnet_base_url}/{fichier}"
    logger.info("FakeNewsNet : téléchargement de %s", url)
    try:
        reponse = requests.get(
            url, timeout=config.request_timeout, headers={"User-Agent": config.user_agent}
        )
        reponse.raise_for_status()
    except requests.RequestException as exc:
        logger.error("FakeNewsNet : téléchargement impossible (%s) : %s", fichier, exc)
        return None

    destination.write_text(reponse.text, encoding="utf-8")
    logger.info("FakeNewsNet : '%s' enregistré (%d octets)", fichier, len(reponse.content))
    return destination


def lit_csv(chemin: Path) -> list[dict[str, str]]:
    """Lit un CSV FakeNewsNet en liste de dictionnaires."""
    contenu = chemin.read_text(encoding="utf-8", errors="replace")
    return list(csv.DictReader(io.StringIO(contenu)))


def _construit_record(ligne: dict[str, str], organisme: str, label: str) -> dict[str, object]:
    """Transforme une ligne FakeNewsNet en dictionnaire brut normalisé."""
    return {
        "source": f"fakenewsnet:{organisme}",
        "source_type": "dataset",
        "access_method": "telechargement_github",
        "title": ligne.get("title", ""),
        # Les CSV n'exposent pas le corps de l'article : le titre porte le signal texte.
        "text": ligne.get("title", ""),
        "url": opengraph.normalise_url(ligne.get("news_url", "")),
        "image_url": "",
        "image_source": "aucune",
        "published_at": "",
        "language": "en",
        "label": label,
        "label_source": f"fakenewsnet:{organisme}",
    }


def fetch_fakenewsnet(config: ExtractionConfig) -> list[dict[str, object]]:
    """Charge les publications labellisées FakeNewsNet et retrouve leurs images.

    On prélève le même nombre de lignes dans chaque fichier afin de garder un
    équilibre entre ``real`` et ``fake`` et entre les deux organismes de
    vérification.
    """
    par_fichier = max(1, config.max_items_per_source // len(config.fakenewsnet_files))
    records: list[dict[str, object]] = []

    for fichier in config.fakenewsnet_files:
        chemin = telecharge_csv(fichier, config)
        if chemin is None:
            continue

        organisme, label = _nom_source(fichier)
        lignes = lit_csv(chemin)[:par_fichier]
        records.extend(_construit_record(ligne, organisme, label) for ligne in lignes)
        logger.info("FakeNewsNet : %d lignes lues dans %s", len(lignes), fichier)

    if not records:
        logger.warning("FakeNewsNet : aucune donnée récupérée.")
        return []

    # Les CSV ne portent pas d'image : on va la chercher chez l'éditeur.
    opengraph.enrichit_publications(records, config)

    logger.info("FakeNewsNet : %d publications labellisées chargées", len(records))
    return records
