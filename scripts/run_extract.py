"""Step 1 on its own — extract.

Collects multimodal publications from the four sources, downloads the images that go with
them, and writes the raw result as JSON under ``data/raw/``. Runs unattended.

Usage:
    uv run python scripts/run_extract.py
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
    """Run the extraction and print a summary of what was collected."""
    setup_logging()
    metrics = run_extract()
    images = metrics["images"]

    print(f"[ok] publications extracted : {metrics['publications_extracted']}")
    print(f"[ok] per source             : {metrics['per_source']}")
    print(f"[ok] images downloaded      : {images['succeeded']} (failed: {images['failed']})")
    print(f"[ok] raw file               : {metrics['archive']}")


if __name__ == "__main__":
    main()
