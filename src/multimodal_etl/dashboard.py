"""KPI dashboard of the ETL pipeline.

A Streamlit application showing what the last run produced and whether it is within the bounds
``docs/protocol.md`` sets. It is built to be read **by someone who did not write the pipeline**,
and ``docs/interface.md`` sets out the three rules that follow from that. The shortest of them:
no status is carried by colour alone, so the word is in the cell.

Colours come from :mod:`multimodal_etl.figure_style`, the same module the figures use; the
Streamlit theme itself lives in ``.streamlit/config.toml``. Nothing here writes a colour.

Launch with:
    uv run streamlit run src/multimodal_etl/dashboard.py
"""

from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

from multimodal_etl.config import absolute_path
from multimodal_etl.figure_style import PALETTE, STATE
from multimodal_etl.kpi import (
    compute_kpis,
    evaluate_thresholds,
    load_latest_dataset,
    run_history,
)

st.set_page_config(page_title="Multimodal ETL — pipeline KPIs", layout="wide")

#: What each status means in words. The colour repeats the word, it never replaces it: a
#: reader who cannot separate the three hues still reads the row.
STATUS_WORDS = {"green": "within bounds", "amber": "watch", "red": "act now"}
STATUS_COLOURS = {"green": STATE["ok"], "amber": STATE["warning"], "red": STATE["danger"]}

# A source can be silent for reasons that are not incidents, and the outcome column is what
# keeps a partial collection from reading as a complete one.
CAUSE_LABELS = {
    "ok": "delivered",
    "empty": "answered, but had nothing",
    "disabled": "turned off (no API key)",
    "quota": "quota spent",
    "network": "unreachable",
    "malformed": "unexpected answer",
}
CAUSE_COLOURS = {
    "ok": STATE["ok"],
    "empty": STATE["warning"],
    "disabled": STATE["neutral"],
    "quota": STATE["danger"],
    "network": STATE["danger"],
    "malformed": STATE["danger"],
}

#: Plotly inherits nothing from the Streamlit theme: a chart left alone comes out in the
#: library's own ten colours, next to a page painted in this project's.
LAYOUT = {
    "paper_bgcolor": PALETTE["paper"],
    "plot_bgcolor": PALETTE["paper"],
    "font": {"color": PALETTE["ink"], "size": 13},
    "margin": {"t": 30, "b": 40, "l": 10, "r": 10},
}
AXIS = {"gridcolor": PALETTE["grid"], "zerolinecolor": PALETTE["grid"], "linecolor": PALETTE["muted"]}


def _styled(frame: pd.DataFrame, column: str, colours: dict[str, str]) -> object:
    """Colour one column's text by its own value, leaving the value legible."""
    return frame.style.map(
        lambda value: f"color: {colours.get(value, PALETTE['ink'])}; font-weight: 600",
        subset=[column],
    )


def kpi_card(column, label: str, value: str, help_text: str) -> None:
    """Display one KPI card with an explanatory tooltip."""
    column.metric(label, value, help=help_text)


def section_status(kpis: dict) -> None:
    """Check the monitored indicators against the thresholds `docs/protocol.md` publishes."""
    st.subheader("Pipeline status")
    st.caption(
        "Each indicator against the bound set in docs/protocol.md, with the unit it is "
        "measured in. Within bounds: nothing to do. Watch: worth a look. Act now: the run "
        "should not feed a model as it stands."
    )

    evaluations = evaluate_thresholds(kpis)
    table = pd.DataFrame(
        [
            {
                "Indicator": evaluation["label"],
                "Measured": evaluation["reading"],
                "Healthy when": evaluation["expected"],
                "Status": STATUS_WORDS[evaluation["status"]],
                "Why it is tracked": evaluation["justification"],
            }
            for evaluation in evaluations
        ]
    )
    st.dataframe(
        _styled(table, "Status", {STATUS_WORDS[k]: v for k, v in STATUS_COLOURS.items()}),
        use_container_width=True,
        hide_index=True,
        # Without explicit widths the last column is given the same share as the first four
        # and its sentence is clipped mid-word — on screen and in every published capture.
        column_config={
            "Indicator": st.column_config.TextColumn(width="small"),
            "Measured": st.column_config.TextColumn(width="small"),
            "Healthy when": st.column_config.TextColumn(width="small"),
            "Status": st.column_config.TextColumn(width="small"),
            "Why it is tracked": st.column_config.TextColumn(width="large"),
        },
    )

    alerts = [e for e in evaluations if e["status"] == "red"]
    if alerts:
        st.error(
            "Outside bounds: "
            + ", ".join(f"{a['label']} at {a['reading']}, healthy {a['expected']}" for a in alerts)
        )


