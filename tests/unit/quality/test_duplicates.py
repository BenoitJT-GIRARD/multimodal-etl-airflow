"""Unit tests of the duplicate measurement."""

from __future__ import annotations

import pandas as pd

from multimodal_etl.quality.duplicates import (
    duplicate_summary,
    missed_by_title,
    missed_duplicates,
    normalise_title,
    normalise_url,
    title_summary,
)


def test_tracking_parameters_do_not_change_the_normalised_url() -> None:
    plain = normalise_url("https://site.com/a")
    assert normalise_url("https://Site.com/a/?utm_source=x&utm_medium=y") == plain
    assert normalise_url("http://www.site.com/a") == plain


def test_a_meaningful_query_parameter_is_kept() -> None:
    # Dropping every parameter would merge genuinely different articles.
    assert normalise_url("https://site.com/a?id=1") != normalise_url("https://site.com/a?id=2")


def test_normalise_title_ignores_case_punctuation_and_spacing() -> None:
    assert normalise_title("A  Headline!") == normalise_title("a headline")
    assert normalise_title("Two words") != normalise_title("two other words")


def test_two_records_of_the_same_article_are_reported_as_missed() -> None:
    df = pd.DataFrame(
        [
            {"id": "1", "url": "https://site.com/a?utm_source=rss", "title": "A Headline"},
            {"id": "2", "url": "https://site.com/a/", "title": "A  headline!"},
            {"id": "3", "url": "https://site.com/b", "title": "Another"},
        ]
    )
    missed = missed_duplicates(df)

    assert len(missed) == 1
    assert sorted(missed[0]["ids"]) == ["1", "2"]


def test_the_summary_counts_pairs_not_groups() -> None:
    # Three records of the same article are three pairs, not one.
    df = pd.DataFrame(
        [
            {"id": "1", "url": "https://site.com/a", "title": "T"},
            {"id": "2", "url": "https://site.com/a/", "title": "t"},
            {"id": "3", "url": "https://www.site.com/a", "title": "T!"},
            {"id": "4", "url": "https://site.com/b", "title": "Other"},
        ]
    )
    summary = duplicate_summary(df)

    assert summary["publications"] == 4
    assert summary["groups"] == 1
    assert summary["missed_pairs"] == 3


def test_an_empty_dataset_measures_zero() -> None:
    summary = duplicate_summary(pd.DataFrame(columns=["id", "url", "title"]))
    assert summary == {"publications": 0, "groups": 0, "missed_pairs": 0}


def test_the_measure_catches_a_realistic_republication() -> None:
    """A zero has to mean "nothing there", never "the instrument is blind".

    The twin is what another feed republishing the same article looks like: tracking
    parameters appended, a www. prefix, the headline shouted and punctuated.
    """
    original = {
        "id": "abc",
        "url": "https://theguardian.com/world/2026/sep/02/some-article",
        "title": "New constitution will undermine democracy",
    }
    twin = {
        "id": "def",
        "url": "https://www.theguardian.com/world/2026/sep/02/some-article/?utm_source=rss",
        "title": "NEW CONSTITUTION WILL UNDERMINE DEMOCRACY!",
    }
    df = pd.DataFrame([original, twin, {"id": "ghi", "url": "https://x.com/b", "title": "Other"}])

    assert duplicate_summary(df)["missed_pairs"] == 1
    assert title_summary(df)["missed_pairs"] == 1
    assert sorted(missed_duplicates(df)[0]["ids"]) == ["abc", "def"]


def test_the_title_measure_reaches_across_publishers() -> None:
    # Two outlets, two genuinely different URLs: no URL normalisation can merge them.
    df = pd.DataFrame(
        [
            {"id": "1", "url": "https://bbc.co.uk/news/a", "title": "Same wire story"},
            {"id": "2", "url": "https://theguardian.com/world/b", "title": "Same wire story"},
        ]
    )
    assert duplicate_summary(df)["missed_pairs"] == 0
    assert title_summary(df)["missed_pairs"] == 1
    assert sorted(missed_by_title(df)[0]["ids"]) == ["1", "2"]
