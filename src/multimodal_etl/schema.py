"""Schéma de la publication multimodale.

Ce module est la **source unique de vérité** du jeu de données : il décrit chaque
champ (nom, type, rôle dans le cas d'usage IA) et fournit la structure
:class:`Publication` utilisée en sortie de transformation. Le schéma conceptuel
et la documentation sont générés à partir de :data:`FIELDS`, ce qui
garantit que diagramme, code et données restent toujours alignés.

Chaque champ est rattaché à une **entité conceptuelle** (:data:`ENTITES`) : c'est
cette information qui permet de dessiner le modèle conceptuel et de découper le
chargement en tables reliées par des clés de jointure.
"""

from __future__ import annotations

import hashlib
from dataclasses import asdict, dataclass
from typing import NamedTuple


class FieldSpec(NamedTuple):
    """Description d'un champ du schéma, exploitée pour générer la documentation."""

    name: str
    dtype: str
    role: str  # rôle dans le cas d'usage : NLP, VISION, TARGET, METADATA, KEY
    entite: str  # entité conceptuelle d'appartenance (cf. ENTITES)
    required: bool
    description: str


# Entités du modèle conceptuel, dans l'ordre de lecture du diagramme.
ENTITES: tuple[str, ...] = (
    "PUBLICATION",
    "SOURCE",
    "CONTENU_TEXTE",
    "CONTENU_IMAGE",
    "LABEL",
)

# Description métier de chaque champ. Sert à la fois de documentation, de base pour
# le diagramme conceptuel et de plan de découpage des tables (cf. load.py).
FIELDS: tuple[FieldSpec, ...] = (
    FieldSpec(
        "id",
        "string",
        "KEY",
        "PUBLICATION",
        True,
        "Identifiant unique de la publication (hash SHA-1 de l'URL + titre).",
    ),
    FieldSpec(
        "source_id",
        "string",
        "KEY",
        "PUBLICATION",
        True,
        "Clé de jointure vers l'entité SOURCE (hash du nom de source).",
    ),
    FieldSpec(
        "source",
        "string",
        "METADATA",
        "SOURCE",
        True,
        "Source précise de la publication (ex. rss:bbc_news, newsdata, fakenewsnet:politifact).",
    ),
    FieldSpec(
        "source_type",
        "string",
        "METADATA",
        "SOURCE",
        True,
        "Famille de source : 'rss', 'api' ou 'dataset'.",
    ),
    FieldSpec(
        "access_method",
        "string",
        "METADATA",
        "SOURCE",
        True,
        "Méthode d'accès employée : 'flux_rss', 'api_rest', 'telechargement_github' "
        "ou 'telechargement_kaggle'.",
    ),
    FieldSpec(
        "domain",
        "string",
        "METADATA",
        "PUBLICATION",
        True,
        "Nom de domaine de l'éditeur de l'article (signal de fiabilité).",
    ),
    FieldSpec(
        "title",
        "string",
        "NLP",
        "CONTENU_TEXTE",
        True,
        "Titre de la publication — signal textuel principal pour le modèle NLP.",
    ),
    FieldSpec(
        "text",
        "string",
        "NLP",
        "CONTENU_TEXTE",
        True,
        "Corps ou résumé nettoyé — entrée texte pour la classification.",
    ),
    FieldSpec(
        "text_length",
        "integer",
        "METADATA",
        "CONTENU_TEXTE",
        True,
        "Longueur du texte nettoyé (nombre de caractères) — feature et contrôle qualité.",
    ),
    FieldSpec(
        "image_url",
        "string",
        "VISION",
        "CONTENU_IMAGE",
        True,
        "URL d'origine de l'image principale.",
    ),
    FieldSpec(
        "image_path",
        "string",
        "VISION",
        "CONTENU_IMAGE",
        True,
        "Chemin du fichier image téléchargé sur disque — entrée réelle du modèle vision.",
    ),
    FieldSpec(
        "image_source",
        "string",
        "METADATA",
        "CONTENU_IMAGE",
        True,
        "Provenance de l'image : 'native' (fournie par la source) ou 'open_graph' "
        "(métadonnée de l'article).",
    ),
    FieldSpec(
        "has_image",
        "boolean",
        "VISION",
        "CONTENU_IMAGE",
        True,
        "Vrai si le fichier image est présent sur disque — garantit le lien texte-image.",
    ),
    FieldSpec(
        "url",
        "string",
        "METADATA",
        "PUBLICATION",
        True,
        "URL de l'article d'origine (traçabilité, déduplication).",
    ),
    FieldSpec(
        "language",
        "string",
        "METADATA",
        "PUBLICATION",
        True,
        "Langue détectée/déclarée (code ISO 639-1, ex. 'en').",
    ),
    FieldSpec(
        "published_at",
        "datetime",
        "METADATA",
        "PUBLICATION",
        False,
        "Date de publication (ISO 8601) — utile pour la fraîcheur et les features temporelles.",
    ),
    FieldSpec(
        "ingested_at",
        "datetime",
        "METADATA",
        "PUBLICATION",
        True,
        "Horodatage de l'ingestion par le pipeline (traçabilité, monitoring).",
    ),
    FieldSpec(
        "label",
        "string",
        "TARGET",
        "LABEL",
        False,
        "Vérité terrain quand elle existe : 'real', 'fake' ou 'unverified'.",
    ),
    FieldSpec(
        "label_source",
        "string",
        "METADATA",
        "LABEL",
        False,
        "Origine du label (ex. 'fakenewsnet:politifact') ou null si non labellisé.",
    ),
)

# Liste ordonnée des colonnes du dataset final.
COLUMNS: tuple[str, ...] = tuple(spec.name for spec in FIELDS)


def fields_of(entite: str) -> tuple[FieldSpec, ...]:
    """Renvoie les champs rattachés à une entité conceptuelle donnée."""
    return tuple(spec for spec in FIELDS if spec.entite == entite)


# Les empreintes ci-dessous servent uniquement à fabriquer des identifiants stables
# et courts : elles ne protègent rien, d'où `usedforsecurity=False`.
def generate_id(url: str, title: str) -> str:
    """Génère l'identifiant stable d'une publication à partir de l'URL et du titre."""
    graine = f"{url}|{title}".encode()
    return hashlib.sha1(graine, usedforsecurity=False).hexdigest()[:16]


def generate_source_id(source: str) -> str:
    """Génère la clé de jointure d'une source à partir de son nom."""
    return hashlib.sha1(source.encode(), usedforsecurity=False).hexdigest()[:12]


@dataclass(slots=True)
class Publication:
    """Une publication multimodale normalisée, prête pour l'entraînement IA."""

    id: str
    source_id: str
    source: str
    source_type: str
    access_method: str
    domain: str
    title: str
    text: str
    text_length: int
    image_url: str
    image_path: str
    image_source: str
    has_image: bool
    url: str
    language: str
    ingested_at: str
    published_at: str | None = None
    label: str | None = None
    label_source: str | None = None

    def to_row(self) -> dict[str, object]:
        """Convertit la publication en dictionnaire (une ligne du dataset)."""
        row = asdict(self)
        # Réordonne selon COLUMNS pour un export stable et lisible.
        return {col: row[col] for col in COLUMNS}
