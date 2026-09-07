"""Unit tests of the data quality report."""

from __future__ import annotations

import pandas as pd

from multimodal_etl.quality.report import by_source, completeness, render_report


def _df() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "source": "rss:bbc",
                "title": "A",
                "text": "some text",
                "text_length": 9,
                "image_path": "data/raw/images/a.jpg",
                "has_image": True,
                "label": "fake",
                "published_at": "2026-09-01T10:00:00+00:00",
            },
            {
                "source": "rss:bbc",
                "title": "B",
                "text": "other text",
                "text_length": 10,
                "image_path": "",
                "has_image": False,
                "label": None,
                "published_at": None,
            },
            {
                "source": "fakeddit",
                "title": "C",
                "text": "third",
                "text_length": 5,
                "image_path": "data/raw/images/c.jpg",
                "has_image": True,
                "label": "real",
                "published_at": "2026-09-02T10:00:00+00:00",
            },
        ]
    )


def test_completeness_counts_an_empty_string_as_missing() -> None:
    table = completeness(_df()).set_index("field")
    # image_path is filled twice out of three: the empty string is not a value.
    assert table.loc["image_path", "filled"] == 2
    assert table.loc["image_path", "filled_pct"] == 66.7
    assert table.loc["title", "filled"] == 3


def test_completeness_counts_null_as_missing() -> None:
    table = completeness(_df()).set_index("field")
    assert table.loc["label", "filled"] == 2
    assert table.loc["published_at", "filled"] == 2


def test_by_source_reports_what_each_source_really_contributes() -> None:
    table = by_source(_df()).set_index("source")

    assert table.loc["rss:bbc", "publications"] == 2
    assert table.loc["rss:bbc", "with_image"] == 1
    assert table.loc["rss:bbc", "labelled"] == 1
    assert table.loc["fakeddit", "with_image"] == 1


def test_the_report_names_every_section_and_survives_an_empty_dataset() -> None:
    markdown = render_report(_df(), {"raw_total": 5}, {"publications": 3, "missed_pairs": 0})
    for heading in ("Completeness", "By source", "Duplicates"):
        assert heading in markdown

    empty = render_report(pd.DataFrame(), {}, {"publications": 0, "missed_pairs": 0})
    assert "no dataset" in empty.lower()
