"""Tests unitaires du chargement en base."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
from sqlalchemy import create_engine, text

from multimodal_etl.config import LoadConfig
from multimodal_etl.load import (
    charge_en_base,
    compte_publications,
    decoupe_en_tables,
    lit_dataset,
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


def test_decoupe_en_tables_repartit_tous_les_champs() -> None:
    tables = decoupe_en_tables(_dataset(("a", "b")))

    assert set(tables) == {"source", "publication", "contenu_texte", "contenu_image", "label"}
    assert list(tables["contenu_texte"].columns) == ["id", "title", "text", "text_length"]
    assert "source_id" in tables["publication"].columns  # la clé de jointure est présente


def test_decoupe_en_tables_deduplique_les_sources() -> None:
    tables = decoupe_en_tables(_dataset(("a", "b", "c", "d")))
    # Quatre publications, mais seulement deux sources distinctes.
    assert len(tables["source"]) == 2


def test_decoupe_en_tables_ne_garde_que_les_publications_annotees() -> None:
    tables = decoupe_en_tables(_dataset(("a", "b", "c")))
    assert list(tables["label"]["id"]) == ["a"]


def test_charge_en_base_cree_toutes_les_tables(tmp_path: Path) -> None:
    config = _config(tmp_path)
    charge_en_base(_dataset(("a", "b")), config)

    engine = create_engine(config.resolved_url)
    with engine.connect() as connexion:
        publications = connexion.execute(text("SELECT COUNT(*) FROM publications")).scalar()
        sources = connexion.execute(text("SELECT COUNT(*) FROM source")).scalar()
    engine.dispose()

    assert publications == 2
    assert sources == 2


def test_le_chargement_est_incremental(tmp_path: Path) -> None:
    config = _config(tmp_path)

    premier = charge_en_base(_dataset(("a", "b")), config)
    second = charge_en_base(_dataset(("b", "c")), config)

    assert premier["publications"] == 2
    # Seule la publication « c » est nouvelle ; « b » est déjà en base.
    assert second["publications"] == 1
    assert second["deja_presentes"] == 1
    assert compte_publications(config) == 3


def test_relancer_le_meme_chargement_n_ajoute_rien(tmp_path: Path) -> None:
    config = _config(tmp_path)
    charge_en_base(_dataset(("a", "b")), config)
    rejeu = charge_en_base(_dataset(("a", "b")), config)

    assert rejeu["publications"] == 0
    assert compte_publications(config) == 2


def test_les_cles_de_jointure_relient_les_tables(tmp_path: Path) -> None:
    config = _config(tmp_path)
    charge_en_base(_dataset(("a", "b")), config)

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


def test_lit_dataset_gere_parquet_et_csv(tmp_path: Path) -> None:
    df = _dataset(("a",))
    chemin_csv = tmp_path / "d.csv"
    df.to_csv(chemin_csv, index=False)
    assert len(lit_dataset(chemin_csv)) == 1

    chemin_parquet = tmp_path / "d.parquet"
    df.to_parquet(chemin_parquet, index=False)
    assert len(lit_dataset(chemin_parquet)) == 1
