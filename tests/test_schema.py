"""Tests unitaires du schéma de données."""

from __future__ import annotations

from multimodal_etl.schema import COLUMNS, ENTITIES, FIELDS, Publication, fields_of


def _sample_publication() -> Publication:
    return Publication(
        id="abc",
        source_id="src",
        source="rss:test",
        source_type="rss",
        access_method="flux_rss",
        domain="a.com",
        title="Titre",
        text="Texte",
        text_length=5,
        image_url="https://a.com/i.jpg",
        image_path="data/raw/images/i.jpg",
        image_source="native",
        has_image=True,
        url="https://a.com",
        language="en",
        ingested_at="2026-06-29T10:00:00+00:00",
    )


def test_columns_match_the_schema_fields() -> None:
    assert tuple(spec.name for spec in FIELDS) == COLUMNS


def test_every_field_has_a_known_role() -> None:
    roles_attendus = {"KEY", "NLP", "VISION", "TARGET", "METADATA"}
    for spec in FIELDS:
        assert spec.role in roles_attendus


def test_every_field_belongs_to_a_declared_entity() -> None:
    for spec in FIELDS:
        assert spec.entity in ENTITIES


def test_every_entity_carries_at_least_one_field() -> None:
    # Sans cela, le diagramme conceptuel afficherait une entité clear.
    for entity in ENTITIES:
        assert fields_of(entity), f"entité sans champ : {entity}"


def test_the_schema_covers_the_essential_modalities() -> None:
    roles = {spec.role for spec in FIELDS}
    # Le cas d'usage multimodal exige a minima du texte (NLP) et de l'image (VISION).
    assert "NLP" in roles
    assert "VISION" in roles
    assert "TARGET" in roles  # label de vérité terrain


def test_the_text_image_link_is_materialised() -> None:
    noms = {spec.name for spec in FIELDS}
    # Le chemin du fichier image est ce qui prouve que texte et image sont associés.
    assert {"image_path", "has_image"} <= noms


def test_publication_to_row_respects_the_column_order() -> None:
    row = _sample_publication().to_row()
    assert tuple(row.keys()) == COLUMNS
