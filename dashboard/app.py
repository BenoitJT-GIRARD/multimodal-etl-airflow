"""Tableau de bord KPI du pipeline ETL.

Application Streamlit qui visualise les indicateurs de performance du pipeline
d'extraction multimodale. Elle est pensée pour être lisible **par un public non
technique** : chaque chiffre est accompagné d'une phrase qui dit ce qu'il mesure,
les seuils du plan de monitoring sont traduits en feux verts / orange / rouges, et
un échantillon d'images montre concrètement ce que le pipeline produit.

Lancement :
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

st.set_page_config(page_title="Multimodal ETL — KPI du pipeline ETL", page_icon="📊", layout="wide")

# Pastille de couleur associée à chaque status_for, pour une lecture immédiate.
PASTILLES = {"vert": "🟢", "orange": "🟠", "rouge": "🔴"}


def kpi_card(colonne, libelle: str, valeur: str, aide: str) -> None:
    """Affiche une carte KPI avec une infobulle explicative."""
    colonne.metric(libelle, valeur, help=aide)


def section_status(kpis: dict) -> None:
    """Confronte les indicateurs surveillés aux seuils du plan de monitoring."""
    st.subheader("État du pipeline")
    st.caption(
        "Chaque indicateur est comparé au seuil défini dans le plan de monitoring. "
        "Vert : situation normale. Orange : à surveiller. Rouge : intervention requise."
    )

    evaluations = evaluate_thresholds(kpis)
    tableau = pd.DataFrame(
        [
            {
                "": PASTILLES[evaluation["statut"]],
                "Indicateur": evaluation["libelle"],
                "Valeur": evaluation["valeur"],
                "Attendu": evaluation["attendu"],
                "Pourquoi c'est suivi": evaluation["justification"],
            }
            for evaluation in evaluations
        ]
    )
    st.dataframe(tableau, use_container_width=True, hide_index=True)

    alertes = [e for e in evaluations if e["statut"] == "rouge"]
    if alertes:
        st.error(
            "Threshold critique franchi : "
            + ", ".join(f"{a['libelle']} ({a['valeur']})" for a in alertes)
        )


def section_quality(qualite: dict) -> None:
    """Cartes de qualité des données."""
    st.subheader("Qualité des données")
    c1, c2, c3, c4 = st.columns(4)
    kpi_card(
        c1,
        "Taux de validité",
        f"{qualite['taux_validite_pct']} %",
        "Part des publications collectées qui passent tous les contrôles de qualité.",
    )
    kpi_card(
        c2,
        "Association texte-image",
        f"{qualite['taux_association_texte_image_pct']} %",
        "Part des publications retenues dont l'image est bien présente sur le disque.",
    )
    kpi_card(
        c3,
        "Publications datées",
        f"{qualite['taux_date_connue_pct']} %",
        "Part des publications dont on connaît la date : sans elle, pas de suivi de fraîcheur.",
    )
    kpi_card(
        c4,
        "Doublons écartés",
        f"{qualite['taux_doublons_pct']} %",
        "Part des publications en double, détectées et supprimées à la transformation.",
    )


def section_volume(volume: dict, fraicheur: dict, performance: dict) -> None:
    """Cartes de volume, de fraîcheur et de coût."""
    st.subheader("Volume, fraîcheur et coût")
    c1, c2, c3, c4 = st.columns(4)
    kpi_card(
        c1,
        "Publications du jeu",
        str(volume["nb_publications"]),
        "Nombre de publications propres produites par la dernière exécution.",
    )
    kpi_card(
        c2,
        "Total accumulé en base",
        str(performance["publications_en_base"]),
        "Le jeu de données grossit à chaque exécution : seules les nouveautés sont ajoutées.",
    )
    kpi_card(
        c3,
        "Âge médian",
        f"{fraicheur['age_median_heures']} h",
        "Ancienneté médiane des publications ingérées. Un détecteur de fake news a "
        "besoin de contenus récents.",
    )
    kpi_card(
        c4,
        "Disque occupé par les images",
        f"{performance['poids_images_mo']} Mo",
        "Coût de stockage des images téléchargées lors de la dernière exécution.",
    )


def section_performance(performance: dict) -> None:
    """Cartes de rapidité et de coût d'exécution."""
    st.subheader("Performance de l'exécution")
    c1, c2, c3, c4 = st.columns(4)
    kpi_card(
        c1,
        "Durée totale",
        f"{performance['duree_totale_sec']} s",
        "Temps total du pipeline : extraction, transformation et chargement.",
    )
    kpi_card(
        c2,
        "Débit",
        f"{performance['debit_publications_par_sec']} /s",
        "Nombre de publications traitées par seconde.",
    )
    kpi_card(
        c3,
        "Apport de l'exécution",
        f"{performance['taux_nouveaute_pct']} %",
        "Part des publications collectées qui n'étaient pas déjà en base.",
    )
    kpi_card(
        c4,
        "Appels d'API consommés",
        str(performance["appels_api_consommes"]),
        "Consommation du quota NewsData.io — principal poste de coût externe.",
    )


