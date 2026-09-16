"""The real Streamlit application object, run against a dataset this test writes.

Streamlit ships a harness that builds the page without a browser and reports the exceptions.
It is the real application — the module, its callbacks, its charts — wired to real artefacts
on disk, which is what makes this an integration test and not a unit one.

The dataset is built here, and never read from ``data/``. The version this replaces skipped
whenever no run had been done, so on a fresh checkout — and in CI — the only dashboard test
that opened a section never ran at all.
"""

from __future__ import annotations

import importlib
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest

from multimodal_etl.utils.paths import ROOT_DIR

pytestmark = pytest.mark.integration

APPLICATION = ROOT_DIR / "src" / "multimodal_etl" / "dashboard.py"

#: Two runs, so the history section has a trend to draw and not an information box.
RUNS = 2


def _publications(count: int) -> pd.DataFrame:
    now = datetime.now(UTC)
    return pd.DataFrame(
        [
            {
                "id": f"pub{index}",
                "source_id": "src_rss",
                "source": "rss:bbc_news" if index % 2 else "kaggle_fakeddit",
                "source_type": "rss",
                "access_method": "rss_feed",
                "domain": "bbc.co.uk",
                "url": f"https://example.invalid/{index}",
                "language": "en",
                "published_at": (now - timedelta(hours=index)).isoformat(),
                "ingested_at": now.isoformat(),
                "title": f"A headline number {index}",
                "text": "A body long enough to pass the minimum length check." * 2,
                "text_length": 104,
                "image_url": f"https://example.invalid/{index}.jpg",
                "image_path": f"data/raw/images/{index}.jpg",
                "image_source": "native",
                "has_image": True,
                "label": "fake" if index % 3 == 0 else None,
                "label_source": "fakenewsnet:politifact" if index % 3 == 0 else None,
            }
            for index in range(count)
        ]
    )


def _run_record(index: int, extracted: int, kept: int) -> dict:
    return {
        "run_at": (datetime.now(UTC) - timedelta(days=RUNS - index)).isoformat(timespec="seconds"),
        "orchestrator": "script",
        "durations_sec": {"extract": 30.0, "transform": 4.0, "load": 2.0},
        "rows_extracted": extracted,
        "rows_loaded": kept,
        "rows_in_db": kept * (index + 1),
        "api_calls": 0,
        "per_source": {
            "rss": {"count": extracted - 4, "cause": "ok"},
            "newsdata": {"count": 0, "cause": "disabled"},
            "fakenewsnet": {"count": 4, "cause": "ok"},
            "kaggle_fakeddit": {"count": 0, "cause": "empty"},
        },
        "failed_sources": 0,
        "images": {"attempted": extracted, "succeeded": kept, "bytes": 1024 * 1024},
        "stats": {"raw_total": extracted, "valid_total": kept, "duplicates": 1},
    }


@pytest.fixture
def dataset(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A complete set of artefacts, in a data directory of this test's own."""
    monkeypatch.setenv("MULTIMODAL_ETL_DATA_DIR", str(tmp_path))
    # The application imports the paths at module scope, so the modules that hold them are
    # rebuilt before the page is: setting the variable afterwards would change nothing.
    from multimodal_etl import config, kpi

    importlib.reload(config)
    importlib.reload(kpi)

    processed = tmp_path / "processed"
    (processed / "runs").mkdir(parents=True)
    frame = _publications(24)
    frame.to_parquet(processed / "publications_20260101_000000.parquet")
    (processed / "publications_20260101_000000_stats.json").write_text(
        json.dumps({"raw_total": 36, "valid_total": 24, "duplicates": 1}), encoding="utf-8"
    )
    for index in range(RUNS):
        (processed / "runs" / f"run_2026010{index + 1}_000000.json").write_text(
            json.dumps(_run_record(index, 36, 24)), encoding="utf-8"
        )
    yield tmp_path
    monkeypatch.delenv("MULTIMODAL_ETL_DATA_DIR", raising=False)
    importlib.reload(config)
    importlib.reload(kpi)


def _run() -> AppTest:
    application = AppTest.from_file(str(APPLICATION), default_timeout=120)
    application.run()
    return application


def test_the_dashboard_builds_without_error(dataset: Path) -> None:
    application = _run()
    assert not application.exception, [str(e) for e in application.exception]


def test_the_dashboard_renders_every_section(dataset: Path) -> None:
    application = _run()
    titles = [element.value for element in application.subheader]

    assert titles == [
        "Pipeline status",
        "Data quality",
        "Volume, freshness and cost",
        "Run performance",
        "Run history",
        "What the pipeline produces",
    ]
    # Four cards in each of the three families.
    assert len(application.metric) == 12


def test_every_card_carries_its_unit(dataset: Path) -> None:
    """A dashboard whose cards read « 96.9 » leaves the reader to guess the unit."""
    application = _run()
    unitless = [
        card.value
        for card in application.metric
        if card.value.rstrip().rstrip("0123456789.") == ""
    ]
    assert not unitless, f"cards with a bare number: {unitless}"


def test_the_status_of_an_indicator_is_a_word_and_not_only_a_colour(dataset: Path) -> None:
    application = _run()
    status = application.dataframe[0].value["Status"].tolist()

    assert set(status) <= {"within bounds", "watch", "act now"}
    assert "Healthy when" in application.dataframe[0].value.columns


def test_the_page_says_what_to_run_when_there_is_no_dataset(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An empty page that says nothing reads as a broken dashboard."""
    monkeypatch.setenv("MULTIMODAL_ETL_DATA_DIR", str(tmp_path / "empty"))
    from multimodal_etl import config, kpi

    importlib.reload(config)
    importlib.reload(kpi)
    try:
        application = _run()
        assert not application.exception
        assert "scripts/run_etl.py" in application.warning[0].value
    finally:
        monkeypatch.delenv("MULTIMODAL_ETL_DATA_DIR", raising=False)
        importlib.reload(config)
        importlib.reload(kpi)
