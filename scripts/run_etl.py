"""The whole ETL, in one command.

Runs the five steps — extract, transform, load, metrics, cleanup — in the same order as
the Airflow DAG and **calling exactly the same functions**. This is the reference script
version: it is how the pipeline gets validated before being orchestrated.

Usage:
    uv run python scripts/run_etl.py
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from dotenv import load_dotenv

load_dotenv(ROOT / ".env")

from multimodal_etl.logging_setup import get_logger, setup_logging
from multimodal_etl.pipeline import (
    run_cleanup,
    run_extract,
    run_load,
    run_metrics,
    run_transform,
)

logger = get_logger("multimodal_etl.etl")


def main() -> None:
    """Run the ETL end to end and print what the run did."""
    setup_logging()

    run_extract()
    run_transform()
    run_load()
    run = run_metrics(orchestrator="script")
    run_cleanup()

    elapsed = sum(run["durations_sec"].values())
    logger.info("ETL finished: %d new publications in %.2fs", run["rows_loaded"], elapsed)

    print(f"[ok] publications extracted : {run['rows_extracted']}")
    print(f"[ok] new in database        : {run['rows_loaded']}")
    print(f"[ok] total in database      : {run['rows_in_db']}")
    print(f"[ok] total duration         : {elapsed:.2f} s")
    print(f"[ok] run record             : {run['file']}")


if __name__ == "__main__":
    main()
