"""Indicateurs de performance (KPI) du pipeline ETL.

Ce module calcule les KPI demandes a l'etape 5 — **precision** des donnees
(part d'entrees valides), **rapidite** (temps par etape) et **cout** (ressources
consommees) — ainsi que des indicateurs metier propres au cas d'usage multimodal
(taux d'association texte-image, part de publications labellisees, diversite des
sources). Les fonctions sont pures : elles prennent des donnees en entree et
renvoient un dictionnaire, ce qui les rend faciles a tester et a afficher.
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from multimodal_etl.config import PROCESSED_DIR

RUNS_DIR = PROCESSED_DIR / "runs"


def _pourcentage(part: float, total: float) -> float:
    """Renvoie un pourcentage arrondi, en evitant la division par zero."""
    if total <= 0:
        return 0.0
    return round(100.0 * part / total, 1)


def kpis_qualite(df: pd.DataFrame, stats: dict[str, int]) -> dict[str, float]:
    """KPI de qualite des donnees (precision, multimodalite, labellisation)."""
    total_brut = stats.get("total_brut", 0)
    total_valide = len(df)
    avec_image = int(df["has_image"].sum()) if not df.empty else 0
    labellisees = int(df["label"].notna().sum()) if not df.empty else 0

    return {
        "taux_validite_pct": _pourcentage(total_valide, total_brut),
        "taux_association_texte_image_pct": _pourcentage(avec_image, total_valide),
        "taux_labellise_pct": _pourcentage(labellisees, total_valide),
        "taux_doublons_pct": _pourcentage(stats.get("doublons", 0), max(total_brut, 1)),
        "longueur_texte_moyenne": round(float(df["text_length"].mean()), 1)
        if not df.empty
        else 0.0,
    }


def kpis_volume(df: pd.DataFrame) -> dict[str, object]:
    """KPI de volume et de diversite des sources."""
    if df.empty:
        return {
            "nb_publications": 0,
            "nb_sources": 0,
            "repartition_sources": {},
            "repartition_langues": {},
        }
    return {
        "nb_publications": len(df),
        "nb_sources": int(df["source"].nunique()),
        "repartition_sources": df["source"].value_counts().to_dict(),
        "repartition_langues": df["language"].value_counts().to_dict(),
    }


def kpis_performance(run: dict[str, object]) -> dict[str, float]:
    """KPI de rapidite et de cout, a partir des metriques d'une execution."""
    durees = run.get("durations_sec", {}) if run else {}
    duree_totale = round(sum(float(v) for v in durees.values()), 2)
    nb_publications = int(run.get("rows_loaded", 0)) if run else 0
    debit = round(nb_publications / duree_totale, 1) if duree_totale > 0 else 0.0

    return {
        "duree_extraction_sec": round(float(durees.get("extract", 0.0)), 2),
        "duree_transformation_sec": round(float(durees.get("transform", 0.0)), 2),
        "duree_chargement_sec": round(float(durees.get("load", 0.0)), 2),
        "duree_totale_sec": duree_totale,
        "debit_publications_par_sec": debit,
        # Cout : nombre d'appels API consommes (quota) — proxy de cout principal.
        "appels_api_consommes": int(run.get("api_calls", 0)) if run else 0,
    }


def compute_kpis(
    df: pd.DataFrame, stats: dict[str, int], run: dict[str, object]
) -> dict[str, object]:
    """Agrege tous les KPI en un seul dictionnaire."""
    return {
        "qualite": kpis_qualite(df, stats),
        "volume": kpis_volume(df),
        "performance": kpis_performance(run),
    }


# --------------------------------------------------------------------------- #
# Chargement des artefacts les plus recents (pour le tableau de bord)
# --------------------------------------------------------------------------- #
def _dernier_fichier(motif: str, dossier: Path = PROCESSED_DIR) -> Path | None:
    """Renvoie le fichier le plus recent correspondant a un motif glob."""
    fichiers = sorted(dossier.glob(motif), key=lambda p: p.stat().st_mtime, reverse=True)
    return fichiers[0] if fichiers else None


def charge_dernier_dataset() -> tuple[pd.DataFrame, dict[str, int], dict[str, object]]:
    """Charge le dataset, les stats et les metriques d'execution les plus recents."""
    dataset = _dernier_fichier("publications_*.parquet") or _dernier_fichier("publications_*.csv")
    if dataset is None:
        return pd.DataFrame(), {}, {}

    df = pd.read_parquet(dataset) if dataset.suffix == ".parquet" else pd.read_csv(dataset)

    stats_path = dataset.with_name(dataset.stem + "_stats.json")
    stats = json.loads(stats_path.read_text(encoding="utf-8")) if stats_path.exists() else {}

    run_path = _dernier_fichier("run_*.json", RUNS_DIR) if RUNS_DIR.exists() else None
    run = json.loads(run_path.read_text(encoding="utf-8")) if run_path else {}

    return df, stats, run
