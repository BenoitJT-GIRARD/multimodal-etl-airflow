"""Unit tests of the database load."""

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


def _dataset(ids: tuple[str, ...]) -> pd.DataFrame:
    """Build a minimal dataset that conforms to the schema."""
    rows = []
    for index, identifier in enumerate(ids):
        rows.append(
            {
                "id": identifier,
                "source_id": "src_rss" if index % 2 == 0 else "src_api",
                "source": "rss:bbc" if index % 2 == 0 else "newsdata",
                "source_type": "rss" if index % 2 == 0 else "api",
                "access_method": "flux_rss" if index % 2 == 0 else "api_rest",
                "domain": "bbc.co.uk",
                "title": f"Title {index}",
                "text": f"Text {index}",
                "text_length": 8,
                "image_url": "https://site.com/i.jpg",
                "image_path": f"data/raw/images/{identifier}.jpg",
                "image_source": "native",
                "has_image": True,
                "url": f"https://site.com/{identifier}",
                "language": "en",
                "published_at": "2026-06-29T10:00:00+00:00",
                "ingested_at": "2026-06-29T11:00:00+00:00",
                "label": "fake" if index == 0 else None,
                "label_source": "fakenewsnet:politifact" if index == 0 else None,
            }
        )
    return pd.DataFrame(rows, columns=list(COLUMNS))


def _config(tmp_path: Path) -> LoadConfig:
    return LoadConfig(db_url=f"sqlite:///{(tmp_path / 'test.db').as_posix()}")


def test_split_into_tables_distributes_every_field() -> None:
    tables = split_into_tables(_dataset(("a", "b")))

    assert set(tables) == {"source", "publication", "contenu_texte", "contenu_image", "label"}
    assert list(tables["contenu_texte"].columns) == ["id", "title", "text", "text_length"]
    assert "source_id" in tables["publication"].columns  # the join key is there


def test_split_into_tables_deduplicates_the_sources() -> None:
    tables = split_into_tables(_dataset(("a", "b", "c", "d")))
    # Four publications, but only two distinct sources.
    assert len(tables["source"]) == 2


def test_split_into_tables_keeps_only_labelled_publications() -> None:
    tables = split_into_tables(_dataset(("a", "b", "c")))
    assert list(tables["label"]["id"]) == ["a"]


def test_write_to_database_creates_every_table(tmp_path: Path) -> None:
    config = _config(tmp_path)
    write_to_database(_dataset(("a", "b")), config)

    engine = create_engine(config.resolved_url)
    with engine.connect() as connection:
        publications = connection.execute(text("SELECT COUNT(*) FROM publications")).scalar()
        sources = connection.execute(text("SELECT COUNT(*) FROM source")).scalar()
    engine.dispose()

    assert publications == 2
    assert sources == 2


def test_loading_is_incremental(tmp_path: Path) -> None:
    config = _config(tmp_path)

    first = write_to_database(_dataset(("a", "b")), config)
    second = write_to_database(_dataset(("b", "c")), config)

    assert first["publications"] == 2
    # Only publication "c" is new; "b" is already in the database.
    assert second["publications"] == 1
    assert second["deja_presentes"] == 1
    assert count_publications(config) == 3


def test_replaying_the_same_load_adds_nothing(tmp_path: Path) -> None:
    config = _config(tmp_path)
    write_to_database(_dataset(("a", "b")), config)
    replay = write_to_database(_dataset(("a", "b")), config)

    assert replay["publications"] == 0
    assert count_publications(config) == 2


def test_the_join_keys_connect_the_tables(tmp_path: Path) -> None:
    config = _config(tmp_path)
    write_to_database(_dataset(("a", "b")), config)

    engine = create_engine(config.resolved_url)
    with engine.connect() as connection:
        rows = connection.execute(
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

    assert len(rows) == 2
    assert rows[0][1] == "rss:bbc"


def test_read_dataset_handles_parquet_and_csv(tmp_path: Path) -> None:
    df = _dataset(("a",))
    csv_path = tmp_path / "d.csv"
    df.to_csv(csv_path, index=False)
    assert len(read_dataset(csv_path)) == 1

    parquet_path = tmp_path / "d.parquet"
    df.to_parquet(parquet_path, index=False)
    assert len(read_dataset(parquet_path)) == 1