def section_quality(quality: dict) -> None:
    """Data quality cards."""
    st.subheader("Data quality")
    c1, c2, c3, c4 = st.columns(4)
    kpi_card(
        c1,
        "Validity rate",
        f"{quality['validity_rate_pct']} %",
        "Share of the collected publications that pass every quality check.",
    )
    kpi_card(
        c2,
        "Text-image pairing",
        f"{quality['text_image_pairing_pct']} %",
        "Share of the kept publications whose image really is on disk.",
    )
    kpi_card(
        c3,
        "Dated publications",
        f"{quality['dated_rate_pct']} %",
        "Share of publications whose date is known: without it, no freshness tracking.",
    )
    kpi_card(
        c4,
        "Duplicates dropped",
        f"{quality['duplicate_rate_pct']} %",
        "Share of duplicate publications, detected and removed at the transform step.",
    )


def section_volume(volume: dict, freshness: dict, performance: dict) -> None:
    """Volume, freshness and cost cards."""
    st.subheader("Volume, freshness and cost")
    c1, c2, c3, c4 = st.columns(4)
    kpi_card(
        c1,
        "Publications in the dataset",
        f"{volume['publications']} publications",
        "Number of clean publications produced by the last run.",
    )
    kpi_card(
        c2,
        "Total in the database",
        f"{performance['publications_in_db']} publications",
        "The dataset grows with every run: only the new rows are added.",
    )
    kpi_card(
        c3,
        "Median age",
        f"{freshness['median_age_hours']} h",
        "Median age of the ingested publications. A fake-news detector needs recent content.",
    )
    kpi_card(
        c4,
        "Disk used by images",
        f"{performance['image_weight_mb']} MB",
        "Storage cost of the images downloaded during the last run.",
    )


def section_performance(performance: dict) -> None:
    """Speed and run-cost cards."""
    st.subheader("Run performance")
    c1, c2, c3, c4 = st.columns(4)
    kpi_card(
        c1,
        "Total duration",
        f"{performance['total_duration_sec']} s",
        "Total pipeline time: extract, transform and load.",
    )
    kpi_card(
        c2,
        "Throughput",
        f"{performance['publications_per_sec']} publications/s",
        "Number of publications processed per second.",
    )
    kpi_card(
        c3,
        "What the run adds",
        f"{performance['new_rate_pct']} %",
        "Share of the collected publications that were not already in the database.",
    )
    kpi_card(
        c4,
        "API calls spent",
        f"{performance['api_calls_spent']} calls",
        "NewsData.io quota consumed — the main external cost.",
    )


def section_charts(volume: dict, performance: dict) -> None:
    """Where the publications come from, and where the time goes."""
    g1, g2 = st.columns(2)

    with g1:
        st.markdown("**Where the publications come from**")
        distribution = volume["by_source"]
        if distribution:
            figure = go.Figure(
                go.Bar(
                    x=list(distribution.values())[::-1],
                    y=list(distribution.keys())[::-1],
                    orientation="h",
                    marker_color=PALETTE["primary"],
                    hovertemplate="%{y}: %{x} publications<extra></extra>",
                )
            )
            figure.update_layout(height=380, **LAYOUT)
            figure.update_xaxes(title_text="publications in the dataset", **AXIS)
            figure.update_yaxes(title_text="source", **AXIS)
            st.plotly_chart(figure, use_container_width=True)

    with g2:
        st.markdown("**Time spent at each step**")
        steps = {
            "Extract": performance["extract_duration_sec"],
            "Transform": performance["transform_duration_sec"],
            "Load": performance["load_duration_sec"],
        }
        figure = go.Figure(
            go.Bar(
                x=list(steps.keys()),
                y=list(steps.values()),
                marker_color=PALETTE["primary"],
                hovertemplate="%{x}: %{y} s<extra></extra>",
            )
        )
        figure.update_layout(height=380, **LAYOUT)
        figure.update_xaxes(title_text="pipeline step", **AXIS)
        figure.update_yaxes(title_text="duration (seconds)", **AXIS)
        st.plotly_chart(figure, use_container_width=True)


def section_sources(run: dict) -> None:
    """Show what each source did on the last run, and why when it did nothing."""
    per_source = run.get("per_source") or {}
    if not per_source:
        return

    st.markdown("**How each source behaved on the last run**")
    rows = []
    for name, entry in per_source.items():
        cause = entry.get("cause", "ok") if isinstance(entry, dict) else "ok"
        count = entry.get("count", 0) if isinstance(entry, dict) else entry
        rows.append(
            {
                "Source": name,
                "Publications": max(int(count), 0),
                "Outcome": CAUSE_LABELS.get(cause, cause),
            }
        )
    frame = pd.DataFrame(rows)
    st.dataframe(
        _styled(frame, "Outcome", {CAUSE_LABELS[k]: v for k, v in CAUSE_COLOURS.items()}),
        use_container_width=True,
        hide_index=True,
    )
    st.caption(
        "A source that is turned off, or that simply had nothing new, is not an incident: "
        "only an unreachable, malformed or quota-spent source counts towards the "
        "failed-sources indicator."
    )


