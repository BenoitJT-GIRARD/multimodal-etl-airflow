"""Smoke test of the dashboard.

The dashboard is a public surface: it has to open without error. Streamlit ships a helper
that runs the application without a browser and reports the exceptions — the simplest way
to check the page really builds.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from multimodal_etl.config import PROJECT_ROOT

APPLICATION = PROJECT_ROOT / "dashboard" / "app.py"


def _run() -> AppTest:
    application = AppTest.from_file(str(APPLICATION), default_timeout=120)
    application.run()
    return application


def test_the_dashboard_builds_without_error() -> None:
    application = _run()
    assert not application.exception, [str(e) for e in application.exception]


def test_the_dashboard_renders_its_sections() -> None:
    if not list((PROJECT_ROOT / "data" / "processed").glob("publications_*_stats.json")):
        pytest.skip("no dataset produced: run scripts/run_etl.py first")

    application = _run()
    titles = [element.value for element in application.subheader]

    assert "Pipeline status" in titles
    assert "Data quality" in titles
    # The KPI cards are present (quality, volume, performance).
    assert len(application.metric) >= 12


def test_the_dashboard_file_exists() -> None:
    assert Path(APPLICATION).is_file()
