"""Connecteur 4 — Fakeddit, jeu de données multimodal hébergé sur Kaggle.

Fakeddit (Nakamura *et al.*, 2020) rassemble plus d'un million de publications
Reddit associant **un titre et une image**, avec trois niveaux de labels (binaire,
3 classes, 6 classes). C'est la source la plus proche du cas d'usage : elle est
nativement multimodale, contrairement à FakeNewsNet.

Le téléchargement d'un jeu Kaggle demande un compte et une clé d'API. Plutôt que
d'introduire une dépendance et un secret supplémentaires dans le pipeline, on
procède comme en entreprise pour un jeu de référence figé : **le fichier est
téléchargé une fois, à la main**, puis déposé dans ``data/raw/kaggle/``. Le
connecteur se contente de le lire.

Si le fichier n'est pas présent, le connecteur bascule sur un **échantillon de
démonstration versionné** (``data/samples/fakeddit_sample.tsv``) : contenus
fabriqués, structure de colonnes identique à celle du jeu réel, images libres de
droits. Le pipeline reste ainsi exécutable par n'importe qui, immédiatement.
"""

from __future__ import annotations

import csv
from pathlib import Path

from multimodal_etl.config import RAW_DIR, SAMPLES_DIR, ExtractionConfig
from multimodal_etl.logging_setup import get_logger

logger = get_logger(__name__)

DOSSIER_KAGGLE = RAW_DIR / "kaggle"
ECHANTILLON = SAMPLES_DIR / "fakeddit_sample.tsv"

# Fakeddit code la vérité terrain dans la colonne 2_way_label : 1 = authentique.
_LABELS = {"1": "real", "0": "fake"}


def choisit_fichier() -> tuple[Path, bool] | None:
    """Choisit la source de données : jeu Kaggle réel si présent, sinon échantillon.

    Renvoie le chemin et un booléen indiquant s'il s'agit du jeu réel.
    """
    if DOSSIER_KAGGLE.exists():
        fichiers = sorted(DOSSIER_KAGGLE.glob("*.tsv"))
        if fichiers:
            logger.info("Fakeddit : jeu Kaggle détecté (%s)", fichiers[0].name)
            return fichiers[0], True

    if ECHANTILLON.exists():
        logger.info("Fakeddit : jeu Kaggle absent, utilisation de %s", ECHANTILLON.name)
        return ECHANTILLON, False

    return None


def lit_tsv(chemin: Path) -> list[dict[str, str]]:
    """Lit un fichier Fakeddit (valeurs séparées par des tabulations)."""
    with chemin.open("r", encoding="utf-8", newline="") as fichier:
        return list(csv.DictReader(fichier, delimiter="\t"))


def _construit_record(ligne: dict[str, str]) -> dict[str, object]:
    """Transforme une ligne Fakeddit en dictionnaire brut normalisé."""
    titre = ligne.get("clean_title") or ligne.get("title") or ""
    image_url = ligne.get("image_url", "").strip()
    return {
        # Fakeddit est une seule source, quel que soit le sous-forum d'origine :
        # découper par subreddit fragmenterait les répartitions en une quinzaine
        # de lignes sans intérêt pour le suivi.
        "source": "fakeddit",
        "source_type": "dataset",
        "access_method": "telechargement_kaggle",
        "title": titre,
        # Fakeddit ne publie pas de corps d'article : le titre est le signal texte.
        "text": titre,
        # Fakeddit identifie chaque publication par son identifiant Reddit : on
        # reconstruit le permalien, qui sert de clé de traçabilité et de déduplication.
        "url": f"https://redd.it/{ligne.get('id', '')}",
        "image_url": image_url,
        "image_source": "native" if image_url else "aucune",
        "published_at": ligne.get("created_utc", ""),
        "language": "en",
        "label": _LABELS.get(ligne.get("2_way_label", "").strip(), "unverified"),
        "label_source": "fakeddit",
    }


def fetch_fakeddit(config: ExtractionConfig) -> list[dict[str, object]]:
    """Charge les publications multimodales Fakeddit."""
    choix = choisit_fichier()
    if choix is None:
        logger.warning(
            "Fakeddit : aucune donnée disponible. Déposez le fichier .tsv dans %s "
            "(procédure dans le rapport d'exploration).",
            DOSSIER_KAGGLE,
        )
        return []

    chemin, est_reel = choix
    lignes = lit_tsv(chemin)

    # Le jeu réel ne garde que les publications réellement multimodales.
    avec_image = [ligne for ligne in lignes if ligne.get("image_url", "").strip()]
    retenues = avec_image[: config.max_items_per_source]

    records = [_construit_record(ligne) for ligne in retenues]
    logger.info(
        "Fakeddit : %d publications chargées depuis %s (%s)",
        len(records),
        chemin.name,
        "jeu Kaggle réel" if est_reel else "échantillon de démonstration",
    )
    return records
