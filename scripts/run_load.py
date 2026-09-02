"""Step 3 on its own — load into the database.

Picks up the dataset left by the transformation, or failing that the most recent dataset
archived under ``data/processed/``, and inserts only the publications that are not there
already.

Usage:
    uv run python scripts/run_load.py
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
    """Load the dataset into the database and print the per-table outcome."""
    setup_logging()
    try:
        metrics = run_load()
    except FileNotFoundError as error:
        print(f"[error] {error}")
        sys.exit(1)

    print(f"[ok] dataset loaded         : {metrics['entree']}")
    print(f"[ok] publications added     : {metrics['publications_ajoutees']}")
    print(f"[ok] publications in database: {metrics['publications_en_base']}")
    print(f"[ok] per table              : {metrics['bilan_tables']}")


if __name__ == "__main__":
    main()
