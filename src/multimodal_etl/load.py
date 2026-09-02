"""Étape L — chargement (stockage dans une base adaptée).

Le dataset transformé est chargé dans une base **relationnelle** via SQLAlchemy.
Par défaut on cible un **SQLite** local (``data/db/multimodal_etl.db``) : léger, sans
serveur, parfait pour une démonstration reproductible. En production, il suffit de
renseigner ``MULTIMODAL_ETL_DB_URL`` pour pointer vers un **PostgreSQL** managé
(authentification, rôles et chiffrage gérés côté serveur — cf. plan de monitoring).

Le choix du relationnel est cohérent avec la donnée : elle est tabulaire, de schéma
fixe, et destinée à des requêtes analytiques (filtrer par source, par label, par
présence d'image).

Deux écritures complémentaires sont réalisées à chaque exécution :

* un **modèle éclaté**, une table par entité du schéma conceptuel, reliées par les
  clés ``id`` (publication) et ``source_id`` (source) — c'est ce modèle qui prépare
  les jointures et évite de répéter les métadonnées de source sur chaque ligne ;
* une **table à plat** ``publications``, dénormalisée, directement consommable pour
  l'entraînement du modèle et par le tableau de bord.

Le chargement est **incrémental** : chaque exécution n'ajoute que les publications
absentes de la base. Le jeu de données s'enrichit donc au fil des exécutions
quotidiennes, sans jamais créer de doublon.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import Engine

from multimodal_etl.config import LoadConfig, ensure_dirs
from multimodal_etl.logging_setup import get_logger
from multimodal_etl.schema import ENTITES, fields_of

logger = get_logger(__name__)

# Nom de la table SQL associée à chaque entité du modèle conceptuel.
TABLES: dict[str, str] = {
    "SOURCE": "source",
    "PUBLICATION": "publication",
    "CONTENU_TEXTE": "contenu_texte",
    "CONTENU_IMAGE": "contenu_image",
    "LABEL": "label",
}

# Clé primaire de chaque table : la source a la sienne, tout le reste est identifié
# par la publication.
CLES: dict[str, str] = {"source": "source_id", "publication": "id"}


def primary_key(table: str) -> str:
    """Renvoie le nom de la clé primaire d'une table."""
    return CLES.get(table, "id")


def check_table(table: str, config: LoadConfig) -> None:
    """Refuse tout nom de table qui ne vient pas du schéma du projet.

    Les requêtes ci-dessous composent leur nom de table par interpolation. Ce
    contrôle garantit que ce nom vient toujours de :data:`TABLES` (ou de la
    configuration) et jamais d'une saisie extérieure : c'est ce qui écarte tout
    risque d'injection SQL.
    """
    autorisees = set(TABLES.values()) | {config.table_name}
    if table not in autorisees:
        raise ValueError(f"table inconnue : {table}")


def read_dataset(path: Path) -> pd.DataFrame:
    """Charge le dataset transformé (Parquet ou CSV) en DataFrame."""
    if path.suffix == ".parquet":
        return pd.read_parquet(path)
    return pd.read_csv(path)


def split_into_tables(df: pd.DataFrame) -> dict[str, pd.DataFrame]:
    """Éclate le dataset à plat en une table par entité du schéma conceptuel.

    Chaque table reçoit sa clé primaire puis les champs que le schéma rattache à
    son entité. La table ``source`` est dédupliquée : une ligne par source, et non
    une par publication.
    """
    tables: dict[str, pd.DataFrame] = {}

    for entite in ENTITES:
        table = TABLES[entite]
        cle = primary_key(table)
        colonnes = [cle] + [spec.name for spec in fields_of(entite) if spec.name != cle]

        morceau = df[colonnes].copy()
        if table == "source":
            morceau = morceau.drop_duplicates(subset="source_id").reset_index(drop=True)
        if table == "label":
            # Seules les publications réellement annotées entrent dans cette table.
            morceau = morceau[morceau["label"].notna()].reset_index(drop=True)

        tables[table] = morceau

    return tables


def read_existing_keys(engine: Engine, table: str, config: LoadConfig) -> set[str]:
    """Renvoie les clés primaires déjà présentes dans une table (clear si absente)."""
    check_table(table, config)
    if not inspect(engine).has_table(table):
        return set()
    cle = primary_key(table)
    with engine.connect() as connexion:
        requete = text(f"SELECT {cle} FROM {table}")  # nosec B608 - noms validés ci-dessus
        return {ligne[0] for ligne in connexion.execute(requete)}


def insert_new_rows(engine: Engine, table: str, morceau: pd.DataFrame, config: LoadConfig) -> int:
    """Ajoute à une table les seules lignes dont la clé est encore inconnue."""
    if morceau.empty:
        return 0

    cle = primary_key(table)
    deja_connues = read_existing_keys(engine, table, config)
    nouveautes = morceau[~morceau[cle].isin(deja_connues)]
    if nouveautes.empty:
        logger.info("Chargement : table '%s' déjà à jour", table)
        return 0

    nouveautes.to_sql(table, engine, if_exists="append", index=False)
    logger.info("Chargement : %d lignes ajoutées dans '%s'", len(nouveautes), table)
    return len(nouveautes)


def write_to_database(df: pd.DataFrame, config: LoadConfig | None = None) -> dict[str, int]:
    """Charge le dataset dans la base et renvoie le nombre de lignes ajoutées par table."""
    config = config or LoadConfig()
    ensure_dirs()

    url = config.resolved_url
    logger.info("Chargement : connexion à la base (%s)", url.split("@")[-1])
    engine = create_engine(url)

    bilan: dict[str, int] = {}
    try:
        # 1. Modèle éclaté : une table par entité, reliées par leurs clés.
        for table, morceau in split_into_tables(df).items():
            bilan[table] = insert_new_rows(engine, table, morceau, config)

        # 2. Table à plat, prête pour l'entraînement et le tableau de bord.
        bilan[config.table_name] = insert_new_rows(engine, config.table_name, df, config)
    finally:
        engine.dispose()

    bilan["deja_presentes"] = len(df) - bilan.get(config.table_name, 0)
    logger.info(
        "Chargement : %d nouvelles publications, %d déjà présentes",
        bilan.get(config.table_name, 0),
        bilan["deja_presentes"],
    )
    return bilan


def count_publications(config: LoadConfig | None = None) -> int:
    """Renvoie le nombre total de publications accumulées en base."""
    config = config or LoadConfig()
    check_table(config.table_name, config)
    engine = create_engine(config.resolved_url)
    try:
        if not inspect(engine).has_table(config.table_name):
            return 0
        with engine.connect() as connexion:
            requete = text(f"SELECT COUNT(*) FROM {config.table_name}")  # nosec B608
            return int(connexion.execute(requete).scalar() or 0)
    finally:
        engine.dispose()


def load_dataset(dataset_path: Path, config: LoadConfig | None = None) -> dict[str, int]:
    """Pipeline de chargement complet : lecture du dataset puis écriture en base."""
    df = read_dataset(dataset_path)
    return write_to_database(df, config)
