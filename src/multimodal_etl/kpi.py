"""Indicateurs de performance (KPI) du pipeline ETL.

Ce module calcule les indicateurs — **précision** des données,
**rapidité** et **coût** — et les complète par ce que le cas d'usage rend
réellement critique : la disponibilité effective des images, la fraîcheur du jeu de
données, sa diversité de sources et l'apport réel de chaque exécution.

Chaque indicateur est là parce qu'il déclenche une action s'il dérive ; le tableau
de bord les affiche et le plan de monitoring fixe les seuils. Ces seuils sont définis
**une seule fois**, ici, dans :data:`SEUILS` : le document et l'application ne peuvent
donc pas se contredire.

Les fonctions de calcul sont pures — données en entrée, dictionnaire en sortie —
ce qui les rend simples à tester et à afficher.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import NamedTuple

import pandas as pd

from multimodal_etl.config import PROCESSED_DIR, RUNS_DIR


class Threshold(NamedTuple):
    """Threshold d'alerte d'un indicateur, tel que défini dans le plan de monitoring."""

    libelle: str
    sens: str  # "haut" : plus c'est grand mieux c'est ; "bas" : l'inverse
    vert: float
    orange: float
    justification: str


# Seuils d'alerte — source unique de vérité, partagée par le tableau de bord et le
# plan de monitoring.
SEUILS: dict[str, Threshold] = {
    "taux_validite_pct": Threshold(
        "Taux de validité",
        "haut",
        60,
        45,
        "Calé sur le comportement observé (environ 65 %) : le rejet vient presque toujours "
        "d'une image indisponible, ce qui est normal. Sous 45 %, c'est une source qui a "
        "changé de format.",
    ),
    "taux_association_texte_image_pct": Threshold(
        "Association texte-image",
        "haut",
        90,
        75,
        "C'est la définition même du jeu de données : sans image, la publication est inutile.",
    ),
    "taux_images_telechargees_pct": Threshold(
        "Images téléchargées",
        "haut",
        80,
        60,
        "Mesure la disponibilité des médias : une URL annoncée ne vaut pas un fichier obtenu.",
    ),
    "taux_doublons_pct": Threshold(
        "Taux de doublons",
        "bas",
        5,
        15,
        "Un taux qui grimpe signale une sur-ingestion ou un identifiant devenu instable.",
    ),
    "part_source_dominante_pct": Threshold(
        "Part de la source dominante",
        "bas",
        50,
        70,
        "Un jeu de données capté par une seule source transmet son biais au modèle.",
    ),
    "age_median_heures": Threshold(
        "Âge médian",
        "bas",
        48,
        168,
        "Un détecteur de fake news doit voir l'actualité récente, pas des archives.",
    ),
    "nb_publications": Threshold(
        "Volume ingéré",
        "haut",
        80,
        40,
        "Un volume qui s'effondre trahit une source en panne.",
    ),
    "duree_totale_sec": Threshold(
        "Durée totale",
        "bas",
        90,
        300,
        "Au-delà, la fenêtre d'exécution quotidienne finit par être dépassée.",
    ),
    "failed_sources": Threshold(
        "Sources en échec",
        "bas",
        0,
        1,
        "Deux sources muettes le même jour, c'est un incident, pas un aléa réseau.",
    ),
}


def _percentage(part: float, total: float) -> float:
    """Renvoie un pourcentage arrondi, en évitant la division par zéro."""
    if total <= 0:
        return 0.0
    return round(100.0 * part / total, 1)


# --------------------------------------------------------------------------- #
# Familles d'indicateurs
# --------------------------------------------------------------------------- #
def quality_kpis(df: pd.DataFrame, stats: dict[str, int]) -> dict[str, float]:
    """Qualité des données : ce qui survit au nettoyage et ce qui est exploitable."""
    total_brut = stats.get("total_brut", 0)
    total_valide = len(df)
    if df.empty:
        return {
            "taux_validite_pct": 0.0,
            "taux_association_texte_image_pct": 0.0,
            "taux_labellise_pct": 0.0,
            "taux_doublons_pct": 0.0,
            "taux_date_connue_pct": 0.0,
            "longueur_texte_moyenne": 0.0,
        }

    return {
        "taux_validite_pct": _percentage(total_valide, total_brut),
        "taux_association_texte_image_pct": _percentage(int(df["has_image"].sum()), total_valide),
        "taux_labellise_pct": _percentage(int(df["label"].notna().sum()), total_valide),
        "taux_doublons_pct": _percentage(stats.get("doublons", 0), max(total_brut, 1)),
        # Sans date de publication, ni la fraîcheur ni les features temporelles ne
        # sont calculables : c'est un contrôle de complétude à part entière.
        "taux_date_connue_pct": _percentage(int(df["published_at"].notna().sum()), total_valide),
        "longueur_texte_moyenne": round(float(df["text_length"].mean()), 1),
    }


def volume_kpis(df: pd.DataFrame) -> dict[str, object]:
    """Volume et diversité : combien de publications, et d'où viennent-elles."""
    if df.empty:
        return {
            "nb_publications": 0,
            "nb_sources": 0,
            "part_source_dominante_pct": 0.0,
            "repartition_sources": {},
            "repartition_langues": {},
            "repartition_methodes_acces": {},
        }

    repartition = df["source"].value_counts()
    return {
        "nb_publications": len(df),
        "nb_sources": int(df["source"].nunique()),
        # Un jeu de données dominé par une seule source hérite de son biais
        # éditorial : on surveille donc la concentration, pas seulement le volume.
        "part_source_dominante_pct": _percentage(int(repartition.iloc[0]), len(df)),
        "repartition_sources": repartition.to_dict(),
        "repartition_langues": df["language"].value_counts().to_dict(),
        "repartition_methodes_acces": df["access_method"].value_counts().to_dict(),
    }


