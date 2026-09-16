"""Step 3 on its own — load into the database.

Picks up the dataset left by the transformation, or failing that the most recent dataset
archived under ``data/processed/``, and inserts only the publications that are not there
already.

Usage:
    uv run python scripts/run_load.py
"""

from __future__ import annotations

import sys

from dotenv import load_dotenv

from multimodal_etl.utils.paths import ROOT_DIR as ROOT

# `.env` first, then the package: `scripts/run_etl.py` says why the order is not a style.
load_dotenv(ROOT / ".env")

from multimodal_etl.logging_setup import setup_logging  # noqa: E402
from multimodal_etl.pipeline import run_load  # noqa: E402


def main() -> None:
    """Load the dataset into the database and print the per-table outcome."""
    setup_logging()
    try:
        metrics = run_load()
    except FileNotFoundError as error:
        print(f"[error] {error}")
        sys.exit(1)

    print(f"[ok] dataset loaded         : {metrics['input']}")
    print(f"[ok] publications added     : {metrics['publications_added']}")
    print(f"[ok] publications in database: {metrics['publications_in_db']}")
    print(f"[ok] per table              : {metrics['per_table']}")


if __name__ == "__main__":
    main()
