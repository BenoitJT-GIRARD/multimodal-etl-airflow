"""Étape 3 seule — chargement en base.

Reprend le dataset déposé par la transformation (ou, à défaut, le dernier dataset
archivé dans ``data/processed/``) et n'ajoute en base que les publications encore
absentes.

Usage :
    uv run python scripts/run_chargement.py
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from dotenv import load_dotenv

load_dotenv(ROOT / ".env")

from multimodal_etl.logging_setup import setup_logging
from multimodal_etl.pipeline import run_load


def main() -> None:
    """Charge le dataset en base et affiche le bilan par table."""
    setup_logging()
    try:
        mesures = run_load()
    except FileNotFoundError as erreur:
        print(f"[erreur] {erreur}")
        sys.exit(1)

    print(f"[ok] dataset chargé          : {mesures['entree']}")
    print(f"[ok] publications ajoutées   : {mesures['publications_ajoutees']}")
    print(f"[ok] publications en base    : {mesures['publications_en_base']}")
    print(f"[ok] bilan par table         : {mesures['bilan_tables']}")


if __name__ == "__main__":
    main()