def section_history() -> None:
    """How the runs evolve over time."""
    history = run_history()
    if history.empty or len(history) < 2:
        st.info(
            "The history appears from the pipeline's second run onwards: it is what lets "
            "you follow trends rather than a snapshot."
        )
        return

    st.subheader("Run history")
    g1, g2 = st.columns(2)

    with g1:
        st.markdown("**Publications collected and added, per run**")
        figure = go.Figure()
        for column, label, colour in (
            ("publications_extracted", "collected by the sources", PALETTE["primary"]),
            ("publications_added", "new in the database", PALETTE["secondary"]),
        ):
            figure.add_trace(
                go.Scatter(
                    x=history["date"],
                    y=history[column],
                    name=label,
                    mode="lines+markers",
                    line={"color": colour},
                    hovertemplate="%{y} publications<extra>" + label + "</extra>",
                )
            )
        figure.update_layout(
            height=380,
            # Below the axis title, not on top of it: at -0.25 the horizontal legend and the
            # words « run date » were printed over each other.
            legend={"orientation": "h", "y": -0.38},
            **LAYOUT,
        )
        figure.update_xaxes(title_text="run date", **AXIS)
        figure.update_yaxes(title_text="publications", **AXIS)
        st.plotly_chart(figure, use_container_width=True)

    with g2:
        st.markdown("**Validity rate and duration, per run**")
        # Two quantities, two units, two axes. Drawn on one axis, a duration in seconds and
        # a percentage share the same scale by accident and the smaller of the two flattens
        # into the baseline.
        figure = make_subplots(specs=[[{"secondary_y": True}]])
        figure.add_trace(
            go.Scatter(
                x=history["date"],
                y=history["validity_rate_pct"],
                name="validity rate",
                mode="lines+markers",
                line={"color": PALETTE["primary"]},
                hovertemplate="%{y} %<extra>validity rate</extra>",
            ),
            secondary_y=False,
        )
        figure.add_trace(
            go.Scatter(
                x=history["date"],
                y=history["total_duration_sec"],
                name="total duration",
                mode="lines+markers",
                line={"color": PALETTE["secondary"]},
                hovertemplate="%{y} s<extra>total duration</extra>",
            ),
            secondary_y=True,
        )
        figure.update_layout(
            height=380,
            # Below the axis title, not on top of it: at -0.25 the horizontal legend and the
            # words « run date » were printed over each other.
            legend={"orientation": "h", "y": -0.38},
            **LAYOUT,
        )
        figure.update_xaxes(title_text="run date", **AXIS)
        figure.update_yaxes(title_text="validity rate (%)", secondary_y=False, **AXIS)
        figure.update_yaxes(title_text="total duration (seconds)", secondary_y=True, **AXIS)
        st.plotly_chart(figure, use_container_width=True)


def section_overview(df: pd.DataFrame) -> None:
    """Composition of the dataset, and a concrete sample."""
    st.subheader("What the pipeline produces")

    a1, a2 = st.columns([1, 2])
    with a1:
        st.markdown("**Ground truth available**")
        labels = df["label"].fillna("no label").value_counts()
        figure = go.Figure(
            go.Bar(
                x=labels.to_numpy(),
                y=labels.index.tolist(),
                orientation="h",
                marker_color=PALETTE["primary"],
                hovertemplate="%{y}: %{x} publications<extra></extra>",
            )
        )
        figure.update_layout(height=320, **LAYOUT)
        figure.update_xaxes(title_text="publications", **AXIS)
        figure.update_yaxes(title_text="label", **AXIS)
        st.plotly_chart(figure, use_container_width=True)
    with a2:
        st.markdown("**A look at the publications**")
        columns = ["source", "title", "language", "has_image", "label"]
        st.dataframe(df[columns].head(12), use_container_width=True, height=320)

    st.markdown("**A few images paired with the texts above**")
    st.caption(
        "These files were downloaded and opened by the pipeline before the row was kept: "
        "they are what the rule « no image on disk, no publication » leaves behind."
    )
    preview = df[df["has_image"]].head(6)
    image_columns = st.columns(6)
    for column, (_, publication) in zip(image_columns, preview.iterrows(), strict=False):
        path = absolute_path(publication["image_path"])
        if path.is_file():
            column.image(str(path), caption=publication["title"][:60], use_container_width=True)


def main() -> None:
    """Build the dashboard from the pipeline's latest artefacts."""
    st.title("Multimodal ETL — extraction pipeline")
    st.caption(
        "Quality, volume and performance of the ETL pipeline that feeds a fake-news "
        "detector with paired text and image."
    )

    df, stats, run = load_latest_dataset()
    if df.empty:
        st.warning("No dataset found. Run the pipeline first: `uv run python scripts/run_etl.py`.")
        return

    kpis = compute_kpis(df, stats, run)

    section_status(kpis)
    section_quality(kpis["quality"])
    section_volume(kpis["volume"], kpis["freshness"], kpis["performance"])
    section_performance(kpis["performance"])
    section_charts(kpis["volume"], kpis["performance"])
    section_sources(run)
    section_history()
    section_overview(df)

    st.caption(
        f"Last run: {run.get('run_at', 'unknown')} "
        f"(orchestrator: {run.get('orchestrator', 'n/a')}) · "
        f"{kpis['volume']['sources']} distinct sources · "
        f"mean text length: {kpis['quality']['mean_text_length']} characters."
    )


if __name__ == "__main__":
    main()