def section_charts(volume: dict, performance: dict) -> None:
    """Répartition des sources, méthodes d'accès et temps par étape."""
    g1, g2 = st.columns(2)

    with g1:
        st.markdown("**D'où viennent les publications ?**")
        repartition = volume["repartition_sources"]
        if repartition:
            figure = px.bar(
                x=list(repartition.values()),
                y=list(repartition.keys()),
                orientation="h",
                labels={"x": "Nombre de publications", "y": "Source"},
                color=list(repartition.keys()),
            )
            figure.update_layout(showlegend=False, height=380)
            st.plotly_chart(figure, use_container_width=True)

    with g2:
        st.markdown("**Temps passé à chaque étape (secondes)**")
        etapes = {
            "Extraction": performance["duree_extraction_sec"],
            "Transformation": performance["duree_transformation_sec"],
            "Chargement": performance["duree_chargement_sec"],
        }
        figure = px.bar(
            x=list(etapes.keys()),
            y=list(etapes.values()),
            labels={"x": "Étape", "y": "Durée (s)"},
            color=list(etapes.keys()),
        )
        figure.update_layout(showlegend=False, height=380)
        st.plotly_chart(figure, use_container_width=True)


def section_history() -> None:
    """Évolution des exécutions dans le temps."""
    historique = run_history()
    if historique.empty or len(historique) < 2:
        st.info(
            "L'historique apparaîtra dès la deuxième exécution du pipeline : il permet "
            "de suivre les tendances plutôt qu'un instantané."
        )
        return

    st.subheader("Historique des exécutions")
    g1, g2 = st.columns(2)

    with g1:
        st.markdown("**Publications collectées et ajoutées, par exécution**")
        figure = px.line(
            historique,
            x="date",
            y=["publications_extraites", "publications_ajoutees"],
            markers=True,
            labels={"date": "Date d'exécution", "value": "Publications", "variable": ""},
        )
        figure.update_layout(height=340)
        st.plotly_chart(figure, use_container_width=True)

    with g2:
        st.markdown("**Taux de validité et durée, par exécution**")
        figure = px.line(
            historique,
            x="date",
            y=["taux_validite_pct", "duree_totale_sec"],
            markers=True,
            labels={"date": "Date d'exécution", "value": "Valeur", "variable": ""},
        )
        figure.update_layout(height=340)
        st.plotly_chart(figure, use_container_width=True)


def section_overview(df: pd.DataFrame) -> None:
    """Composition du jeu de données et échantillon concret."""
    st.subheader("Ce que le pipeline produit")

    a1, a2 = st.columns([1, 2])
    with a1:
        st.markdown("**Répartition des labels**")
        labels = df["label"].fillna("non labellisé").value_counts()
        figure = px.pie(values=labels.to_numpy(), names=labels.index.tolist(), hole=0.4)
        figure.update_layout(height=320, margin={"t": 10, "b": 10})
        st.plotly_chart(figure, use_container_width=True)
    with a2:
        st.markdown("**Aperçu des publications**")
        colonnes = ["source", "title", "language", "has_image", "label"]
        st.dataframe(df[colonnes].head(12), use_container_width=True, height=320)

    st.markdown("**Quelques images associées aux textes ci-dessus**")
    st.caption(
        "Ces fichiers ont été téléchargés et vérifiés par le pipeline : c'est la preuve "
        "que chaque publication du jeu de données associe bien un texte et une image."
    )
    apercu = df[df["has_image"]].head(6)
    colonnes_images = st.columns(6)
    for colonne, (_, publication) in zip(colonnes_images, apercu.iterrows(), strict=False):
        path_for = absolute_path(publication["image_path"])
        if path_for.is_file():
            colonne.image(
                str(path_for), caption=publication["title"][:60], use_container_width=True
            )


def main() -> None:
    """Construit le tableau de bord à partir des derniers artefacts du pipeline."""
    st.title("📊 Multimodal ETL — Tableau de bord du pipeline d'extraction")
    st.caption(
        "Suivi de la qualité, du volume et de la performance du pipeline ETL qui alimente "
        "le détecteur de fake news en données multimodales (texte + image)."
    )

    df, stats, run = load_latest_dataset()
    if df.empty:
        st.warning(
            "Aucun jeu de données trouvé. Lancez d'abord le pipeline : "
            "`uv run python scripts/run_etl.py`."
        )
        return

    kpis = compute_kpis(df, stats, run)

    section_status(kpis)
    section_quality(kpis["qualite"])
    section_volume(kpis["volume"], kpis["fraicheur"], kpis["performance"])
    section_performance(kpis["performance"])
    section_charts(kpis["volume"], kpis["performance"])
    section_history()
    section_overview(df)

    st.caption(
        f"Dernière exécution : {run.get('run_at', 'inconnue')} "
        f"(orchestrateur : {run.get('orchestrateur', 'n/c')}) · "
        f"{kpis['volume']['nb_sources']} sources distinctes · "
        f"longueur de texte moyenne : {kpis['qualite']['longueur_texte_moyenne']} caractères."
    )


if __name__ == "__main__":
    main()
