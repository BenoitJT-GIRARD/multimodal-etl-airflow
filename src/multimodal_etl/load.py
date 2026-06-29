"""Etape L — chargement (stockage dans une base adaptee).

Le dataset transforme est charge dans une base relationnelle via SQLAlchemy. Par
defaut on cible un **SQLite** local (``data/db/multimodal_etl.db``) : leger, sans
serveur, parfait pour une demonstration locale et reproductible. En production,
il suffit de renseigner ``MULTIMODAL_ETL_DB_URL`` pour pointer vers un **PostgreSQL /
Supabase** (authentification, roles, chiffrage geres cote serveur — cf. plan de
monitoring).

Le choix d'une base **relationnelle** est pertinent ici : le dataset est tabulaire,
fortement structure (schema fixe) et destine a des requetes analytiques (filtrage
par source, label, presence d'image).
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
from sqlalchemy import create_engine

from multimodal_etl.config import LoadConfig, ensure_dirs
from multimodal_etl.logging_setup import get_logger

logger = get_logger(__name__)


def lit_dataset(path: Path) -> pd.DataFrame:
    """Charge le dataset transforme (Parquet ou CSV) en DataFrame."""
    if path.suffix == ".parquet":
        return pd.read_parquet(path)
    return pd.read_csv(path)


def charge_en_base(df: pd.DataFrame, config: LoadConfig | None = None) -> int:
    """Charge le DataFrame dans la table cible et renvoie le nombre de lignes ecrites.

    On utilise ``if_exists='replace'`` pour que le chargement soit idempotent :
    relancer le pipeline regenere une table propre et coherente.
    """
    config = config or LoadConfig()
    ensure_dirs()

    url = config.resolved_url
    logger.info("Chargement : connexion a la base (%s)", url.split("@")[-1])
    engine = create_engine(url)
    try:
        df.to_sql(config.table_name, engine, if_exists="replace", index=False)
    finally:
        engine.dispose()

    logger.info("Chargement : %d lignes ecrites dans la table '%s'", len(df), config.table_name)
    return len(df)


def run_load(dataset_path: Path, config: LoadConfig | None = None) -> int:
    """Pipeline de chargement complet : lecture du dataset puis ecriture en base."""
    df = lit_dataset(dataset_path)
    return charge_en_base(df, config)
