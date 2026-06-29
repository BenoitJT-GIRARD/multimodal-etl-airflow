"""Etape T — transformation (nettoyage, validation, normalisation).

Pipeline reproductible et journalise qui convertit les publications brutes en un
jeu de donnees propre et structure, conforme au :mod:`multimodal_etl.schema`. Il est
organise en trois temps explicites — **lecture**, **traitement**, **export** — et
modularise en petites fonctions (``nettoie_texte``, ``valide_image``, ...) afin que
chaque transformation soit lisible, testable et tracee dans les logs.
"""

from __future__ import annotations

import hashlib
import html
import json
import re
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd
import tldextract
from bs4 import BeautifulSoup

from multimodal_etl.config import PROCESSED_DIR, TransformConfig, ensure_dirs
from multimodal_etl.logging_setup import get_logger
from multimodal_etl.schema import COLUMNS, Publication

logger = get_logger(__name__)

_WHITESPACE_RE = re.compile(r"\s+")


# --------------------------------------------------------------------------- #
# Fonctions unitaires de transformation
# --------------------------------------------------------------------------- #
def nettoie_texte(texte: str) -> str:
    """Nettoie un texte : retire le HTML, decode les entites, normalise les espaces."""
    if not texte:
        return ""
    sans_html = BeautifulSoup(texte, "lxml").get_text(separator=" ")
    decode = html.unescape(sans_html)
    return _WHITESPACE_RE.sub(" ", decode).strip()


def valide_image(image_url: str, config: TransformConfig) -> bool:
    """Verifie qu'une URL d'image est plausible et exploitable.

    Controle le schema HTTP(S) et l'extension de fichier (en ignorant une
    eventuelle chaine de requete). On ne telecharge pas l'image ici pour garder
    l'etape rapide et hors-ligne ; la verification reseau releve du monitoring.
    """
    if not image_url or not image_url.lower().startswith(("http://", "https://")):
        return False
    chemin = image_url.split("?", 1)[0].lower()
    return chemin.endswith(config.valid_image_extensions)


def extrait_domaine(url: str) -> str:
    """Extrait le nom de domaine enregistre d'une URL (signal de fiabilite)."""
    if not url:
        return ""
    extrait = tldextract.extract(url)
    return extrait.registered_domain or extrait.domain or ""


def genere_id(url: str, title: str) -> str:
    """Genere un identifiant stable et unique a partir de l'URL et du titre."""
    graine = f"{url}|{title}".encode()
    return hashlib.sha1(graine).hexdigest()[:16]


def normalise_label(label: object) -> str | None:
    """Harmonise le label de verite terrain : 'real', 'fake' ou None."""
    if not label:
        return None
    valeur = str(label).strip().lower()
    if valeur in {"real", "true", "vrai"}:
        return "real"
    if valeur in {"fake", "false", "faux"}:
        return "fake"
    return "unverified"


# --------------------------------------------------------------------------- #
# Construction d'une publication normalisee
# --------------------------------------------------------------------------- #
def construit_publication(
    brut: dict[str, object], config: TransformConfig, ingere_le: str
) -> Publication | None:
    """Transforme un enregistrement brut en :class:`Publication`, ou None si invalide.

    Une publication est ecartee si : titre vide, texte trop court, ou (en mode
    multimodal strict) absence d'image valide — ce qui garantit l'association
    texte-image attendue par le cas d'usage.
    """
    titre = nettoie_texte(str(brut.get("title", "")))
    texte = nettoie_texte(str(brut.get("text", "")))
    url = str(brut.get("url", "")).strip()
    image_url = str(brut.get("image_url", "")).strip()

    if not titre:
        return None
    if len(texte) < config.min_text_length:
        return None

    image_valide = valide_image(image_url, config)
    if config.require_image and not image_valide:
        return None

    return Publication(
        id=genere_id(url, titre),
        source=str(brut.get("source", "inconnu")),
        source_type=str(brut.get("source_type", "inconnu")),
        title=titre,
        text=texte,
        url=url,
        image_url=image_url if image_valide else "",
        language=str(brut.get("language", "en")),
        domain=extrait_domaine(url),
        has_image=image_valide,
        text_length=len(texte),
        ingested_at=ingere_le,
        published_at=str(brut.get("published_at", "")) or None,
        label=normalise_label(brut.get("label")),
        label_source=(str(brut.get("label_source")) if brut.get("label_source") else None),
    )


