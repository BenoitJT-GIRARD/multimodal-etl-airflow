"""Connecteur 3 — jeu de donnees FakeNewsNet (PolitiFact / GossipCop).

FakeNewsNet (Shu et al., 2018) est la reference pour la detection de fake news :
chaque publication y porte un **label de verite terrain** (``real`` / ``fake``)
issu de PolitiFact ou GossipCop. C'est la seule des trois sources a fournir des
labels fiables, indispensables pour entrainer un classifieur supervise.

Le jeu complet ne peut etre redistribue (politique Twitter, droits des editeurs).
On lit donc :
1. les CSV reels s'ils ont ete telecharges dans ``data/raw/fakenewsnet/`` ;
2. sinon un echantillon representatif versionne dans ``data/samples/``.
"""

from __future__ import annotations

import csv
from pathlib import Path

from multimodal_etl.config import RAW_DIR, SAMPLES_DIR, ExtractionConfig
from multimodal_etl.logging_setup import get_logger

logger = get_logger(__name__)

_REAL_SUBDIR = RAW_DIR / "fakenewsnet"
_SAMPLE_FILE = SAMPLES_DIR / "fakenewsnet_sample.csv"


def _read_csv(path: Path) -> list[dict[str, str]]:
    """Lit un CSV en liste de dictionnaires (encodage UTF-8 tolerant)."""
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _parse_row(row: dict[str, str]) -> dict[str, object]:
    """Transforme une ligne FakeNewsNet en dictionnaire brut normalise."""
    news_source = row.get("news_source", "politifact")
    return {
        "source": f"fakenewsnet:{news_source}",
        "source_type": "dataset",
        "title": row.get("title", ""),
        "text": row.get("text", "") or row.get("title", ""),
        "url": row.get("url", ""),
        "image_url": row.get("image_url", ""),
        "published_at": row.get("published_at", ""),
        "language": "en",
        "label": row.get("label", ""),  # 'real' ou 'fake'
        "label_source": f"fakenewsnet:{news_source}",
    }


def _select_source_file() -> Path | None:
    """Choisit la meilleure source disponible : CSV reels, sinon echantillon."""
    if _REAL_SUBDIR.exists():
        real_csvs = sorted(_REAL_SUBDIR.glob("*.csv"))
        if real_csvs:
            logger.info("FakeNewsNet : %d CSV reels detectes dans %s", len(real_csvs), _REAL_SUBDIR)
            return real_csvs[0] if len(real_csvs) == 1 else _REAL_SUBDIR
    if _SAMPLE_FILE.exists():
        logger.info("FakeNewsNet : utilisation de l'echantillon versionne %s", _SAMPLE_FILE.name)
        return _SAMPLE_FILE
    return None


def fetch_fakenewsnet(config: ExtractionConfig) -> list[dict[str, object]]:
    """Charge les publications labellisees FakeNewsNet."""
    source = _select_source_file()
    if source is None:
        logger.warning("FakeNewsNet : aucune donnee disponible (ni CSV reels, ni echantillon).")
        return []

    rows: list[dict[str, str]] = []
    if source.is_dir():
        for csv_file in sorted(source.glob("*.csv")):
            rows.extend(_read_csv(csv_file))
    else:
        rows = _read_csv(source)

    rows = rows[: config.max_items_per_source]
    records = [_parse_row(row) for row in rows]
    logger.info("FakeNewsNet : %d publications labellisees chargees", len(records))
    return records
