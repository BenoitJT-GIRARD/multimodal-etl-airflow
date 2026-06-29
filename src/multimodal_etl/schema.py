"""Schema de la publication multimodale.

Ce module est la **source unique de verite** du jeu de donnees : il decrit chaque
champ (nom, type, role dans le cas d'usage IA) et fournit la structure
:class:`Publication` utilisee en sortie de transformation. Le schema conceptuel
et la documentation sont generes a partir de :data:`FIELDS`, ce qui
garantit que diagramme, code et donnees restent toujours alignes.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import NamedTuple


class FieldSpec(NamedTuple):
    """Description d'un champ du schema, exploitee pour generer la documentation."""

    name: str
    dtype: str
    role: str  # role dans le cas d'usage : NLP, VISION, TARGET, METADATA, KEY
    required: bool
    description: str


# Description metier de chaque champ. Sert a la fois de documentation et de base
# pour le diagramme conceptuel (cf. scripts/build_schema_diagram.py).
FIELDS: tuple[FieldSpec, ...] = (
    FieldSpec(
        "id",
        "string",
        "KEY",
        True,
        "Identifiant unique de la publication (hash SHA-1 de l'URL + titre).",
    ),
    FieldSpec(
        "source",
        "string",
        "METADATA",
        True,
        "Source precise de la publication (ex. rss:bbc_news, newsdata, fakenewsnet:politifact).",
    ),
    FieldSpec(
        "source_type", "string", "METADATA", True, "Famille de source : 'rss', 'api' ou 'dataset'."
    ),
    FieldSpec(
        "title",
        "string",
        "NLP",
        True,
        "Titre de la publication — signal textuel principal pour le modele NLP.",
    ),
    FieldSpec(
        "text",
        "string",
        "NLP",
        True,
        "Corps ou resume nettoye — entree texte pour la classification.",
    ),
    FieldSpec(
        "url",
        "string",
        "METADATA",
        True,
        "URL de l'article d'origine (tracabilite, deduplication).",
    ),
    FieldSpec(
        "image_url",
        "string",
        "VISION",
        True,
        "URL de l'image principale — entree visuelle pour le modele multimodal.",
    ),
    FieldSpec(
        "published_at",
        "datetime",
        "METADATA",
        False,
        "Date de publication (ISO 8601) — utile pour la fraicheur et les features temporelles.",
    ),
    FieldSpec(
        "language",
        "string",
        "METADATA",
        True,
        "Langue detectee/declaree (code ISO 639-1, ex. 'en').",
    ),
    FieldSpec(
        "domain",
        "string",
        "METADATA",
        True,
        "Nom de domaine de l'editeur (signal de fiabilite de la source).",
    ),
    FieldSpec(
        "label",
        "string",
        "TARGET",
        False,
        "Verite terrain quand elle existe : 'real', 'fake' ou 'unverified'.",
    ),
    FieldSpec(
        "label_source",
        "string",
        "METADATA",
        False,
        "Origine du label (ex. 'fakenewsnet:politifact') ou null si non labellise.",
    ),
    FieldSpec(
        "has_image",
        "boolean",
        "VISION",
        True,
        "Vrai si une image valide est associee — garantit le lien texte-image.",
    ),
    FieldSpec(
        "text_length",
        "integer",
        "METADATA",
        True,
        "Longueur du texte nettoye (nombre de caracteres) — feature et controle qualite.",
    ),
    FieldSpec(
        "ingested_at",
        "datetime",
        "METADATA",
        True,
        "Horodatage de l'ingestion par le pipeline (tracabilite, monitoring).",
    ),
)

# Liste ordonnee des colonnes du dataset final.
COLUMNS: tuple[str, ...] = tuple(spec.name for spec in FIELDS)


@dataclass(slots=True)
class Publication:
    """Une publication multimodale normalisee, prete pour l'entrainement IA."""

    id: str
    source: str
    source_type: str
    title: str
    text: str
    url: str
    image_url: str
    language: str
    domain: str
    has_image: bool
    text_length: int
    ingested_at: str
    published_at: str | None = None
    label: str | None = None
    label_source: str | None = None

    def to_row(self) -> dict[str, object]:
        """Convertit la publication en dictionnaire (une ligne du dataset)."""
        row = asdict(self)
        # Reordonne selon COLUMNS pour un export stable et lisible.
        return {col: row[col] for col in COLUMNS}
