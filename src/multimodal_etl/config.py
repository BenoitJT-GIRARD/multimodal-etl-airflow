"""Configuration centralisée du pipeline.

Tous les chemins et les paramètres ajustables sont regroupés ici sous forme de
dataclasses ``frozen`` (immuables). Les scripts, notebooks et le DAG Airflow
importent ces objets plutôt que de coder en dur des constantes : c'est ce qui
rend le pipeline **reproductible** et **paramétrable** (cf. fiche d'autoévaluation).
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

# Racine du projet = deux niveaux au-dessus de ce fichier (src/multimodal_etl/config.py).
PROJECT_ROOT: Path = Path(__file__).resolve().parents[2]

DATA_DIR: Path = PROJECT_ROOT / "data"
RAW_DIR: Path = DATA_DIR / "raw"
IMAGES_DIR: Path = RAW_DIR / "images"
PROCESSED_DIR: Path = DATA_DIR / "processed"
# Une fiche par exécution du pipeline : c'est l'historique lu par le tableau de bord.
RUNS_DIR: Path = PROCESSED_DIR / "runs"
SAMPLES_DIR: Path = DATA_DIR / "samples"
DB_DIR: Path = DATA_DIR / "db"
LOGS_DIR: Path = PROJECT_ROOT / "logs"

# Zone de transit : fichiers d'échange entre deux tâches Airflow. Voir transit.py.
INTERIM_DIR: Path = DATA_DIR / "interim"


def chemin_relatif(chemin: Path) -> str:
    """Exprime un chemin par rapport à la racine du projet.

    Les chemins stockés dans le jeu de données doivent rester valables ailleurs
    que sur la machine qui les a produits : le pipeline tourne aussi bien en local
    que dans le conteneur Airflow, où la racine du projet n'est pas au même
    endroit. On enregistre donc ``data/raw/images/xxx.jpg`` et jamais un chemin
    absolu.
    """
    try:
        return chemin.resolve().relative_to(PROJECT_ROOT).as_posix()
    except ValueError:
        # Chemin hors du projet : on le garde tel quel plutôt que de le perdre.
        return chemin.as_posix()


def chemin_absolu(chemin: str) -> Path:
    """Retrouve le fichier réel à partir d'un chemin relatif au projet."""
    candidat = Path(chemin)
    return candidat if candidat.is_absolute() else PROJECT_ROOT / candidat


def _env_int(name: str, default: int) -> int:
    """Lit une variable d'environnement entière, avec valeur de repli."""
    raw = os.environ.get(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        return int(raw)
    except ValueError:
        return default


@dataclass(frozen=True)
class ExtractionConfig:
    """Paramètres de l'étape d'extraction (E)."""

    # Nombre maximum d'éléments collectés par source (garde-fou contre les quotas API).
    max_items_per_source: int = field(
        default_factory=lambda: _env_int("MULTIMODAL_ETL_MAX_ITEMS_PER_SOURCE", 50)
    )
    # Délai d'attente (secondes) pour chaque requête réseau.
    request_timeout: int = field(default_factory=lambda: _env_int("MULTIMODAL_ETL_REQUEST_TIMEOUT", 15))
    # En-tête User-Agent : politesse minimale vis-à-vis des serveurs interrogés.
    user_agent: str = "Multimodal ETL-bot/0.1 (+https://github.com/multimodal_etl)"
    # Flux RSS multimodaux (titre + résumé + image) — sources officielles, sans clé.
    rss_feeds: tuple[tuple[str, str], ...] = (
        ("the_guardian", "https://www.theguardian.com/world/rss"),
        ("bbc_news", "https://feeds.bbci.co.uk/news/world/rss.xml"),
        ("abc_news", "https://abcnews.go.com/abcnews/internationalheadlines"),
    )
    # Paramètres de l'API NewsData.io (source activée si une clé est fournie).
    newsdata_endpoint: str = "https://newsdata.io/api/1/news"
    newsdata_language: str = "en"
    # FakeNewsNet : CSV labellisés publiés sur le dépôt GitHub officiel.
    fakenewsnet_base_url: str = (
        "https://raw.githubusercontent.com/KaiDMML/FakeNewsNet/master/dataset"
    )
    fakenewsnet_files: tuple[str, ...] = (
        "politifact_fake.csv",
        "politifact_real.csv",
        "gossipcop_fake.csv",
        "gossipcop_real.csv",
    )
    # Ces CSV ne contiennent pas d'image : on va la chercher dans les métadonnées
    # Open Graph de l'article. L'opération coûte une requête HTTP par publication,
    # on la plafonne donc pour garder un run court.
    max_enrichissements_open_graph: int = field(
        default_factory=lambda: _env_int("MULTIMODAL_ETL_MAX_OPEN_GRAPH", 40)
    )


@dataclass(frozen=True)
class ImageConfig:
    """Paramètres du téléchargement des images (volet « vision » du multimodal)."""

    # Nombre maximum d'images téléchargées par exécution (maîtrise du temps et du disque).
    max_images: int = field(default_factory=lambda: _env_int("MULTIMODAL_ETL_MAX_IMAGES", 120))
    # Délai d'attente (secondes) d'un téléchargement d'image.
    request_timeout: int = field(default_factory=lambda: _env_int("MULTIMODAL_ETL_REQUEST_TIMEOUT", 15))
    # Taille maximale acceptée pour un fichier image (Mo).
    taille_max_mo: float = 5.0
    # Types MIME acceptés (contrôle avant écriture sur disque).
    types_mime_acceptes: tuple[str, ...] = ("image/jpeg", "image/png", "image/webp", "image/gif")
    user_agent: str = "Multimodal ETL-bot/0.1 (+https://github.com/multimodal_etl)"


@dataclass(frozen=True)
class TransformConfig:
    """Paramètres de l'étape de transformation (T)."""

    # Longueur minimale de texte (caractères) pour qu'une publication soit exploitable.
    min_text_length: int = 30
    # Si True, une publication sans image téléchargée est écartée (multimodal strict).
    require_image: bool = True
    # Format d'export du dataset transformé.
    output_format: str = "parquet"  # "parquet" ou "csv"


@dataclass(frozen=True)
class LoadConfig:
    """Paramètres de l'étape de chargement (L)."""

    # URL SQLAlchemy de la base cible. Vide -> SQLite local (data/db/multimodal_etl.db).
    db_url: str = field(default_factory=lambda: os.environ.get("MULTIMODAL_ETL_DB_URL", "").strip())
    # Table « à plat », prête pour l'entraînement du modèle.
    table_name: str = "publications"

    @property
    def resolved_url(self) -> str:
        """Renvoie l'URL de connexion effective (SQLite local par défaut)."""
        if self.db_url:
            return self.db_url
        return f"sqlite:///{(DB_DIR / 'multimodal_etl.db').as_posix()}"


def ensure_dirs() -> None:
    """Crée les répertoires de travail s'ils n'existent pas encore."""
    for directory in (
        RAW_DIR,
        IMAGES_DIR,
        PROCESSED_DIR,
        RUNS_DIR,
        SAMPLES_DIR,
        DB_DIR,
        LOGS_DIR,
        INTERIM_DIR,
    ):
        directory.mkdir(parents=True, exist_ok=True)
