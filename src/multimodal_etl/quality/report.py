"""What fraction of the collected dataset is actually usable.

The KPIs answer "is the pipeline healthy". This answers a different question, the one a
team training a model downstream would ask first: **of the rows you collected, how many can
I use, and for what?** A raw row count says nothing — a publication with no image is dead
weight for a multimodal model, and one with no label is dead weight for supervised
training.

The report is written to ``reports/data_quality.md`` by ``scripts/quality_report.py``.
"""

from __future__ import annotations

import pandas as pd

# Fields worth reporting on: the ones a downstream consumer would filter by.
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


def _markdown(table: pd.DataFrame) -> str:
    """Render a DataFrame as a markdown table, without pulling in a dependency."""
    header = "| " + " | ".join(table.columns) + " |"
    rule = "|" + "|".join("---" for _ in table.columns) + "|"
    body = [
        "| " + " | ".join(str(value) for value in row) + " |"
        for row in table.itertuples(index=False)
    ]
    return "\n".join([header, rule, *body])


def render_report(
    df: pd.DataFrame,
    stats: dict[str, int],
    duplicates: dict[str, int],
    by_title: dict[str, int] | None = None,
) -> str:
    """Build the whole report as markdown."""
    if df.empty:
        return (
            "# Data quality report\n\n"
            "There is no dataset to report on. Run `uv run python scripts/run_etl.py` "
            "first.\n"
        )

    usable_pct = round(100.0 * int(df["has_image"].sum()) / len(df), 1)
    labelled_pct = round(100.0 * _filled(df["label"]) / len(df), 1)

    return f"""# Data quality report

Generated from the most recent dataset, by `scripts/quality_report.py`.

{len(df)} publications kept out of {stats.get("raw_total", "?")} collected.
**{usable_pct}%** carry an image on disk — the multimodal requirement — and
**{labelled_pct}%** carry a ground-truth label.

## Completeness

How many rows carry a real value for each field. An empty string counts as missing.

{_markdown(completeness(df))}

## By source

What each source contributes, not merely how much.

{_markdown(by_source(df))}

### What the labelled subset really looks like

{_label_note(df)}

## Duplicates

Publications the current identifier treats as distinct although their normalised URL and
title match. Measured, not assumed — see `multimodal_etl.quality.duplicates`.

| Measure | Pairs missed | What it would catch |
|---|---|---|
| Same normalised URL **and** title | {duplicates.get("missed_pairs", 0)} | one article reached twice through variant URLs |
| Same normalised title, any URL | {(by_title or {}).get("missed_pairs", 0)} | one wire story republished by two outlets |

Measured on {duplicates.get("publications", 0)} publications.
"""


def _label_note(df: pd.DataFrame) -> str:
    """One sentence on how the labelled rows differ from the rest."""
    split = labelled_versus_unlabelled(df)
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
