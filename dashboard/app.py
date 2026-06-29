"""Tableau de bord KPI du pipeline ETL.

Application Streamlit qui visualise les indicateurs de performance du pipeline
d'extraction multimodale. Pensee pour etre lisible **meme par un public non
technique** : des cartes de KPI commentees, des graphiques etiquetes et un apercu
du jeu de donnees produit.

Lancement :
    uv run streamlit run dashboard/app.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import plotly.express as px
import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from multimodal_etl.kpi import charge_dernier_dataset, compute_kpis  # noqa: E402

st.set_page_config(page_title="KPI du pipeline ETL", page_icon="📊", layout="wide")


def _carte(colonne, libelle: str, valeur: str, aide: str) -> None:
    """Affiche une carte KPI avec une infobulle explicative."""
    colonne.metric(libelle, valeur, help=aide)


def main() -> None:
    """Construit le tableau de bord a partir des derniers artefacts du pipeline."""
    st.title("📊 Tableau de bord du pipeline d'extraction")
    st.caption(
        "Suivi de la qualité, du volume et de la performance du pipeline ETL qui "
        "alimente le détecteur de fake news en données multimodales (texte + image)."
    )

    df, stats, run = charge_dernier_dataset()
    if df.empty:
        st.warning(
            "Aucun jeu de données trouvé. Lancez d'abord le pipeline : "
            "`uv run python scripts/run_etl.py`."
        )
        return

    kpis = compute_kpis(df, stats, run)
    qualite = kpis["qualite"]
    volume = kpis["volume"]
    perf = kpis["performance"]

    # --- Section 1 : KPI de qualité des données ------------------------------ #
    st.subheader("Qualité des données")
    c1, c2, c3, c4 = st.columns(4)
    _carte(
        c1,
        "Taux de validité",
        f"{qualite['taux_validite_pct']} %",
        "Part des publications brutes qui passent tous les contrôles de qualité.",
    )
    _carte(
        c2,
        "Association texte-image",
        f"{qualite['taux_association_texte_image_pct']} %",
        "Part des publications retenues disposant d'une image valide (cas d'usage multimodal).",
    )
    _carte(
        c3,
        "Publications labellisées",
        f"{qualite['taux_labellise_pct']} %",
        "Part des publications avec un label de vérité terrain (real/fake).",
    )
    _carte(
        c4,
        "Doublons écartés",
        f"{qualite['taux_doublons_pct']} %",
        "Part des doublons détectés et supprimés lors de la transformation.",
    )

    # --- Section 2 : KPI de performance -------------------------------------- #
    st.subheader("Performance du pipeline")
    p1, p2, p3, p4 = st.columns(4)
    _carte(
        p1,
        "Publications chargées",
        str(volume["nb_publications"]),
        "Nombre de publications propres chargées en base lors du dernier run.",
    )
    _carte(
        p2,
        "Durée totale",
        f"{perf['duree_totale_sec']} s",
        "Temps total d'exécution du pipeline (extraction + transformation + chargement).",
    )
    _carte(
        p3,
        "Débit",
        f"{perf['debit_publications_par_sec']} /s",
        "Nombre de publications traitées par seconde.",
    )
    _carte(
        p4,
        "Appels API consommés",
        str(perf["appels_api_consommes"]),
        "Nombre d'appels à l'API NewsData.io (suivi du quota et du coût).",
    )

    # --- Section 3 : graphiques ---------------------------------------------- #
    g1, g2 = st.columns(2)

    with g1:
        st.markdown("**Répartition des publications par source**")
        repartition = volume["repartition_sources"]
        if repartition:
            fig = px.bar(
                x=list(repartition.values()),
                y=list(repartition.keys()),
                orientation="h",
                labels={"x": "Nombre de publications", "y": "Source"},
                color=list(repartition.keys()),
            )
            fig.update_layout(showlegend=False, height=380)
            st.plotly_chart(fig, use_container_width=True)

    with g2:
        st.markdown("**Temps d'exécution par étape (secondes)**")
        etapes = {
            "Extraction": perf["duree_extraction_sec"],
            "Transformation": perf["duree_transformation_sec"],
            "Chargement": perf["duree_chargement_sec"],
        }
        fig = px.bar(
            x=list(etapes.keys()),
            y=list(etapes.values()),
            labels={"x": "Étape", "y": "Durée (s)"},
            color=list(etapes.keys()),
        )
        fig.update_layout(showlegend=False, height=380)
        st.plotly_chart(fig, use_container_width=True)

    # --- Section 4 : répartition real/fake et aperçu ------------------------- #
    st.subheader("Composition du jeu de données")
    a1, a2 = st.columns([1, 2])
    with a1:
        labels = df["label"].fillna("non labellisé").value_counts()
        fig = px.pie(values=labels.to_numpy(), names=labels.index.tolist(), hole=0.4)
        fig.update_layout(height=340, margin={"t": 10, "b": 10})
        st.plotly_chart(fig, use_container_width=True)
    with a2:
        st.markdown("**Aperçu des publications extraites**")
        apercu = df[["source", "title", "language", "has_image", "label"]].head(15)
        st.dataframe(apercu, use_container_width=True, height=340)

    st.caption(
        f"Longueur de texte moyenne : {qualite['longueur_texte_moyenne']} caractères · "
        f"{volume['nb_sources']} sources distinctes · dernier run : {run.get('run_at', 'n/c')}."
    )


if __name__ == "__main__":
    main()
