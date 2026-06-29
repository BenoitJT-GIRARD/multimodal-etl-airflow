"""Connecteurs d'extraction, un module par source de donnees.

Chaque connecteur expose une fonction ``fetch_*`` qui renvoie une liste de
dictionnaires « bruts » partageant les memes cles, afin que l'etape de
transformation puisse les traiter de maniere uniforme quelle que soit l'origine.
"""

from __future__ import annotations

# Cles minimales garanties par chaque connecteur en sortie.
RAW_KEYS: tuple[str, ...] = (
    "source",
    "source_type",
    "title",
    "text",
    "url",
    "image_url",
    "published_at",
    "language",
    "label",
    "label_source",
)
