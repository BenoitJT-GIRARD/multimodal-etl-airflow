"""Étape E — extraction (collecte des données brutes).

Ce module orchestre les connecteurs de sources, télécharge les images associées,
puis sauvegarde le résultat brut au format JSON dans ``data/raw/``. Il s'exécute
**sans intervention manuelle** : chaque source est isolée dans un try/except, de
sorte qu'une source en panne n'empêche jamais les autres de fonctionner.

Le format de sortie est du **JSON** et non du CSV : une publication multimodale
associe un texte et un **chemin de fichier image**, et le JSON conserve cette
structure sans ambiguïté (le CSV serait suffisant pour du texte seul).
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from multimodal_etl.config import RAW_DIR, ExtractionConfig, ImageConfig, ensure_dirs
from multimodal_etl.images import download_images
from multimodal_etl.logging_setup import get_logger
from multimodal_etl.sources import fakenewsnet, kaggle_fakeddit, newsdata, rss

logger = get_logger(__name__)

# Table des connecteurs : nom logique -> fonction d'extraction. Ajouter une source
# au pipeline revient à écrire un module dans `sources/` et une ligne ici.
_CONNECTEURS = {
    "rss": rss.fetch_all_rss,
    "newsdata": newsdata.fetch_newsdata,
    "fakenewsnet": fakenewsnet.fetch_fakenewsnet,
    "kaggle_fakeddit": kaggle_fakeddit.fetch_fakeddit,
}


def _timestamp() -> str:
    """Horodatage compact pour nommer les fichiers de sortie."""
    return datetime.now(UTC).strftime("%Y%m%d_%H%M%S")


def collect_sources(config: ExtractionConfig | None = None) -> tuple[list[dict], dict[str, int]]:
    """Lance tous les connecteurs et renvoie les publications brutes et le bilan par source.

    Le bilan (nombre de publications par connecteur, ``-1`` en cas d'échec) alimente
    le KPI « sources en échec » du plan de monitoring.
    """
    config = config or ExtractionConfig()
    ensure_dirs()

    publications: list[dict] = []
    bilan: dict[str, int] = {}

    for nom, connecteur in _CONNECTEURS.items():
        logger.info("Extraction : démarrage de la source '%s'", nom)
        try:
            recuperees = connecteur(config)
        except Exception as exc:
            logger.error("Extraction : la source '%s' a échoué : %s", nom, exc)
            bilan[nom] = -1
            continue
        logger.info("Extraction : source '%s' -> %d publications", nom, len(recuperees))
        bilan[nom] = len(recuperees)
        publications.extend(recuperees)

    logger.info("Extraction : %d publications brutes au total", len(publications))
    return publications, bilan


def failed_sources(bilan: dict[str, int]) -> int:
    """Compte les sources réellement en panne, pour l'alerte du plan de monitoring.

    Une source volontairement **désactivée** n'est pas une panne : NewsData.io ne
    s'active que si une clé d'API est fournie, et son absence ne doit pas déclencher
    d'alerte. Sans cette distinction, un pipeline en bonne santé passerait à l'orange
    dès qu'on l'exécute sans clé.
    """
    desactivees = set() if newsdata.is_enabled() else {"newsdata"}
    return sum(1 for nom, nombre in bilan.items() if nombre <= 0 and nom not in desactivees)


def extract_all(config: ExtractionConfig | None = None) -> list[dict]:
    """Collecte les publications de toutes les sources, images comprises."""
    publications, _ = collect_sources(config)
    download_images(publications, ImageConfig())
    return publications


def save_raw(records: list[dict], path: Path | None = None) -> Path:
    """Sauvegarde les publications brutes en JSON et renvoie le chemin du fichier."""
    ensure_dirs()
    path = path or RAW_DIR / f"raw_publications_{_timestamp()}.json"
    with path.open("w", encoding="utf-8") as fichier:
        json.dump(records, fichier, ensure_ascii=False, indent=2)
    logger.info("Extraction : %d publications écrites dans %s", len(records), path)
    return path


def run_extraction(config: ExtractionConfig | None = None) -> tuple[Path, dict[str, object]]:
    """Pipeline d'extraction complet : collecte, images, puis sauvegarde JSON.

    Renvoie le chemin du fichier brut et un compte rendu de l'exécution (bilan par
    source et statistiques de téléchargement d'images), consommé par les KPI.
    """
    publications, bilan = collect_sources(config)
    compteurs_images = download_images(publications, ImageConfig())
    path_for = save_raw(publications)

    compte_rendu: dict[str, object] = {
        "publications_extraites": len(publications),
        "bilan_sources": bilan,
        "failed_sources": failed_sources(bilan),
        "images": compteurs_images,
        "fichier_brut": str(path_for),
    }
    return path_for, compte_rendu
