"""Measure one run, and publish what it produced.

Two steps, on purpose. A corpus assembled from live feeds is never twice the same, so measuring
and publishing under one command would make ``reports/data_quality.md`` a file no reader can
reproduce. ``--measure`` writes the numbers of one named run to two tracked files; the default
run turns the first of them into the markdown, byte for byte, on any machine.

``reports/data_quality.json`` carries what the corpus is worth, in the sense the header of
:mod:`multimodal_etl.quality.report` defines. ``reports/indicators.json`` carries the state of
the pipeline that produced it: the nine indicators of ``docs/protocol.md``, each with the value
this run measured, its unit, the bound it was read against and the side of it the run fell on.
Neither file holds a headline, a URL or an image path. They are counts, and that is what lets
them be published while the corpus itself stays out of the repository.

Usage:
    uv run python scripts/quality_report.py              # render the report from the measures
    uv run python scripts/quality_report.py --measure    # remeasure from the latest dataset
    uv run python scripts/quality_report.py --duplicates # print the duplicate measure only
"""

from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path

from multimodal_etl.kpi import compute_kpis, evaluate_thresholds, load_latest_dataset
from multimodal_etl.quality.duplicates import (
    duplicate_summary,
    missed_duplicates,
    title_summary,
)
from multimodal_etl.quality.report import measure, render
from multimodal_etl.utils.paths import REPORTS_DIR

MEASURES = REPORTS_DIR / "data_quality.json"
INDICATORS = REPORTS_DIR / "indicators.json"
REPORT = REPORTS_DIR / "data_quality.md"


def _write(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline=""
    )
    print(f"[ok] written        : {path.name}")


def remeasure() -> int:
    """Recompute the published numbers from the most recent dataset on disk."""
    df, stats, run = load_latest_dataset()
    if df.empty:
        print("[warn] no dataset found. Run scripts/run_etl.py first.")
        return 1

    measured_on = datetime.now(UTC).date().isoformat()
    _write(
        MEASURES,
        measure(df, stats, duplicate_summary(df), title_summary(df), measured_on=measured_on),
    )
    _write(
        INDICATORS,
        {
            "schema": "run-indicators/1",
            "measured_on": measured_on,
            "orchestrator": str(run.get("orchestrator", "unknown")),
            "indicators": [
                {
                    "indicator": reading["indicator"],
                    "label": reading["label"],
                    "value": reading["value"],
                    "unit": reading["unit"],
                    "healthy_when": reading["expected"],
                    "status": reading["status"],
                }
                for reading in evaluate_thresholds(compute_kpis(df, stats, run))
            ],
        },
    )
    return 0


def publish() -> int:
    """Turn the tracked measures into the published markdown."""
    if not MEASURES.exists():
        print(f"[warn] {MEASURES.name} missing. Run with --measure first.")
        return 1
    measures = json.loads(MEASURES.read_text(encoding="utf-8"))
    REPORT.write_text(render(measures), encoding="utf-8", newline="")
    print(f"[ok] report written : {REPORT.name}")
    print(f"[ok] measured on    : {measures['measured_on']}")
    return 0


def show_duplicates() -> int:
    """Print the duplicate measure against the dataset on disk, writing nothing."""
    df, _stats, _run = load_latest_dataset()
    if df.empty:
        print("[warn] no dataset found. Run scripts/run_etl.py first.")
        return 1
    summary = duplicate_summary(df)
    by_title = title_summary(df)
    print(f"[ok] publications  : {summary['publications']}")
    print(f"[ok] groups missed : {summary['groups']}")
    print(f"[ok] pairs missed  : {summary['missed_pairs']} (by url+title)")
    print(f"[ok] pairs missed  : {by_title['missed_pairs']} (by title alone)")
    for group in missed_duplicates(df)[:10]:
        print(f"     {group['ids']} -> {group['normalised_url'][:70]}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--measure", action="store_true", help="remeasure from the dataset on disk"
    )
    parser.add_argument(
        "--duplicates", action="store_true", help="print the duplicate measure, write nothing"
    )
    arguments = parser.parse_args(argv)

    if arguments.duplicates:
        return show_duplicates()
    if arguments.measure:
        return remeasure()
    return publish()


if __name__ == "__main__":
    raise SystemExit(main())
