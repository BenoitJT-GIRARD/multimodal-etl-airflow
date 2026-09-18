"""What fraction of the collected dataset is actually usable.

The KPIs answer "is the pipeline healthy". This answers the question a team about to train on
the output asks first: **how much of what you collected is usable, and usable for what?** A row
count alone settles nothing, since a publication with no image is dead weight for a multimodal
model and one with no label is dead weight for supervised training.

Measuring and writing are two steps, and they are separate on purpose. The sources are live,
so the corpus a run collects today is not the corpus of the run whose figures are published;
:func:`measure` therefore writes its numbers to ``reports/data_quality.json``, and
:func:`render` turns **that file** into ``reports/data_quality.md``. The published report is
then reproducible byte for byte from a tracked file, without redistributing a single
publisher's headline — the measures are counts, never content.
"""

from __future__ import annotations

from typing import Any

import pandas as pd

#: Fields worth reporting on: the ones a downstream consumer would filter by.
_REPORTED = (
    "title",
    "text",
    "image_path",
    "image_url",
    "label",
    "label_source",
    "published_at",
    "domain",
    "language",
)

SCHEMA = "data-quality/1"


def _filled(series: pd.Series) -> int:
    """Count the values that are genuinely there: an empty string is not a value."""
    present = series.notna()
    non_empty = series.astype(str).str.strip().ne("")
    return int((present & non_empty).sum())


def completeness(df: pd.DataFrame) -> pd.DataFrame:
    """Report, field by field, how many rows carry a real value."""
    rows = []
    for field in _REPORTED:
        if field not in df.columns:
            continue
        filled = _filled(df[field])
        rows.append(
            {
                "field": field,
                "filled": filled,
                "filled_pct": round(100.0 * filled / len(df), 1) if len(df) else 0.0,
            }
        )
    return pd.DataFrame(rows, columns=["field", "filled", "filled_pct"])


def by_source(df: pd.DataFrame) -> pd.DataFrame:
    """Report what each source really contributes, not just how much."""
    if df.empty:
        return pd.DataFrame(columns=["source", "publications", "with_image", "labelled"])

    grouped = df.groupby("source")
    table = pd.DataFrame(
        {
            "publications": grouped.size(),
            "with_image": grouped["has_image"].sum().astype(int),
            "labelled": grouped["label"].apply(_filled),
            "mean_text_length": grouped["text_length"].mean().round(0).astype(int),
        }
    ).reset_index()
    return table.sort_values("publications", ascending=False).reset_index(drop=True)


def labelled_versus_unlabelled(df: pd.DataFrame) -> dict[str, float]:
    """Compare the labelled subset to the rest.

    This is the comparison that matters to whoever trains a model: the labelled rows are the
    only ones supervised training can use, and they may not look like the bulk of the
    dataset at all.
    """
    if df.empty:
        return {"labelled": 0, "labelled_mean_text": 0.0, "unlabelled_mean_text": 0.0}

    has_label = df["label"].notna() & df["label"].astype(str).str.strip().ne("")
    return {
        "labelled": int(has_label.sum()),
        "labelled_mean_text": _mean_text(df[has_label]),
        "unlabelled_mean_text": _mean_text(df[~has_label]),
    }


def _mean_text(frame: pd.DataFrame) -> float:
    return round(float(frame["text_length"].mean()), 1) if len(frame) else 0.0


# --- 1. Measuring: a dataset in, a record of numbers out --------------------


