"""Étape T — transformation (nettoyage, validation, normalisation).

Pipeline reproductible et journalisé qui convertit les publications brutes en un
jeu de données propre et structuré, conforme au :mod:`multimodal_etl.schema`. Il est
organisé en trois temps explicites — **lecture**, **traitement**, **export** — et
modularisé en petites fonctions (``nettoie_texte``, ``valide_image``, ...) afin que
chaque transformation soit lisible, testable et tracée dans les logs.
"""

from __future__ import annotations

import html
import json
import re
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd
import tldextract
from bs4 import BeautifulSoup

from multimodal_etl.config import PROCESSED_DIR, TransformConfig, chemin_absolu, ensure_dirs
from multimodal_etl.logging_setup import get_logger
from multimodal_etl.schema import COLUMNS, Publication, genere_id, genere_source_id

logger = get_logger(__name__)

_ESPACES = re.compile(r"\s+")
# Un horodatage Unix, entier ou flottant : '1425138660' comme '1425138660.0'.
_EST_HORODATAGE = re.compile(r"\d{9,11}(\.\d+)?")


# --------------------------------------------------------------------------- #
# Fonctions unitaires de transformation
# --------------------------------------------------------------------------- #
def nettoie_texte(texte: str) -> str:
    """Nettoie un texte : retire le HTML, décode les entités, normalise les espaces."""
    if not texte:
        return ""
    sans_html = BeautifulSoup(texte, "lxml").get_text(separator=" ")
    decode = html.unescape(sans_html)
    return _ESPACES.sub(" ", decode).strip()


def valide_image(image_path: str) -> bool:
    """Vérifie que le fichier image annoncé existe réellement sur le disque.

    C'est le contrôle qui **garantit l'association texte-image** : l'étape
    d'extraction a déjà téléchargé et validé l'image avec Pillow ; on vérifie ici
    que le fichier est toujours là au moment de construire le jeu de données. Le
    chemin est relatif à la racine du projet, on le résout donc avant de tester.
    """
    if not image_path:
        return False
    return chemin_absolu(image_path).is_file()


def extrait_domaine(url: str) -> str:
    """Extrait le nom de domaine enregistré d'une URL (signal de fiabilité)."""
    if not url:
        return ""
    extrait = tldextract.extract(url)
    return extrait.registered_domain or extrait.domain or ""


def normalise_label(label: object) -> str | None:
    """Harmonise le label de vérité terrain : 'real', 'fake' ou None."""
    if not label:
        return None
    valeur = str(label).strip().lower()
    if valeur in {"real", "true", "vrai"}:
        return "real"
    if valeur in {"fake", "false", "faux"}:
        return "fake"
    return "unverified"


def normalise_langue(langue: object) -> str:
    """Ramène une langue au code ISO 639-1 sur deux lettres.

    Les sources ne s'accordent pas : le RSS déclare ``en``, NewsData.io renvoie
    ``english``, d'autres emploient ``en-GB``. Sans harmonisation, un filtre par
    langue laisserait passer la moitié des publications anglophones.
    """
    valeur = str(langue or "").strip().lower()
    if not valeur:
        return "en"

    noms = {"english": "en", "french": "fr", "francais": "fr", "spanish": "es", "german": "de"}
    if valeur in noms:
        return noms[valeur]
    # Variantes régionales : 'en-gb' et 'en_us' désignent la même langue.
    return valeur.replace("_", "-").split("-")[0][:2]


def normalise_date(date_brute: object) -> str | None:
    """Convertit une date de publication en chaîne ISO 8601, ou None si illisible.

    Les sources n'emploient pas le même format (RFC 822 pour le RSS, ISO pour les
    API, horodatage Unix pour certains jeux de données) : on ramène tout au même
    format, sans quoi le KPI de fraîcheur serait incalculable.
    """
    if not date_brute:
        return None
    texte = str(date_brute).strip()
    if not texte:
        return None

    # Horodatage Unix : Fakeddit expose un created_utc numérique, parfois écrit
    # comme un flottant ('1425138660.0').
    if _EST_HORODATAGE.fullmatch(texte):
        try:
            return datetime.fromtimestamp(float(texte), tz=UTC).isoformat(timespec="seconds")
        except (ValueError, OSError, OverflowError):
            return None

    horodatage = pd.to_datetime(texte, errors="coerce", utc=True, format="mixed")
    if pd.isna(horodatage):
        return None
    return horodatage.isoformat(timespec="seconds")


