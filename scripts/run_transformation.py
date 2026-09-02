"""Étape 2 seule — transformation.

Reprend le fichier brut déposé par l'extraction (ou, à défaut, la dernière
extraction archivée dans ``data/raw/``) et produit le dataset propre dans
``data/processed/``.

Usage :
    uv run python scripts/run_transformation.py
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from multimodal_etl.logging_setup import setup_logging
from multimodal_etl.pipeline import run_transform


def main() -> None:
    """Transforme les publications brutes et affiche un résumé."""
    setup_logging()
    try:
        mesures = run_transform()
    except FileNotFoundError as erreur:
        print(f"[erreur] {erreur}")
        sys.exit(1)

    print(f"[ok] fichier lu          : {mesures['entree']}")
    print(f"[ok] dataset transformé  : {mesures['archive']}")
    print(f"[ok] statistiques        : {mesures['stats']}")


if __name__ == "__main__":
    main()
