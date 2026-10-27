"""Step 2 on its own — transform.

Picks up the raw file left by the extraction, or failing that the most recent extraction
archived under ``data/raw/``, and writes the tidy dataset to ``data/processed/``.

Usage:
    uv run python scripts/run_transform.py
"""

from __future__ import annotations

import sys

from dotenv import load_dotenv

from multimodal_etl.utils.paths import ROOT_DIR as ROOT

# `.env` before the package. `scripts/run_etl.py` carries the reason.
load_dotenv(ROOT / ".env")

from multimodal_etl.logging_setup import setup_logging  # noqa: E402
from multimodal_etl.pipeline import run_transform  # noqa: E402


def main() -> None:
    """Transform the raw publications and print a summary."""
    setup_logging()
    try:
        metrics = run_transform()
    except FileNotFoundError as error:
        print(f"[error] {error}")
        sys.exit(1)

    print(f"[ok] file read          : {metrics['input']}")
    print(f"[ok] dataset written    : {metrics['archive']}")
    print(f"[ok] statistics         : {metrics['stats']}")


if __name__ == "__main__":
    main()
