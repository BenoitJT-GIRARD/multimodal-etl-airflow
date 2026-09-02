"""Les cinq étapes du pipeline, écrites pour être exécutables séparément.

Ce module rassemble une fonction par étape. Ce sont **exactement les mêmes
fonctions** qui sont appelées par les scripts en ligne de commande, par les
notebooks et par les ``PythonOperator`` du DAG Airflow : il n'existe qu'une seule
version de la logique métier.

Chaque étape suit le même contrat, et c'est ce contrat qui rend les tâches
indépendantes les unes des autres :

1. elle lit son entrée dans la **zone de transit** (:mod:`multimodal_etl.transit`), avec
   repli sur le dernier artefact archivé si le fichier temporaire a disparu ;
2. elle archive son résultat (``data/raw/`` ou ``data/processed/``) ;
3. elle dépose une copie de travail dans la zone de transit pour l'étape suivante ;
4. elle mesure sa durée et écrit son compte rendu.

La dernière étape, :func:`run_cleanup`, vide la zone de transit une fois les
fichiers consommés.
"""

from __future__ import annotations

import json
import time
from datetime import UTC, datetime

from multimodal_etl import transit
from multimodal_etl.config import (
    RUNS_DIR,
    ExtractionConfig,
    LoadConfig,
    TransformConfig,
    ensure_dirs,
)
from multimodal_etl.extract import run_extraction
from multimodal_etl.load import compte_publications, load_dataset
from multimodal_etl.logging_setup import get_logger
from multimodal_etl.sources import newsdata
from multimodal_etl.transform import run_transformation

logger = get_logger(__name__)


def _maintenant() -> str:
    """Horodatage ISO de l'instant présent (UTC)."""
    return datetime.now(UTC).isoformat(timespec="seconds")


# --------------------------------------------------------------------------- #
# Étape 1 — extraction
# --------------------------------------------------------------------------- #
def run_extract(config: ExtractionConfig | None = None) -> dict[str, object]:
    """Collecte les publications de toutes les sources et télécharge leurs images."""
    logger.info("=== ÉTAPE 1 — EXTRACTION ===")
    ensure_dirs()
    debut = time.perf_counter()

    archive, compte_rendu = run_extraction(config or ExtractionConfig())
    transit.depose(archive, transit.EXTRACTION)

    mesures = {
        "horodatage": _maintenant(),
        "duree_sec": round(time.perf_counter() - debut, 2),
        "archive": str(archive),
        # Un appel d'API consommé par exécution lorsque la source NewsData.io est active.
        "appels_api": 1 if newsdata.is_enabled() else 0,
        **compte_rendu,
    }
    transit.ecris_mesures("extraction", mesures)
    return mesures


# --------------------------------------------------------------------------- #
# Étape 2 — transformation
# --------------------------------------------------------------------------- #
def run_transform(config: TransformConfig | None = None) -> dict[str, object]:
    """Nettoie, valide et normalise les publications brutes en un dataset propre."""
    logger.info("=== ÉTAPE 2 — TRANSFORMATION ===")
    ensure_dirs()
    entree = transit.entree_extraction()
    if entree is None:
        raise FileNotFoundError(
            "Aucune extraction disponible : lancez d'abord l'étape d'extraction."
        )

    debut = time.perf_counter()
    archive, stats = run_transformation(entree, config or TransformConfig())
    transit.depose(archive, transit.DATASET)

    mesures = {
        "horodatage": _maintenant(),
        "duree_sec": round(time.perf_counter() - debut, 2),
        "entree": str(entree),
        "archive": str(archive),
        "stats": stats,
    }
    transit.ecris_mesures("transformation", mesures)
    return mesures


# --------------------------------------------------------------------------- #
# Étape 3 — chargement
# --------------------------------------------------------------------------- #
def run_load(config: LoadConfig | None = None) -> dict[str, object]:
    """Charge le dataset dans la base relationnelle, en n'ajoutant que les nouveautés."""
    logger.info("=== ÉTAPE 3 — CHARGEMENT ===")
    config = config or LoadConfig()
    entree = transit.entree_dataset()
    if entree is None:
        raise FileNotFoundError(
            "Aucun dataset disponible : lancez d'abord l'étape de transformation."
        )

    debut = time.perf_counter()
    bilan = load_dataset(entree, config)

    mesures = {
        "horodatage": _maintenant(),
        "duree_sec": round(time.perf_counter() - debut, 2),
        "entree": str(entree),
        "bilan_tables": bilan,
        "publications_ajoutees": bilan.get(config.table_name, 0),
        "publications_en_base": compte_publications(config),
    }
    transit.ecris_mesures("chargement", mesures)
    return mesures


# --------------------------------------------------------------------------- #
# Étape 4 — métriques d'exécution
# --------------------------------------------------------------------------- #
def run_metrics(orchestrateur: str = "script") -> dict[str, object]:
    """Consolide les mesures des trois étapes en une fiche d'exécution.

    Cette fiche est le seul historique dont le tableau de bord a besoin : une par
    exécution, conservée dans ``data/processed/runs/``.
    """
    logger.info("=== ÉTAPE 4 — MÉTRIQUES ===")
    extraction = transit.lit_mesures("extraction")
    transformation = transit.lit_mesures("transformation")
    chargement = transit.lit_mesures("chargement")

    images = extraction.get("images", {}) or {}
    run = {
        "run_at": _maintenant(),
        "orchestrateur": orchestrateur,
        "durations_sec": {
            "extract": extraction.get("duree_sec", 0.0),
            "transform": transformation.get("duree_sec", 0.0),
            "load": chargement.get("duree_sec", 0.0),
        },
        "rows_extracted": extraction.get("publications_extraites", 0),
        "rows_loaded": chargement.get("publications_ajoutees", 0),
        "rows_in_db": chargement.get("publications_en_base", 0),
        "api_calls": extraction.get("appels_api", 0),
        "bilan_sources": extraction.get("bilan_sources", {}),
        "failed_sources": extraction.get("failed_sources", 0),
        "images": images,
        "stats": transformation.get("stats", {}),
        "dataset_path": transformation.get("archive", ""),
    }

    RUNS_DIR.mkdir(parents=True, exist_ok=True)
    fichier = RUNS_DIR / f"run_{datetime.now(UTC).strftime('%Y%m%d_%H%M%S')}.json"
    fichier.write_text(json.dumps(run, ensure_ascii=False, indent=2), encoding="utf-8")
    logger.info("Métriques : fiche d'exécution écrite dans %s", fichier)

    run["fichier"] = str(fichier)
    return run


# --------------------------------------------------------------------------- #
# Étape 5 — nettoyage de la zone de transit
# --------------------------------------------------------------------------- #
def run_cleanup() -> dict[str, object]:
    """Supprime les fichiers temporaires une fois qu'ils ont tous été consommés."""
    logger.info("=== ÉTAPE 5 — NETTOYAGE ===")
    supprimes = transit.vide()
    return {"fichiers_supprimes": supprimes, "nombre": len(supprimes)}
