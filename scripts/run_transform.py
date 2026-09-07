"""Step 2 on its own — transform.

Picks up the raw file left by the extraction, or failing that the most recent extraction
archived under ``data/raw/``, and writes the tidy dataset to ``data/processed/``.

Usage:
    uv run python scripts/run_transform.py
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from multimodal_etl.logging_setup import setup_logging
from multimodal_etl.pipeline import run_transform


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
