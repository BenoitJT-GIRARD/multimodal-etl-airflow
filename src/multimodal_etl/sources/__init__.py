"""Connecteurs d'extraction, un module par source de données.

Chaque connecteur expose une fonction ``fetch_*`` qui renvoie une liste de
dictionnaires « bruts » partageant les mêmes clés (:data:`RAW_KEYS`), afin que
l'étape de transformation puisse les traiter de manière uniforme quelle que soit
l'origine de la donnée.

Le champ ``access_method`` trace **comment** la donnée a été obtenue : c'est ce qui
permet, dans le rapport d'exploration comme dans les KPI, de rattacher chaque
publication à sa méthode d'accès (flux, API, téléchargement de jeu de données).
"""

from __future__ import annotations

# Clés minimales garanties par chaque connecteur en sortie.
RAW_KEYS: tuple[str, ...] = (
    "source",
    "source_type",
    "access_method",
    "title",
    "text",
    "url",
    "image_url",
    "image_source",
    "published_at",
    "language",
    "label",
    "label_source",
)

# Valeurs autorisées pour ``access_method``.
METHODES_ACCES: tuple[str, ...] = (
    "flux_rss",
    "api_rest",
    "telechargement_github",
    "telechargement_kaggle",
)

# Valeurs autorisées pour ``image_source`` : l'image est soit fournie directement
# par la source, soit retrouvée dans les métadonnées Open Graph de l'article.
ORIGINES_IMAGE: tuple[str, ...] = ("native", "open_graph", "aucune")
