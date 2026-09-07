"""KPI dashboard of the ETL pipeline.

A Streamlit application visualising the performance indicators of the multimodal
extraction pipeline. It is built to be readable **by a non-technical audience**: every
figure comes with a sentence saying what it measures, the monitoring plan's thresholds are
turned into green / amber / red lights, and a sample of images shows concretely what the
pipeline produces.

Launch with:
    uv run streamlit run dashboard/app.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from multimodal_etl.config import absolute_path  # noqa: E402
from multimodal_etl.kpi import (  # noqa: E402
    compute_kpis,
    evaluate_thresholds,
    load_latest_dataset,
    run_history,
)

st.set_page_config(page_title="Multimodal ETL — pipeline KPIs", page_icon="📊", layout="wide")

# Coloured dot for each status, so the table reads at a glance.
STATUS_DOTS = {"green": "🟢", "amber": "🟠", "red": "🔴"}

# A source can be silent for reasons that are not incidents. Showing the reason is what
# stops a run that brought back three sources out of four from looking successful.
CAUSE_DOTS = {
    "ok": "🟢",
    "empty": "🟠",
    "disabled": "⚪",
    "quota": "🔴",
    "network": "🔴",
    "malformed": "🔴",
}
CAUSE_LABELS = {
    "ok": "delivered",
    "empty": "answered, but had nothing",
    "disabled": "turned off (no API key)",
    "quota": "quota spent",
    "network": "unreachable",
    "malformed": "unexpected answer",
}


def kpi_card(column, label: str, value: str, help_text: str) -> None:
    """Display one KPI card with an explanatory tooltip."""
    column.metric(label, value, help=help_text)


def section_status(kpis: dict) -> None:
    """Check the monitored indicators against the monitoring plan's thresholds."""
    st.subheader("Pipeline status")
    st.caption(
        "Each indicator is compared to the threshold set in the monitoring plan. "
        "Green: normal. Amber: worth watching. Red: intervention required."
    )

    evaluations = evaluate_thresholds(kpis)
    table = pd.DataFrame(
        [
            {
                "": STATUS_DOTS[evaluation["status"]],
                "Indicator": evaluation["label"],
                "Value": evaluation["value"],
                "Expected": evaluation["expected"],
                "Why it is tracked": evaluation["justification"],
            }
            for evaluation in evaluations
        ]
    )
    st.dataframe(table, use_container_width=True, hide_index=True)

    alerts = [e for e in evaluations if e["status"] == "red"]
    if alerts:
        st.error(
            "Critical threshold crossed: "
            + ", ".join(f"{a['label']} ({a['value']})" for a in alerts)
        )


def section_quality(quality: dict) -> None:
    """Data quality cards."""
    st.subheader("Data quality")
    c1, c2, c3, c4 = st.columns(4)
    kpi_card(
        c1,
        "Validity rate",
        f"{quality['validity_rate_pct']}%",
        "Share of the collected publications that pass every quality check.",
    )
    kpi_card(
        c2,
        "Text-image pairing",
        f"{quality['text_image_pairing_pct']}%",
        "Share of the kept publications whose image really is on disk.",
    )
    kpi_card(
        c3,
        "Dated publications",
        f"{quality['dated_rate_pct']}%",
        "Share of publications whose date is known: without it, no freshness tracking.",
    )
    kpi_card(
        c4,
        "Duplicates dropped",
        f"{quality['duplicate_rate_pct']}%",
        "Share of duplicate publications, detected and removed at the transform step.",
    )


def section_volume(volume: dict, freshness: dict, performance: dict) -> None:
    """Volume, freshness and cost cards."""
    st.subheader("Volume, freshness and cost")
    c1, c2, c3, c4 = st.columns(4)
    kpi_card(
        c1,
        "Publications in the dataset",
        str(volume["publications"]),
        "Number of clean publications produced by the last run.",
    )
    kpi_card(
        c2,
        "Total in the database",
        str(performance["publications_in_db"]),
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
        f"{performance['publications_per_sec']} /s",
        "Number of publications processed per second.",
    )
    kpi_card(
        c3,
        "What the run adds",
        f"{performance['new_rate_pct']}%",
        "Share of the collected publications that were not already in the database.",
    )
    kpi_card(
        c4,
        "API calls spent",
        str(performance["api_calls_spent"]),
        "NewsData.io quota consumed — the main external cost.",
    )


