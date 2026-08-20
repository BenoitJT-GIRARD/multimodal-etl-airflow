"""Tests unitaires du schéma de données."""

from __future__ import annotations

from multimodal_etl.schema import COLUMNS, ENTITES, FIELDS, Publication, champs_de


def _publication_exemple() -> Publication:
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


def test_colonnes_alignees_sur_les_champs() -> None:
    assert tuple(spec.name for spec in FIELDS) == COLUMNS


def test_chaque_champ_a_un_role_connu() -> None:
    roles_attendus = {"KEY", "NLP", "VISION", "TARGET", "METADATA"}
    for spec in FIELDS:
        assert spec.role in roles_attendus


def test_chaque_champ_appartient_a_une_entite_declaree() -> None:
    for spec in FIELDS:
        assert spec.entite in ENTITES


def test_chaque_entite_porte_au_moins_un_champ() -> None:
    # Sans cela, le diagramme conceptuel afficherait une entité vide.
    for entite in ENTITES:
        assert champs_de(entite), f"entité sans champ : {entite}"


def test_schema_couvre_les_modalites_essentielles() -> None:
    roles = {spec.role for spec in FIELDS}
    # Le cas d'usage multimodal exige a minima du texte (NLP) et de l'image (VISION).
    assert "NLP" in roles
    assert "VISION" in roles
    assert "TARGET" in roles  # label de vérité terrain


def test_le_lien_texte_image_est_materialise() -> None:
    noms = {spec.name for spec in FIELDS}
    # Le chemin du fichier image est ce qui prouve que texte et image sont associés.
    assert {"image_path", "has_image"} <= noms


def test_publication_to_row_respecte_l_ordre_des_colonnes() -> None:
    row = _publication_exemple().to_row()
    assert tuple(row.keys()) == COLUMNS