def measure(
    df: pd.DataFrame,
    stats: dict[str, int],
    duplicates: dict[str, int],
    by_title: dict[str, int] | None = None,
    *,
    measured_on: str,
) -> dict[str, Any]:
    """Every number the report carries, and nothing that could identify a publication."""
    return {
        "schema": SCHEMA,
        "measured_on": measured_on,
        "collected": int(stats.get("raw_total", 0)),
        "kept": len(df),
        "with_image_pct": round(100.0 * df["has_image"].sum() / len(df), 1) if len(df) else 0.0,
        "labelled_pct": round(100.0 * _filled(df["label"]) / len(df), 1) if len(df) else 0.0,
        "completeness": completeness(df).to_dict(orient="records"),
        "by_source": by_source(df).to_dict(orient="records"),
        "labelled_subset": labelled_versus_unlabelled(df),
        "duplicates": {
            "publications": int(duplicates.get("publications", 0)),
            "missed_pairs_url_and_title": int(duplicates.get("missed_pairs", 0)),
            "missed_pairs_title_only": int((by_title or {}).get("missed_pairs", 0)),
        },
    }


# --- 2. Writing: the record in, the published markdown out ------------------


def _markdown(rows: list[dict[str, Any]], columns: tuple[str, ...]) -> str:
    """Render a list of records as a markdown table, without pulling in a dependency."""
    header = "| " + " | ".join(columns) + " |"
    rule = "|" + "|".join("---" for _ in columns) + "|"
    body = ["| " + " | ".join(str(row[column]) for column in columns) + " |" for row in rows]
    return "\n".join([header, rule, *body])


def render(measures: dict[str, Any]) -> str:
    """Build the whole report as markdown, from the measures and from nothing else."""
    if not measures.get("kept"):
        return (
            "# Data quality report\n\n"
            "Written by `scripts/quality_report.py` from `reports/data_quality.json`.\n\n"
            "There is no dataset to report on. Run `uv run python scripts/run_etl.py` then "
            "`uv run python scripts/quality_report.py --measure`.\n"
        )

    duplicates = measures["duplicates"]
    return f"""# Data quality report

Written by `scripts/quality_report.py` from `reports/data_quality.json`, measured on
{measures["measured_on"]}. The sources are live: the numbers below describe the corpus of that
run, and a run today collects a different one.

Of n = {measures["collected"]} publications collected, {measures["kept"]} were kept. Of those,
**{measures["with_image_pct"]}%** carry an image file on disk, which is the multimodal
requirement, and **{measures["labelled_pct"]}%** carry a ground-truth label.

## Completeness

How many rows carry a real value for each field. An empty string counts as missing.

{_markdown(measures["completeness"], ("field", "filled", "filled_pct"))}

## By source

What each source contributes, not merely how much.

{_markdown(measures["by_source"], ("source", "publications", "with_image", "labelled", "mean_text_length"))}

> **How to read it.** One row per source feeding the pipeline. `publications` counts what the
> source delivered, `with_image` how many of those carried a usable illustration, and `labelled`
> how many arrived with a ground-truth annotation. `mean_text_length` is the average number of
> characters of body text, and it is the column that separates a full article from a headline
> with a link under it.

### What the labelled subset really looks like

{_label_note(measures["labelled_subset"])}

## Duplicates

Publications the current identifier treats as distinct although their normalised URL and
title match, over n = {duplicates["publications"]} publications. Measured, not assumed: the
code is `multimodal_etl.quality.duplicates`.

| Measure | Pairs missed | What it would catch |
|---|---|---|
| Same normalised URL **and** title | {duplicates["missed_pairs_url_and_title"]} | one article reached twice through variant URLs |
| Same normalised title, any URL | {duplicates["missed_pairs_title_only"]} | one wire story republished by two outlets |

Measured on {duplicates["publications"]} publications.
"""


def _label_note(split: dict[str, float]) -> str:
    """One sentence on how the labelled rows differ from the rest."""
    if not split["labelled"]:
        return "No publication carries a ground-truth label in this dataset."
    return (
        f"The {split['labelled']} labelled publications average "
        f"**{split['labelled_mean_text']} characters** of text, against "
        f"{split['unlabelled_mean_text']} for the unlabelled ones. The labels come from "
        "FakeNewsNet and Fakeddit, which publish a headline and no article body: the only "
        "rows usable for supervised training are also the textually poorest. A model "
        "trained on this dataset would be learning from headlines."
    )