def freshness_kpis(df: pd.DataFrame, maintenant: datetime | None = None) -> dict[str, float]:
    """Fraîcheur : quel âge ont les publications que l'on vient d'ingérer."""
    clear = {"age_median_heures": 0.0, "part_moins_24h_pct": 0.0, "publications_datees": 0}
    if df.empty or "published_at" not in df.columns:
        return clear

    dates = pd.to_datetime(df["published_at"], errors="coerce", utc=True, format="mixed").dropna()
    if dates.empty:
        return clear

    reference = maintenant or datetime.now(UTC)
    ages_heures = (pd.Timestamp(reference) - dates).dt.total_seconds() / 3600

    return {
        "age_median_heures": round(float(ages_heures.median()), 1),
        "part_moins_24h_pct": _percentage(int((ages_heures <= 24).sum()), len(ages_heures)),
        "publications_datees": len(ages_heures),
    }


def performance_kpis(run: dict[str, object]) -> dict[str, float]:
    """Rapidité, coût et fiabilité de l'exécution."""
    durees = run.get("durations_sec", {}) if run else {}
    duree_totale = round(sum(float(valeur) for valeur in durees.values()), 2)
    lignes = int(run.get("rows_loaded", 0)) if run else 0
    extraites = int(run.get("rows_extracted", 0)) if run else 0
    images = run.get("images", {}) if run else {}

    return {
        "duree_extraction_sec": round(float(durees.get("extract", 0.0)), 2),
        "duree_transformation_sec": round(float(durees.get("transform", 0.0)), 2),
        "duree_chargement_sec": round(float(durees.get("load", 0.0)), 2),
        "duree_totale_sec": duree_totale,
        "debit_publications_par_sec": round(extraites / duree_totale, 1) if duree_totale else 0.0,
        # Coût : appels d'API consommés sur le quota, et disque occupé par les images.
        "appels_api_consommes": int(run.get("api_calls", 0)) if run else 0,
        "poids_images_mo": round(float(images.get("octets", 0)) / (1024 * 1024), 2),
        "taux_images_telechargees_pct": _percentage(
            float(images.get("reussies", 0)), float(images.get("tentees", 0))
        ),
        # Part des publications de ce run réellement nouvelles en base : c'est ce
        # qu'une exécution quotidienne apporte vraiment au jeu de données.
        "taux_nouveaute_pct": _percentage(lignes, extraites),
        "publications_ajoutees": lignes,
        "publications_en_base": int(run.get("rows_in_db", 0)) if run else 0,
        "failed_sources": int(run.get("failed_sources", 0)) if run else 0,
    }


def compute_kpis(
    df: pd.DataFrame, stats: dict[str, int], run: dict[str, object]
) -> dict[str, object]:
    """Agrège les quatre familles d'indicateurs en un seul dictionnaire."""
    return {
        "qualite": quality_kpis(df, stats),
        "volume": volume_kpis(df),
        "fraicheur": freshness_kpis(df),
        "performance": performance_kpis(run),
    }


# --------------------------------------------------------------------------- #
# Confrontation aux seuils du plan de monitoring
# --------------------------------------------------------------------------- #
def status_for(indicateur: str, valeur: float) -> str:
    """Classe une valeur en 'vert', 'orange' ou 'rouge' selon son seuil."""
    seuil = SEUILS[indicateur]
    if seuil.sens == "haut":
        if valeur >= seuil.vert:
            return "vert"
        return "orange" if valeur >= seuil.orange else "rouge"

    if valeur <= seuil.vert:
        return "vert"
    return "orange" if valeur <= seuil.orange else "rouge"


