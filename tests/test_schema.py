"""Unit tests of the data schema."""

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
        title="Title",
        text="Text",
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
    known_roles = {"KEY", "NLP", "VISION", "TARGET", "METADATA"}
    for spec in FIELDS:
        assert spec.role in known_roles


def test_every_field_belongs_to_a_declared_entity() -> None:
    for spec in FIELDS:
        assert spec.entity in ENTITIES


def test_every_entity_carries_at_least_one_field() -> None:
    # Without this, the conceptual diagram would show an empty entity.
    for entity in ENTITIES:
        assert fields_of(entity), f"entity with no field: {entity}"


def test_the_schema_covers_the_essential_modalities() -> None:
    roles = {spec.role for spec in FIELDS}
    # The multimodal use case demands at least text (NLP) and image (VISION).
    assert "NLP" in roles
    assert "VISION" in roles
    assert "TARGET" in roles  # the ground-truth label


def test_the_text_image_link_is_materialised() -> None:
    names = {spec.name for spec in FIELDS}
    # The image file path is what proves text and image are paired.
    assert {"image_path", "has_image"} <= names


def test_publication_to_row_respects_the_column_order() -> None:
    row = _sample_publication().to_row()
    assert tuple(row.keys()) == COLUMNS
