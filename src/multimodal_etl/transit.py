"""Zone de transit — passage de relais entre deux étapes du pipeline.

Airflow permet de relancer **n'importe quelle tâche d'un DAG indépendamment des
autres**. Pour que ce soit vrai ici, aucune étape ne reçoit ses données de la
précédente par la mémoire : chaque étape **écrit son résultat sur le disque**, dans
``data/interim/``, et l'étape suivante **relit ce fichier**.

Trois conséquences pratiques :

* une tâche peut être rejouée seule, sans rejouer celles d'avant ;
* si le fichier de transit a disparu, l'étape se rabat sur le dernier artefact
  archivé (``data/raw/`` ou ``data/processed/``) : elle reste exécutable ;
* une dernière tâche du DAG **vide la zone de transit** une fois les données
  consommées, pour ne pas laisser traîner de fichiers temporaires.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

from multimodal_etl.config import INTERIM_DIR, PROCESSED_DIR, RAW_DIR
from multimodal_etl.logging_setup import get_logger

logger = get_logger(__name__)

# Noms des fichiers échangés entre les étapes. Ils sont fixes : c'est ce qui permet
# à une tâche de retrouver l'entrée qui l'attend sans rien savoir de l'exécution
# qui l'a produite.
EXTRACTION = "extraction.json"
DATASET = "dataset.parquet"

# Mesures déposées par chaque étape et relues par l'étape « métriques ».
MESURES = {
    "extraction": "mesures_extraction.json",
    "transformation": "mesures_transformation.json",
    "chargement": "mesures_chargement.json",
}


def path_for(nom: str) -> Path:
    """Renvoie le chemin d'un fichier de la zone de transit."""
    return INTERIM_DIR / nom


def _latest_artefact(dossier: Path, motif: str) -> Path | None:
    """Renvoie le fichier le plus récent d'un dossier correspondant à un motif.

    Le nom du fichier départage deux artefacts écrits dans la même seconde : tous
    les noms produits par le pipeline portent un horodatage triable.
    """
    if not dossier.exists():
        return None
    fichiers = sorted(dossier.glob(motif), key=lambda p: (p.stat().st_mtime, p.name), reverse=True)
    return fichiers[0] if fichiers else None


def stage(artefact: Path, nom: str) -> Path:
    """Copie un artefact produit par une étape dans la zone de transit."""
    INTERIM_DIR.mkdir(parents=True, exist_ok=True)
    destination = path_for(nom)
    shutil.copy2(artefact, destination)
    logger.info("Transit : '%s' déposé pour l'étape suivante", nom)
    return destination


def write_metrics(etape: str, mesures: dict[str, object]) -> Path:
    """Enregistre les mesures d'une étape (durée, volumes) dans la zone de transit."""
    INTERIM_DIR.mkdir(parents=True, exist_ok=True)
    destination = path_for(MESURES[etape])
    destination.write_text(
        json.dumps(mesures, ensure_ascii=False, indent=2, default=str), encoding="utf-8"
    )
    return destination


def read_metrics(etape: str) -> dict[str, object]:
    """Relit les mesures d'une étape, ou un dictionnaire clear si elles manquent."""
    fichier = path_for(MESURES[etape])
    if not fichier.exists():
        logger.warning("Transit : mesures manquantes pour l'étape '%s'", etape)
        return {}
    return json.loads(fichier.read_text(encoding="utf-8"))


def extraction_input() -> Path | None:
    """Renvoie le fichier brut à transformer.

    On privilégie le fichier déposé par la tâche d'extraction ; s'il est absent
    (tâche rejouée seule, zone de transit déjà nettoyée), on reprend la dernière
    extraction archivée.
    """
    fichier = path_for(EXTRACTION)
    if fichier.exists():
        return fichier

    repli = _latest_artefact(RAW_DIR, "raw_publications_*.json")
    if repli is not None:
        logger.warning("Transit : '%s' absent, reprise de l'archive %s", EXTRACTION, repli.name)
    return repli


def dataset_input() -> Path | None:
    """Renvoie le dataset transformé à charger, avec le même mécanisme de repli."""
    fichier = path_for(DATASET)
    if fichier.exists():
        return fichier

    repli = _latest_artefact(PROCESSED_DIR, "publications_*.parquet")
    if repli is not None:
        logger.warning("Transit : '%s' absent, reprise de l'archive %s", DATASET, repli.name)
    return repli


def clear() -> list[str]:
    """Supprime tous les fichiers de la zone de transit et renvoie leurs noms."""
    if not INTERIM_DIR.exists():
        return []

    supprimes = []
    for fichier in sorted(INTERIM_DIR.iterdir()):
        if fichier.is_file():
            fichier.unlink()
            supprimes.append(fichier.name)

    logger.info("Transit : %d fichiers temporaires supprimés", len(supprimes))
    return supprimes
