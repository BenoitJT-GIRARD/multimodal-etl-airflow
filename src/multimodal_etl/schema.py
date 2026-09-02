"""Schema of the multimodal publication.

This module is the **single source of truth** of the dataset: it describes every field
(name, type, role in the AI use case) and provides the :class:`Publication` structure the
transform step returns. The conceptual schema and the documentation are both generated
from :data:`FIELDS`, which is what keeps diagram, code and data aligned.

Every field belongs to a **conceptual entity** (:data:`ENTITIES`): that is the piece of
information that lets us draw the conceptual model and split the load into tables joined
by keys.
"""

from __future__ import annotations

import hashlib
from dataclasses import asdict, dataclass
from typing import NamedTuple


class FieldSpec(NamedTuple):
    """Description of one schema field, used to generate the documentation."""

    name: str
    dtype: str
    role: str  # role in the use case: NLP, VISION, TARGET, METADATA, KEY
    entity: str  # conceptual entity it belongs to (see ENTITIES)
    required: bool
    description: str


# Entities of the conceptual model, in the reading order of the diagram.
ENTITIES: tuple[str, ...] = (
    "PUBLICATION",
    "SOURCE",
    "TEXT_CONTENT",
    "IMAGE_CONTENT",
    "LABEL",
)

# Business description of every field. It doubles as documentation, as the basis of the
# conceptual diagram, and as the plan for splitting the tables (see load.py).
FIELDS: tuple[FieldSpec, ...] = (
    FieldSpec(
        "id",
        "string",
        "KEY",
        "PUBLICATION",
        True,
        "Unique identifier of the publication (SHA-1 hash of the URL and the title).",
    ),
    FieldSpec(
        "source_id",
        "string",
        "KEY",
        "PUBLICATION",
        True,
        "Join key towards the SOURCE entity (hash of the source name).",
    ),
    FieldSpec(
        "source",
        "string",
        "METADATA",
        "SOURCE",
        True,
        "Precise source of the publication (e.g. rss:bbc_news, newsdata, fakenewsnet:politifact).",
    ),
    FieldSpec(
        "source_type",
        "string",
        "METADATA",
        "SOURCE",
        True,
        "Source family: 'rss', 'api' or 'dataset'.",
    ),
    FieldSpec(
        "access_method",
        "string",
        "METADATA",
        "SOURCE",
        True,
        "How the data was reached: 'rss_feed', 'rest_api', 'github_download' or 'kaggle_download'.",
    ),
    FieldSpec(
        "domain",
        "string",
        "METADATA",
        "PUBLICATION",
        True,
        "Domain name of the article's publisher (a reliability signal).",
    ),
    FieldSpec(
        "title",
        "string",
        "NLP",
        "TEXT_CONTENT",
        True,
        "Title of the publication — the main textual signal for the NLP model.",
    ),
    FieldSpec(
        "text",
        "string",
        "NLP",
        "TEXT_CONTENT",
        True,
        "Cleaned body or summary — the text input for classification.",
    ),
    FieldSpec(
        "text_length",
        "integer",
        "METADATA",
        "TEXT_CONTENT",
        True,
        "Length of the cleaned text, in characters — a feature and a quality check.",
    ),
    FieldSpec(
        "image_url",
        "string",
        "VISION",
        "IMAGE_CONTENT",
        True,
        "Original URL of the main image.",
    ),
    FieldSpec(
        "image_path",
        "string",
        "VISION",
        "IMAGE_CONTENT",
        True,
        "Path of the image file downloaded to disk — the real input of the vision model.",
    ),
    FieldSpec(
        "image_source",
        "string",
        "METADATA",
        "IMAGE_CONTENT",
        True,
        "Where the image came from: 'native' (supplied by the source) or 'open_graph' "
        "(metadata of the article).",
    ),
    FieldSpec(
        "has_image",
        "boolean",
        "VISION",
        "IMAGE_CONTENT",
        True,
        "True when the image file is on disk — this is what guarantees the text-image link.",
    ),
    FieldSpec(
        "url",
        "string",
        "METADATA",
        "PUBLICATION",
        True,
        "URL of the original article (traceability, deduplication).",
    ),
    FieldSpec(
        "language",
        "string",
        "METADATA",
        "PUBLICATION",
        True,
        "Detected or declared language (ISO 639-1 code, e.g. 'en').",
    ),
    FieldSpec(
        "published_at",
        "datetime",
        "METADATA",
        "PUBLICATION",
        False,
        "Publication date (ISO 8601) — useful for freshness and time-based features.",
    ),
    FieldSpec(
        "ingested_at",
        "datetime",
        "METADATA",
        "PUBLICATION",
        True,
        "Timestamp of the ingestion by the pipeline (traceability, monitoring).",
    ),
    FieldSpec(
        "label",
        "string",
        "TARGET",
        "LABEL",
        False,
        "Ground truth where it exists: 'real', 'fake' or 'unverified'.",
    ),
    FieldSpec(
        "label_source",
        "string",
        "METADATA",
        "LABEL",
        False,
        "Origin of the label (e.g. 'fakenewsnet:politifact'), or null when unlabelled.",
    ),
)

# Ordered list of the final dataset's columns.
COLUMNS: tuple[str, ...] = tuple(spec.name for spec in FIELDS)


def fields_of(entity: str) -> tuple[FieldSpec, ...]:
    """Return the fields attached to a given conceptual entity."""
    return tuple(spec for spec in FIELDS if spec.entity == entity)


# The hashes below only exist to build short, stable identifiers: they protect nothing,
# hence `usedforsecurity=False`.
def generate_id(url: str, title: str) -> str:
    """Build the stable identifier of a publication from its URL and its title."""
    seed = f"{url}|{title}".encode()
    return hashlib.sha1(seed, usedforsecurity=False).hexdigest()[:16]


def generate_source_id(source: str) -> str:
    """Build the join key of a source from its name."""
    return hashlib.sha1(source.encode(), usedforsecurity=False).hexdigest()[:12]


@dataclass(slots=True)
class Publication:
    """One normalised multimodal publication, ready for AI training."""

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
        """Turn the publication into a dictionary — one row of the dataset."""
        row = asdict(self)
        # Reorder along COLUMNS, for a stable and readable export.
        return {col: row[col] for col in COLUMNS}
