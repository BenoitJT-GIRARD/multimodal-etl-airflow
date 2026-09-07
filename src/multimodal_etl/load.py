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

**Idempotency is a property of the schema, not of this code.** Every table is declared with
its primary key and every insert ignores conflicts. Replaying a task — which the DAG
explicitly invites — cannot duplicate a row, and neither can two runs overlapping. An
earlier version read the existing keys and then wrote the rest, which was a race by
construction and loaded every key of the table into memory to boot.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
from sqlalchemy import (
    Boolean,
    Column,
    Integer,
    MetaData,
    String,
    Table,
    create_engine,
    func,
    inspect,
    select,
    text,
)
from sqlalchemy.engine import Engine

from multimodal_etl.config import LoadConfig, ensure_dirs
from multimodal_etl.logging_setup import get_logger
from multimodal_etl.schema import ENTITIES, FIELDS, fields_of

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

# The schema knows each field's logical type; the database needs a SQL one. Timestamps are
# carried as ISO strings by the dataset, so they stay strings here rather than being parsed
# twice.
_SQL_TYPES = {"string": String, "integer": Integer, "boolean": Boolean, "datetime": String}
_COLUMN_TYPES = {spec.name: _SQL_TYPES[spec.dtype] for spec in FIELDS}


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


def declare_tables(engine: Engine, frames: dict[str, pd.DataFrame]) -> MetaData:
    """Create every table with its primary key, and return the metadata describing them.

    Declaring the tables is what makes the load idempotent. Letting ``to_sql`` create them
    produces tables with no constraint at all, so nothing but the application code stops a
    duplicate.
    """
    metadata = MetaData()
    for table, chunk in frames.items():
        key = primary_key(table)
        Table(
            table,
            metadata,
            *[
                Column(name, _COLUMN_TYPES.get(name, String), primary_key=(name == key))
                for name in chunk.columns
            ],
        )
    metadata.create_all(engine)
    return metadata


def _insert_ignoring_conflicts(engine: Engine, table: Table):
    """Build the dialect's "insert, and skip what is already there" statement.

    ``on_conflict_do_nothing`` is not part of the generic SQLAlchemy insert: it belongs to
    the SQLite and PostgreSQL dialects, which are the two targets this project supports.
    """
    if engine.dialect.name == "postgresql":
        from sqlalchemy.dialects.postgresql import insert as dialect_insert
    else:
        from sqlalchemy.dialects.sqlite import insert as dialect_insert
    return dialect_insert(table).on_conflict_do_nothing()


def _as_python(value: object) -> object:
    """Turn a pandas/numpy scalar into something the database driver accepts."""
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    if value is pd.NaT:
        return None
    item = getattr(value, "item", None)
    return item() if callable(item) else value


def insert_new_rows(engine: Engine, table: Table, chunk: pd.DataFrame) -> int:
    """Insert the rows of a chunk, skipping the keys the table already holds.

    Returns how many rows were really written, measured rather than predicted: the count
    before and after. A prediction would be the read-then-write race all over again.
    """
    if chunk.empty:
        return 0

    records = [
        {name: _as_python(value) for name, value in row.items()} for row in chunk.to_dict("records")
    ]
    total = select(func.count()).select_from(table)

    with engine.begin() as connection:
        before = connection.execute(total).scalar_one()
        connection.execute(_insert_ignoring_conflicts(engine, table), records)
        after = connection.execute(total).scalar_one()

    written = after - before
    if written:
        logger.info("Load: %d rows added to '%s'", written, table.name)
    else:
        logger.info("Load: table '%s' already up to date", table.name)
    return written


def write_to_database(df: pd.DataFrame, config: LoadConfig | None = None) -> dict[str, int]:
    """Load the dataset into the database and return the rows added per table."""
    config = config or LoadConfig()
    ensure_dirs()

    url = config.resolved_url
    logger.info("Load: connecting to the database (%s)", url.split("@")[-1])
    engine = create_engine(url)

    frames = split_into_tables(df)
    frames[config.table_name] = df  # the flat table, ready for training and the dashboard

    per_table: dict[str, int] = {}
    try:
        metadata = declare_tables(engine, frames)
        for table, chunk in frames.items():
            per_table[table] = insert_new_rows(engine, metadata.tables[table], chunk)
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
