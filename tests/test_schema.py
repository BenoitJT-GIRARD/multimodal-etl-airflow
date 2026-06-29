"""Tests unitaires du schema de donnees."""

from __future__ import annotations

from multimodal_etl.schema import COLUMNS, FIELDS, Publication


def test_colonnes_alignees_sur_les_champs() -> None:
    assert tuple(spec.name for spec in FIELDS) == COLUMNS


def test_chaque_champ_a_un_role_connu() -> None:
    roles_attendus = {"KEY", "NLP", "VISION", "TARGET", "METADATA"}
    for spec in FIELDS:
        assert spec.role in roles_attendus


def test_schema_couvre_les_modalites_essentielles() -> None:
    roles = {spec.role for spec in FIELDS}
    # Le cas d'usage multimodal exige a minima du texte (NLP) et de l'image (VISION).
    assert "NLP" in roles
    assert "VISION" in roles
    assert "TARGET" in roles  # label de verite terrain


def test_publication_to_row_respecte_l_ordre_des_colonnes() -> None:
    pub = Publication(
        id="abc",
        source="rss:test",
        source_type="rss",
        title="Titre",
        text="Texte",
        url="https://a.com",
        image_url="https://a.com/i.jpg",
        language="en",
        domain="a.com",
        has_image=True,
        text_length=5,
        ingested_at="2026-06-29T10:00:00+00:00",
    )
    row = pub.to_row()
    assert tuple(row.keys()) == COLUMNS
