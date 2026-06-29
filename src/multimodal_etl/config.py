"""Configuration centralisee du pipeline.

Tous les chemins et les parametres ajustables sont regroupes ici sous forme de
dataclasses ``frozen`` (immuables). Les scripts, notebooks et le DAG Airflow
importent ces objets plutot que de coder en dur des constantes : c'est ce qui
rend le pipeline **reproductible** et **parametrable** (cf. fiche d'autoevaluation).
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

# Racine du projet = deux niveaux au-dessus de ce fichier (src/multimodal_etl/config.py).
PROJECT_ROOT: Path = Path(__file__).resolve().parents[2]

DATA_DIR: Path = PROJECT_ROOT / "data"
RAW_DIR: Path = DATA_DIR / "raw"
PROCESSED_DIR: Path = DATA_DIR / "processed"
SAMPLES_DIR: Path = DATA_DIR / "samples"
DB_DIR: Path = DATA_DIR / "db"
LOGS_DIR: Path = PROJECT_ROOT / "logs"


def _env_int(name: str, default: int) -> int:
    """Lit une variable d'environnement entiere, avec valeur de repli."""
    raw = os.environ.get(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        return int(raw)
    except ValueError:
        return default


@dataclass(frozen=True)
class ExtractionConfig:
    """Parametres de l'etape d'extraction (E)."""

    # Nombre maximum d'elements collectes par source (garde-fou contre les quotas API).
    max_items_per_source: int = field(
        default_factory=lambda: _env_int("MULTIMODAL_ETL_MAX_ITEMS_PER_SOURCE", 50)
    )
    # Delai d'attente (secondes) pour chaque requete reseau.
    request_timeout: int = field(default_factory=lambda: _env_int("MULTIMODAL_ETL_REQUEST_TIMEOUT", 15))
    # En-tete User-Agent : politesse minimale vis-a-vis des serveurs interroges.
    user_agent: str = "Multimodal ETL-bot/0.1 (+https://github.com/multimodal_etl)"
    # Flux RSS multimodaux (titre + resume + image) — sources officielles, sans cle.
    rss_feeds: tuple[tuple[str, str], ...] = (
        ("the_guardian", "https://www.theguardian.com/world/rss"),
        ("bbc_news", "https://feeds.bbci.co.uk/news/world/rss.xml"),
        ("abc_news", "https://abcnews.go.com/abcnews/internationalheadlines"),
    )
    # Parametres de l'API NewsData.io (source activee si une cle est fournie).
    newsdata_endpoint: str = "https://newsdata.io/api/1/news"
    newsdata_language: str = "en"


@dataclass(frozen=True)
class TransformConfig:
    """Parametres de l'etape de transformation (T)."""

    # Longueur minimale de texte (caracteres) pour qu'une publication soit jugee exploitable.
    min_text_length: int = 30
    # Extensions d'image considerees comme valides.
    valid_image_extensions: tuple[str, ...] = (".jpg", ".jpeg", ".png", ".webp", ".gif")
    # Si True, une publication sans image valide est ecartee (cas d'usage multimodal strict).
    require_image: bool = True
    # Format d'export du dataset transforme.
    output_format: str = "parquet"  # "parquet" ou "csv"


@dataclass(frozen=True)
class LoadConfig:
    """Parametres de l'etape de chargement (L)."""

    # URL SQLAlchemy de la base cible. Vide -> SQLite local (data/db/multimodal_etl.db).
    db_url: str = field(default_factory=lambda: os.environ.get("MULTIMODAL_ETL_DB_URL", "").strip())
    table_name: str = "publications"

    @property
    def resolved_url(self) -> str:
        """Renvoie l'URL de connexion effective (SQLite local par defaut)."""
        if self.db_url:
            return self.db_url
        return f"sqlite:///{(DB_DIR / 'multimodal_etl.db').as_posix()}"


def ensure_dirs() -> None:
    """Cree les repertoires de travail s'ils n'existent pas encore."""
    for directory in (RAW_DIR, PROCESSED_DIR, SAMPLES_DIR, DB_DIR, LOGS_DIR):
        directory.mkdir(parents=True, exist_ok=True)
