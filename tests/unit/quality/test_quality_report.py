"""Unit tests of the data quality measurement, and of the report rendered from it."""

from __future__ import annotations

import json

import pandas as pd

from multimodal_etl.quality.report import by_source, completeness, measure, render


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


def _measures() -> dict:
    return measure(
        _df(),
        {"raw_total": 5},
        {"publications": 3, "missed_pairs": 0},
        {"missed_pairs": 1},
        measured_on="2026-09-03",
    )


def test_the_measures_carry_the_headline_numbers_and_the_day_they_were_taken() -> None:
    measures = _measures()
    assert measures["collected"] == 5
    assert measures["kept"] == 3
    assert measures["measured_on"] == "2026-09-03"
    assert measures["duplicates"]["missed_pairs_title_only"] == 1


def test_the_measures_carry_no_publication_text() -> None:
    """They are published, and the four sources forbid redistributing their content."""
    serialised = json.dumps(_measures())
    for text in ("some text", "other text", "third", "data/raw/images/a.jpg"):
        assert text not in serialised


def test_the_report_names_every_section_and_survives_an_empty_dataset() -> None:
    markdown = render(_measures())
    for heading in ("Completeness", "By source", "Duplicates"):
        assert heading in markdown
    assert "2026-09-03" in markdown

    empty = render(
        measure(
            pd.DataFrame(),
            {},
            {"publications": 0, "missed_pairs": 0},
            measured_on="2026-09-03",
        )
    )
    assert "no dataset" in empty.lower()


def test_the_report_is_a_function_of_the_measures_and_of_nothing_else() -> None:
    """Rendering twice from the same record gives the same bytes, on any machine."""
    assert render(_measures()) == render(_measures())
