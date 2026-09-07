"""Write the data quality report from the most recent dataset.

Usage:
    uv run python scripts/quality_report.py
    uv run python scripts/quality_report.py --duplicates   # print the measure only
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from multimodal_etl.kpi import load_latest_dataset
from multimodal_etl.quality.duplicates import (
    duplicate_summary,
    missed_duplicates,
    title_summary,
)
from multimodal_etl.quality.report import render_report

OUTPUT = ROOT / "reports" / "data_quality.md"


def main() -> None:
    """Measure the latest dataset and write the report."""
    df, stats, _ = load_latest_dataset()
    if df.empty:
        print("[warn] no dataset found. Run scripts/run_etl.py first.")
        return

    summary = duplicate_summary(df)
    by_title = title_summary(df)

    if "--duplicates" in sys.argv:
        print(f"[ok] publications  : {summary['publications']}")
        print(f"[ok] groups missed : {summary['groups']}")
        print(f"[ok] pairs missed  : {summary['missed_pairs']} (by url+title)")
        print(f"[ok] pairs missed  : {by_title['missed_pairs']} (by title alone)")
        for group in missed_duplicates(df)[:10]:
            print(f"     {group['ids']} -> {group['normalised_url'][:70]}")
        return

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(render_report(df, stats, summary, by_title), encoding="utf-8")
    print(f"[ok] report written : {OUTPUT}")
    print(f"[ok] pairs missed   : {summary['missed_pairs']} on {summary['publications']}")


if __name__ == "__main__":
    main()
