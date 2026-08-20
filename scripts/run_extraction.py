"""Étape d'extraction seule.

Collecte les publications multimodales depuis les quatre sources, télécharge les
images associées et écrit le résultat en JSON brut dans ``data/raw/``. S'exécute
sans aucune intervention manuelle.

Usage :
    uv run python scripts/run_extraction.py
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from dotenv import load_dotenv

load_dotenv(ROOT / ".env")

from multimodal_etl.config import ExtractionConfig
from multimodal_etl.extract import run_extraction
from multimodal_etl.logging_setup import setup_logging


def main() -> None:
    """Lance l'extraction et affiche un résumé de ce qui a été collecté."""
    setup_logging()
    chemin, compte_rendu = run_extraction(ExtractionConfig())
    images = compte_rendu["images"]

    print(f"[ok] publications brutes écrites : {chemin}")
    print(f"[ok] publications extraites : {compte_rendu['publications_extraites']}")
    print(f"[ok] bilan par source : {compte_rendu['bilan_sources']}")
    print(f"[ok] images téléchargées : {images['reussies']} (échecs : {images['echouees']})")


if __name__ == "__main__":
    main()
