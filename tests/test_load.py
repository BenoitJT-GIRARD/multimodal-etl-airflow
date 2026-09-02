"""Tests unitaires du chargement en base."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
from sqlalchemy import create_engine, text

from multimodal_etl.config import LoadConfig
from multimodal_etl.load import (
    count_publications,
    read_dataset,
    split_into_tables,
    write_to_database,
)
from multimodal_etl.schema import COLUMNS


def _dataset(identifiants: tuple[str, ...]) -> pd.DataFrame:
    """Construit un dataset minimal conforme au schéma."""
    lignes = []
    for index, identifiant in enumerate(identifiants):
        lignes.append(
            {
                "id": identifiant,
                "source_id": "src_rss" if index % 2 == 0 else "src_api",
                "source": "rss:bbc" if index % 2 == 0 else "newsdata",
                "source_type": "rss" if index % 2 == 0 else "api",
                "access_method": "flux_rss" if index % 2 == 0 else "api_rest",
                "domain": "bbc.co.uk",
                "title": f"Titre {index}",
                "text": f"Texte {index}",
                "text_length": 8,
                "image_url": "https://site.com/i.jpg",
                "image_path": f"data/raw/images/{identifiant}.jpg",
                "image_source": "native",
                "has_image": True,
                "url": f"https://site.com/{identifiant}",
                "language": "en",
                "published_at": "2026-06-29T10:00:00+00:00",
                "ingested_at": "2026-06-29T11:00:00+00:00",
                "label": "fake" if index == 0 else None,
                "label_source": "fakenewsnet:politifact" if index == 0 else None,
            }
        )
    return pd.DataFrame(lignes, columns=list(COLUMNS))


def _config(tmp_path: Path) -> LoadConfig:
    return LoadConfig(db_url=f"sqlite:///{(tmp_path / 'test.db').as_posix()}")


def test_split_into_tables_distributes_every_field() -> None:
    tables = split_into_tables(_dataset(("a", "b")))

    assert set(tables) == {"source", "publication", "contenu_texte", "contenu_image", "label"}
    assert list(tables["contenu_texte"].columns) == ["id", "title", "text", "text_length"]
    assert "source_id" in tables["publication"].columns  # la clé de jointure est présente


def test_split_into_tables_deduplicates_the_sources() -> None:
    tables = split_into_tables(_dataset(("a", "b", "c", "d")))
    # Quatre publications, mais seulement deux sources distinctes.
    assert len(tables["source"]) == 2


def test_split_into_tables_keeps_only_labelled_publications() -> None:
    tables = split_into_tables(_dataset(("a", "b", "c")))
    assert list(tables["label"]["id"]) == ["a"]


def test_write_to_database_creates_every_table(tmp_path: Path) -> None:
    config = _config(tmp_path)
    write_to_database(_dataset(("a", "b")), config)

    engine = create_engine(config.resolved_url)
    with engine.connect() as connexion:
        publications = connexion.execute(text("SELECT COUNT(*) FROM publications")).scalar()
        sources = connexion.execute(text("SELECT COUNT(*) FROM source")).scalar()
    engine.dispose()

    assert publications == 2
    assert sources == 2


def test_loading_is_incremental(tmp_path: Path) -> None:
    config = _config(tmp_path)

    premier = write_to_database(_dataset(("a", "b")), config)
    second = write_to_database(_dataset(("b", "c")), config)

    assert premier["publications"] == 2
    # Seule la publication « c » est nouvelle ; « b » est déjà en base.
    assert second["publications"] == 1
    assert second["deja_presentes"] == 1
    assert count_publications(config) == 3


def test_replaying_the_same_load_adds_nothing(tmp_path: Path) -> None:
    config = _config(tmp_path)
    write_to_database(_dataset(("a", "b")), config)
    rejeu = write_to_database(_dataset(("a", "b")), config)

    assert rejeu["publications"] == 0
    assert count_publications(config) == 2


def test_the_join_keys_connect_the_tables(tmp_path: Path) -> None:
    config = _config(tmp_path)
    write_to_database(_dataset(("a", "b")), config)

    engine = create_engine(config.resolved_url)
    with engine.connect() as connexion:
        lignes = connexion.execute(
            text(
                "SELECT p.id, s.source, t.title, i.image_path "
                "FROM publication p "
                "JOIN source s ON s.source_id = p.source_id "
                "JOIN contenu_texte t ON t.id = p.id "
                "JOIN contenu_image i ON i.id = p.id "
                "ORDER BY p.id"
            )
        ).fetchall()
    engine.dispose()

    assert len(lignes) == 2
    assert lignes[0][1] == "rss:bbc"


def test_read_dataset_handles_parquet_and_csv(tmp_path: Path) -> None:
    df = _dataset(("a",))
    chemin_csv = tmp_path / "d.csv"
    df.to_csv(chemin_csv, index=False)
    assert len(read_dataset(chemin_csv)) == 1

    chemin_parquet = tmp_path / "d.parquet"
    df.to_parquet(chemin_parquet, index=False)
    assert len(read_dataset(chemin_parquet)) == 1
