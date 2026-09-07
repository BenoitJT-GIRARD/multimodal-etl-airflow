"""Step L — load (storing into a database that fits the data).

The transformed dataset is loaded into a **relational** database through SQLAlchemy. By
default we target a local **SQLite** (``data/db/multimodal_etl.db``): light, serverless,
ideal for a reproducible demonstration. In production, setting ``MULTIMODAL_ETL_DB_URL``
is enough to point at a managed **PostgreSQL** — authentication, roles and encryption
handled server-side (see the monitoring plan).

Choosing relational is consistent with the data: it is tabular, of fixed schema, and meant
for analytical queries (filter by source, by label, by presence of an image).

Two complementary writes happen on every run:

* an **exploded model**, one table per entity of the conceptual schema, joined by the
  ``id`` (publication) and ``source_id`` (source) keys — this is the model that prepares
  the joins and avoids repeating the source metadata on every row;
* a **flat table** ``publications``, denormalised, directly consumable for model training
  and by the dashboard.

The load is **incremental**: each run only adds the publications the database does not
already hold. The dataset therefore grows over the daily runs, without ever creating a
duplicate.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import Engine

from multimodal_etl.config import LoadConfig, ensure_dirs
from multimodal_etl.logging_setup import get_logger
from multimodal_etl.schema import ENTITIES, fields_of

logger = get_logger(__name__)

# SQL table name matching each entity of the conceptual model.
TABLES: dict[str, str] = {
    "SOURCE": "source",
    "PUBLICATION": "publication",
    "TEXT_CONTENT": "text_content",
    "IMAGE_CONTENT": "image_content",
    "LABEL": "label",
}

# Primary key of each table: the source has its own, everything else is identified by the
# publication.
PRIMARY_KEYS: dict[str, str] = {"source": "source_id", "publication": "id"}


def primary_key(table: str) -> str:
    """Return the name of a table's primary key."""
    return PRIMARY_KEYS.get(table, "id")


def check_table(table: str, config: LoadConfig) -> None:
    """Reject any table name that does not come from the project's schema.

    The queries below build their table name by interpolation. This check guarantees that
    the name always comes from :data:`TABLES` (or from the configuration) and never from
    outside input: that is what rules out any SQL injection.
    """
    allowed = set(TABLES.values()) | {config.table_name}
    if table not in allowed:
        raise ValueError(f"unknown table: {table}")


def read_dataset(path: Path) -> pd.DataFrame:
    """Load the transformed dataset (Parquet or CSV) into a DataFrame."""
    if path.suffix == ".parquet":
        return pd.read_parquet(path)
    return pd.read_csv(path)


def split_into_tables(df: pd.DataFrame) -> dict[str, pd.DataFrame]:
    """Explode the flat dataset into one table per entity of the conceptual schema.

    Each table gets its primary key, then the fields the schema attaches to its entity.
    The ``source`` table is deduplicated: one row per source, not one per publication.
    """
    tables: dict[str, pd.DataFrame] = {}

    for entity in ENTITIES:
        table = TABLES[entity]
        key = primary_key(table)
        columns = [key] + [spec.name for spec in fields_of(entity) if spec.name != key]

        chunk = df[columns].copy()
        if table == "source":
            chunk = chunk.drop_duplicates(subset="source_id").reset_index(drop=True)
        if table == "label":
            # Only the publications that really carry an annotation enter this table.
            chunk = chunk[chunk["label"].notna()].reset_index(drop=True)

        tables[table] = chunk

    return tables


def read_existing_keys(engine: Engine, table: str, config: LoadConfig) -> set[str]:
    """Return the primary keys already in a table (empty when the table is absent)."""
    check_table(table, config)
    if not inspect(engine).has_table(table):
        return set()
    key = primary_key(table)
    with engine.connect() as connection:
        query = text(f"SELECT {key} FROM {table}")  # nosec B608 - names validated above
        return {row[0] for row in connection.execute(query)}


def insert_new_rows(engine: Engine, table: str, chunk: pd.DataFrame, config: LoadConfig) -> int:
    """Add to a table only the rows whose key is not known yet."""
    if chunk.empty:
        return 0

    key = primary_key(table)
    already_known = read_existing_keys(engine, table, config)
    new_rows = chunk[~chunk[key].isin(already_known)]
    if new_rows.empty:
        logger.info("Load: table '%s' already up to date", table)
        return 0

    new_rows.to_sql(table, engine, if_exists="append", index=False)
    logger.info("Load: %d rows added to '%s'", len(new_rows), table)
    return len(new_rows)


def write_to_database(df: pd.DataFrame, config: LoadConfig | None = None) -> dict[str, int]:
    """Load the dataset into the database and return the rows added per table."""
    config = config or LoadConfig()
    ensure_dirs()

    url = config.resolved_url
    logger.info("Load: connecting to the database (%s)", url.split("@")[-1])
    engine = create_engine(url)

    per_table: dict[str, int] = {}
    try:
        # 1. Exploded model: one table per entity, joined by their keys.
        for table, chunk in split_into_tables(df).items():
            per_table[table] = insert_new_rows(engine, table, chunk, config)

        # 2. Flat table, ready for training and for the dashboard.
        per_table[config.table_name] = insert_new_rows(engine, config.table_name, df, config)
    finally:
        engine.dispose()

    per_table["already_present"] = len(df) - per_table.get(config.table_name, 0)
    logger.info(
        "Load: %d new publications, %d already present",
        per_table.get(config.table_name, 0),
        per_table["already_present"],
    )
    return per_table


def count_publications(config: LoadConfig | None = None) -> int:
    """Return the total number of publications accumulated in the database."""
    config = config or LoadConfig()
    check_table(config.table_name, config)
    engine = create_engine(config.resolved_url)
    try:
        if not inspect(engine).has_table(config.table_name):
            return 0
        with engine.connect() as connection:
            query = text(f"SELECT COUNT(*) FROM {config.table_name}")  # nosec B608
            return int(connection.execute(query).scalar() or 0)
    finally:
        engine.dispose()


def load_dataset(dataset_path: Path, config: LoadConfig | None = None) -> dict[str, int]:
    """The whole load pipeline: read the dataset, then write it to the database."""
    df = read_dataset(dataset_path)
    return write_to_database(df, config)