# --------------------------------------------------------------------------- #
# Construction d'une publication normalisée
# --------------------------------------------------------------------------- #
def construit_publication(
    brut: dict[str, object], config: TransformConfig, ingere_le: str
) -> Publication | None:
    """Transforme un enregistrement brut en :class:`Publication`, ou None si invalide.

    Une publication est écartée si : titre vide, texte trop court, ou (en mode
    multimodal strict) absence de fichier image — ce qui garantit l'association
    texte-image attendue par le cas d'usage.
    """
    titre = nettoie_texte(str(brut.get("title", "")))
    texte = nettoie_texte(str(brut.get("text", "")))
    url = str(brut.get("url", "")).strip()
    image_url = str(brut.get("image_url", "")).strip()
    image_path = str(brut.get("image_path", "")).strip()

    if not titre:
        return None
    if len(texte) < config.min_text_length:
        return None

    a_une_image = valide_image(image_path)
    if config.require_image and not a_une_image:
        return None

    source = str(brut.get("source", "inconnu"))
    return Publication(
        id=genere_id(url, titre),
        source_id=genere_source_id(source),
        source=source,
        source_type=str(brut.get("source_type", "inconnu")),
        access_method=str(brut.get("access_method", "inconnu")),
        domain=extrait_domaine(url),
        title=titre,
        text=texte,
        text_length=len(texte),
        image_url=image_url,
        image_path=image_path if a_une_image else "",
        image_source=str(brut.get("image_source", "aucune")) if a_une_image else "aucune",
        has_image=a_une_image,
        url=url,
        language=normalise_langue(brut.get("language")),
        ingested_at=ingere_le,
        published_at=normalise_date(brut.get("published_at")),
        label=normalise_label(brut.get("label")),
        label_source=(str(brut.get("label_source")) if brut.get("label_source") else None),
    )


# --------------------------------------------------------------------------- #
# Pipeline : lecture -> traitement -> export
# --------------------------------------------------------------------------- #
def lit_brut(path: Path) -> list[dict[str, object]]:
    """Étape 1 — lecture : charge les publications brutes depuis un fichier JSON."""
    logger.info("Transformation : lecture du fichier brut %s", path)
    with path.open("r", encoding="utf-8") as fichier:
        records = json.load(fichier)
    logger.info("Transformation : %d publications brutes lues", len(records))
    return records


def traite(
    records: list[dict[str, object]], config: TransformConfig
) -> tuple[pd.DataFrame, dict[str, int]]:
    """Étape 2 — traitement : nettoie, valide, normalise, déduplique.

    Renvoie le DataFrame final ainsi qu'un dictionnaire de statistiques (utilisé
    par les KPI et le monitoring).
    """
    ingere_le = datetime.now(UTC).isoformat(timespec="seconds")
    total_brut = len(records)

    publications = [construit_publication(brut, config, ingere_le) for brut in records]
    valides = [pub for pub in publications if pub is not None]
    logger.info(
        "Transformation : %d/%d publications valides après nettoyage", len(valides), total_brut
    )

    lignes = [pub.to_row() for pub in valides]
    df = pd.DataFrame(lignes, columns=list(COLUMNS))

    avant_dedup = len(df)
    df = df.drop_duplicates(subset="id").reset_index(drop=True)
    logger.info("Transformation : %d doublons retirés", avant_dedup - len(df))

    stats = {
        "total_brut": total_brut,
        "total_valide": len(df),
        "rejetes": int(total_brut - len(valides)),
        "doublons": int(avant_dedup - len(df)),
        "avec_image": int(df["has_image"].sum()) if not df.empty else 0,
        "labellisees": int(df["label"].notna().sum()) if not df.empty else 0,
        "images_natives": int((df["image_source"] == "native").sum()) if not df.empty else 0,
        "images_open_graph": int((df["image_source"] == "open_graph").sum()) if not df.empty else 0,
    }
    return df, stats


def exporte(
    df: pd.DataFrame,
    config: TransformConfig,
    stats: dict[str, int] | None = None,
    path: Path | None = None,
) -> Path:
    """Étape 3 — export : écrit le dataset propre et ses statistiques.

    Les statistiques sont systématiquement écrites à côté du dataset, sous le même
    nom : le tableau de bord charge toujours la paire, jamais un jeu de données
    orphelin.
    """
    ensure_dirs()
    horodatage = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
    extension = "parquet" if config.output_format == "parquet" else "csv"
    path = path or PROCESSED_DIR / f"publications_{horodatage}.{extension}"

    if extension == "parquet":
        df.to_parquet(path, index=False)
    else:
        df.to_csv(path, index=False, encoding="utf-8")
    logger.info("Transformation : dataset de %d lignes exporté vers %s", len(df), path)

    chemin_stats = path.with_name(path.stem + "_stats.json")
    with chemin_stats.open("w", encoding="utf-8") as fichier:
        json.dump(stats or {}, fichier, ensure_ascii=False, indent=2)
    logger.info("Transformation : statistiques écrites dans %s", chemin_stats)
    return path


def run_transformation(
    raw_path: Path,
    config: TransformConfig | None = None,
    output_path: Path | None = None,
) -> tuple[Path, dict[str, int]]:
    """Pipeline de transformation complet : lecture -> traitement -> export.

    Renvoie le chemin du dataset transformé et les statistiques de l'exécution.
    """
    config = config or TransformConfig()
    records = lit_brut(raw_path)
    df, stats = traite(records, config)
    sortie = exporte(df, config, stats, output_path)
    return sortie, stats
