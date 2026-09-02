"""Étape 1 seule — extraction.

Collecte les publications multimodales des quatre sources, télécharge les images
associées et écrit le résultat en JSON brut dans ``data/raw/``. S'exécute sans
aucune intervention manuelle.

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

from multimodal_etl.logging_setup import setup_logging
from multimodal_etl.pipeline import run_extract


def main() -> None:
    """Lance l'extraction et affiche un résumé de ce qui a été collecté."""
    setup_logging()
    mesures = run_extract()
    images = mesures["images"]

    print(f"[ok] publications extraites : {mesures['publications_extraites']}")
    print(f"[ok] bilan par source       : {mesures['bilan_sources']}")
    print(f"[ok] images téléchargées    : {images['reussies']} (échecs : {images['echouees']})")
    print(f"[ok] fichier brut           : {mesures['archive']}")


if __name__ == "__main__":
    main()