def evaluate_thresholds(kpis: dict[str, object]) -> list[dict[str, object]]:
    """Confronte chaque indicateur surveillé à son seuil et renvoie son status_for."""
    valeurs: dict[str, float] = {}
    for famille in kpis.values():
        for nom, valeur in famille.items():
            if nom in SEUILS and isinstance(valeur, int | float):
                valeurs[nom] = float(valeur)

    return [
        {
            "indicateur": nom,
            "libelle": SEUILS[nom].libelle,
            "valeur": valeur,
            "statut": status_for(nom, valeur),
            "attendu": (
                f"≥ {SEUILS[nom].vert:g}"
                if SEUILS[nom].sens == "haut"
                else f"≤ {SEUILS[nom].vert:g}"
            ),
            "justification": SEUILS[nom].justification,
        }
        for nom, valeur in valeurs.items()
    ]


# --------------------------------------------------------------------------- #
# Chargement des artefacts produits par le pipeline
# --------------------------------------------------------------------------- #
def _available_datasets() -> list[Path]:
    """Liste les datasets exportés, du plus récent au plus ancien."""
    fichiers = list(PROCESSED_DIR.glob("publications_*.parquet"))
    fichiers += list(PROCESSED_DIR.glob("publications_*.csv"))
    return sorted(fichiers, key=lambda p: (p.stat().st_mtime, p.name), reverse=True)


def _read_dataset(path_for: Path) -> pd.DataFrame:
    """Lit un dataset exporté, quel que soit son format."""
    return pd.read_parquet(path_for) if path_for.suffix == ".parquet" else pd.read_csv(path_for)


def load_latest_dataset() -> tuple[pd.DataFrame, dict[str, int], dict[str, object]]:
    """Charge le dataset le plus récent **accompagné de ses statistiques**.

    Les statistiques sont écrites à côté du dataset par l'étape de transformation.
    On retient donc le dataset le plus récent qui possède les siennes : afficher un
    jeu de données sans ses statistiques donnerait des indicateurs faux (un taux de
    validité à 0 %, par exemple).
    """
    for path_for in _available_datasets():
        chemin_stats = path_for.with_name(path_for.stem + "_stats.json")
        if not chemin_stats.exists():
            continue
        df = _read_dataset(path_for)
        stats = json.loads(chemin_stats.read_text(encoding="utf-8"))
        return df, stats, latest_run()

    return pd.DataFrame(), {}, {}


def _run_records() -> list[Path]:
    """Liste les fiches d'exécution, de la plus récente à la plus ancienne."""
    if not RUNS_DIR.exists():
        return []
    return sorted(
        RUNS_DIR.glob("run_*.json"), key=lambda p: (p.stat().st_mtime, p.name), reverse=True
    )


def latest_run() -> dict[str, object]:
    """Renvoie la fiche de la dernière exécution du pipeline."""
    fiches = _run_records()
    if not fiches:
        return {}
    return json.loads(fiches[0].read_text(encoding="utf-8"))


def run_history() -> pd.DataFrame:
    """Rassemble toutes les exécutions passées en un tableau chronologique.

    C'est ce qui permet de regarder une tendance plutôt qu'un instantané : un taux
    de validité de 80 % ne se lit pas de la même façon selon qu'il monte ou qu'il
    descend.
    """
    lignes = []
    for fiche in reversed(_run_records()):
        run = json.loads(fiche.read_text(encoding="utf-8"))
        stats = run.get("stats", {})
        durees = run.get("durations_sec", {})
        lignes.append(
            {
                "date": run.get("run_at", ""),
                "orchestrateur": run.get("orchestrateur", "script"),
                "publications_extraites": run.get("rows_extracted", 0),
                "publications_ajoutees": run.get("rows_loaded", 0),
                "publications_en_base": run.get("rows_in_db", 0),
                "duree_totale_sec": round(sum(float(v) for v in durees.values()), 2),
                "taux_validite_pct": _percentage(
                    stats.get("total_valide", 0), stats.get("total_brut", 0)
                ),
                "failed_sources": run.get("failed_sources", 0),
            }
        )

    if not lignes:
        return pd.DataFrame()

    historique = pd.DataFrame(lignes)
    historique["date"] = pd.to_datetime(historique["date"], errors="coerce", utc=True)
    return historique
