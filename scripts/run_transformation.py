"""Etape de transformation seule.

Prend le fichier brut le plus recent de ``data/raw/`` (ou un fichier passe en
argument) et produit le dataset propre dans ``data/processed/``.

Usage :
    uv run python scripts/run_transformation.py [chemin/vers/raw.json]
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from multimodal_etl.config import RAW_DIR, TransformConfig
from multimodal_etl.logging_setup import setup_logging
from multimodal_etl.transform import run_transformation


def _dernier_brut() -> Path | None:
    """Renvoie le fichier brut le plus recent de data/raw/."""
    fichiers = sorted(
        RAW_DIR.glob("raw_publications_*.json"), key=lambda p: p.stat().st_mtime, reverse=True
    )
    return fichiers[0] if fichiers else None


def main() -> None:
    """Transforme le fichier brut choisi et affiche un resume."""
    setup_logging()
    raw_path = Path(sys.argv[1]) if len(sys.argv) > 1 else _dernier_brut()
    if raw_path is None or not raw_path.exists():
        print("[erreur] aucun fichier brut trouve — lancez d'abord run_extraction.py")
        sys.exit(1)

    dataset_path, stats = run_transformation(raw_path, TransformConfig())
    print(f"[ok] dataset transforme : {dataset_path}")
    print(f"[ok] statistiques : {stats}")


if __name__ == "__main__":
    main()
