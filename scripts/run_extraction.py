"""Etape d'extraction seule.

Collecte les publications multimodales depuis les trois sources et les ecrit en
JSON brut dans ``data/raw/``. S'execute sans aucune intervention manuelle.

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
    """Lance l'extraction et affiche le chemin du fichier brut produit."""
    setup_logging()
    raw_path = run_extraction(ExtractionConfig())
    print(f"[ok] publications brutes ecrites : {raw_path}")


if __name__ == "__main__":
    main()