def section_charts(volume: dict, performance: dict) -> None:
    """Spread of sources and access methods, and time spent per step."""
    g1, g2 = st.columns(2)

    with g1:
        st.markdown("**Where do the publications come from?**")
        distribution = volume["by_source"]
        if distribution:
            figure = px.bar(
                x=list(distribution.values()),
                y=list(distribution.keys()),
                orientation="h",
                labels={"x": "Number of publications", "y": "Source"},
                color=list(distribution.keys()),
            )
            figure.update_layout(showlegend=False, height=380)
            st.plotly_chart(figure, use_container_width=True)

    with g2:
        st.markdown("**Time spent at each step (seconds)**")
        steps = {
            "Extract": performance["extract_duration_sec"],
            "Transform": performance["transform_duration_sec"],
            "Load": performance["load_duration_sec"],
        }
        figure = px.bar(
            x=list(steps.keys()),
            y=list(steps.values()),
            labels={"x": "Step", "y": "Duration (s)"},
            color=list(steps.keys()),
        )
        figure.update_layout(showlegend=False, height=380)
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
                "": CAUSE_DOTS.get(cause, "⚪"),
                "Source": name,
                "Publications": max(int(count), 0),
                "Outcome": CAUSE_LABELS.get(cause, cause),
            }
        )
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
    st.caption(
        "A source that is turned off, or that simply had nothing new, is not an incident: "
        "only the red rows count towards the failed-sources indicator."
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
        figure = px.line(
            history,
            x="date",
            y=["publications_extracted", "publications_added"],
            markers=True,
            labels={"date": "Run date", "value": "Publications", "variable": ""},
        )
        figure.update_layout(height=340)
        st.plotly_chart(figure, use_container_width=True)

    with g2:
        st.markdown("**Validity rate and duration, per run**")
        figure = px.line(
            history,
            x="date",
            y=["validity_rate_pct", "total_duration_sec"],
            markers=True,
            labels={"date": "Run date", "value": "Value", "variable": ""},
        )
        figure.update_layout(height=340)
        st.plotly_chart(figure, use_container_width=True)


def section_overview(df: pd.DataFrame) -> None:
    """Composition of the dataset, and a concrete sample."""
    st.subheader("What the pipeline produces")

    a1, a2 = st.columns([1, 2])
    with a1:
        st.markdown("**Spread of labels**")
        labels = df["label"].fillna("unlabelled").value_counts()
        figure = px.pie(values=labels.to_numpy(), names=labels.index.tolist(), hole=0.4)
        figure.update_layout(height=320, margin={"t": 10, "b": 10})
        st.plotly_chart(figure, use_container_width=True)
    with a2:
        st.markdown("**A look at the publications**")
        columns = ["source", "title", "language", "has_image", "label"]
        st.dataframe(df[columns].head(12), use_container_width=True, height=320)

    st.markdown("**A few images paired with the texts above**")
    st.caption(
        "These files were downloaded and verified by the pipeline: this is the proof that "
        "every publication in the dataset really does pair a text with an image."
    )
    preview = df[df["has_image"]].head(6)
    image_columns = st.columns(6)
    for column, (_, publication) in zip(image_columns, preview.iterrows(), strict=False):
        path = absolute_path(publication["image_path"])
        if path.is_file():
            column.image(str(path), caption=publication["title"][:60], use_container_width=True)


def main() -> None:
    """Build the dashboard from the pipeline's latest artefacts."""
    st.title("📊 Multimodal ETL — extraction pipeline dashboard")
    st.caption(
        "Quality, volume and performance of the ETL pipeline that feeds the fake-news "
        "detector with multimodal data (text + image)."
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
