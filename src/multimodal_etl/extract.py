"""Etape E — extraction (collecte des donnees brutes).

Ce module orchestre les trois connecteurs (RSS, NewsData.io, FakeNewsNet) et
sauvegarde le resultat brut au format JSON dans ``data/raw/``. Il s'execute
**sans intervention manuelle** : chaque source est isolee dans un try/except,
de sorte qu'une source en panne n'empeche jamais les autres de fonctionner.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from multimodal_etl.config import RAW_DIR, ExtractionConfig, ensure_dirs
from multimodal_etl.logging_setup import get_logger
from multimodal_etl.sources import newsdata, rss
from multimodal_etl.sources.fakenewsnet import fetch_fakenewsnet

logger = get_logger(__name__)

# Table des connecteurs : nom logique -> fonction d'extraction.
_CONNECTORS = {
    "rss": rss.fetch_all_rss,
    "newsdata": newsdata.fetch_newsdata,
    "fakenewsnet": fetch_fakenewsnet,
}


def _timestamp() -> str:
    """Horodatage compact pour nommer les fichiers de sortie."""
    return datetime.now(UTC).strftime("%Y%m%d_%H%M%S")


def extract_all(config: ExtractionConfig | None = None) -> list[dict[str, object]]:
    """Lance tous les connecteurs et renvoie la liste agregee des publications brutes."""
    config = config or ExtractionConfig()
    ensure_dirs()

    all_records: list[dict[str, object]] = []
    for name, connector in _CONNECTORS.items():
        logger.info("Extraction : demarrage de la source '%s'", name)
        try:
            records = connector(config)
        except Exception as exc:
            logger.error("Extraction : la source '%s' a echoue : %s", name, exc)
            records = []
        logger.info("Extraction : source '%s' -> %d publications", name, len(records))
        all_records.extend(records)

    logger.info("Extraction : %d publications brutes au total", len(all_records))
    return all_records


def save_raw(records: list[dict[str, object]], path: Path | None = None) -> Path:
    """Sauvegarde les publications brutes en JSON et renvoie le chemin du fichier."""
    ensure_dirs()
    path = path or RAW_DIR / f"raw_publications_{_timestamp()}.json"
    with path.open("w", encoding="utf-8") as handle:
        json.dump(records, handle, ensure_ascii=False, indent=2)
    logger.info("Extraction : %d publications ecrites dans %s", len(records), path)
    return path


def run_extraction(config: ExtractionConfig | None = None) -> Path:
    """Pipeline d'extraction complet : collecte puis sauvegarde JSON."""
    records = extract_all(config)
    return save_raw(records)