# --------------------------------------------------------------------------- #
# Pipeline : lecture -> traitement -> export
# --------------------------------------------------------------------------- #
def lit_brut(path: Path) -> list[dict[str, object]]:
    """Etape 1 — lecture : charge les publications brutes depuis un fichier JSON."""
    logger.info("Transformation : lecture du fichier brut %s", path)
    with path.open("r", encoding="utf-8") as handle:
        records = json.load(handle)
    logger.info("Transformation : %d publications brutes lues", len(records))
    return records


def traite(
    records: list[dict[str, object]], config: TransformConfig
) -> tuple[pd.DataFrame, dict[str, int]]:
    """Etape 2 — traitement : nettoie, valide, normalise, deduplique.

    Renvoie le DataFrame final ainsi qu'un dictionnaire de statistiques (utilise
    par les KPI et le monitoring).
    """
    ingere_le = datetime.now(UTC).isoformat(timespec="seconds")
    total_brut = len(records)

    publications = [construit_publication(brut, config, ingere_le) for brut in records]
    valides = [pub for pub in publications if pub is not None]
    logger.info(
        "Transformation : %d/%d publications valides apres nettoyage", len(valides), total_brut
    )

    lignes = [pub.to_row() for pub in valides]
    df = pd.DataFrame(lignes, columns=list(COLUMNS))

    avant_dedup = len(df)
    df = df.drop_duplicates(subset="id").reset_index(drop=True)
    logger.info("Transformation : %d doublons retires", avant_dedup - len(df))

    stats = {
        "total_brut": total_brut,
        "total_valide": len(df),
        "rejetes": int(total_brut - len(valides)),
        "doublons": int(avant_dedup - len(df)),
        "avec_image": int(df["has_image"].sum()) if not df.empty else 0,
        "labellisees": int(df["label"].notna().sum()) if not df.empty else 0,
    }
    return df, stats


def exporte(df: pd.DataFrame, config: TransformConfig, path: Path | None = None) -> Path:
    """Etape 3 — export : ecrit le dataset propre en Parquet ou CSV."""
    ensure_dirs()
    horodatage = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
    extension = "parquet" if config.output_format == "parquet" else "csv"
    path = path or PROCESSED_DIR / f"publications_{horodatage}.{extension}"

    if extension == "parquet":
        df.to_parquet(path, index=False)
    else:
        df.to_csv(path, index=False, encoding="utf-8")
    logger.info("Transformation : dataset de %d lignes exporte vers %s", len(df), path)
    return path


def run_transformation(
    raw_path: Path,
    config: TransformConfig | None = None,
    output_path: Path | None = None,
) -> tuple[Path, dict[str, int]]:
    """Pipeline de transformation complet : lecture -> traitement -> export.

    Renvoie le chemin du dataset transforme et les statistiques de l'execution.
    """
    config = config or TransformConfig()
    records = lit_brut(raw_path)
    df, stats = traite(records, config)
    out = exporte(df, config, output_path)

    # On persiste les statistiques pour le tableau de bord KPI et le monitoring.
    stats_path = out.with_name(out.stem + "_stats.json")
    with stats_path.open("w", encoding="utf-8") as handle:
        json.dump(stats, handle, ensure_ascii=False, indent=2)
    logger.info("Transformation : statistiques ecrites dans %s", stats_path)
    return out, stats
