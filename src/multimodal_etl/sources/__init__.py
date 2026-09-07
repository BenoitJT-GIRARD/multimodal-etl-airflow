"""Extraction connectors, one module per data source.

Every connector exposes a ``fetch_*`` function returning a list of "raw" dictionaries
that share the same keys (:data:`RAW_KEYS`), so that the transform step can process them
uniformly whatever the data came from.

The ``access_method`` field records **how** the data was obtained: that is what lets the
exploration report and the KPIs attribute each publication to its access method (feed,
API, dataset download).
"""

from __future__ import annotations

# Minimum keys every connector guarantees on output.
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

# Allowed values for ``access_method``.
ACCESS_METHODS: tuple[str, ...] = (
    "rss_feed",
    "rest_api",
    "github_download",
    "kaggle_download",
)

# Allowed values for ``image_source``: the image is either supplied directly by the
# source, or found in the article's Open Graph metadata.
IMAGE_ORIGINS: tuple[str, ...] = ("native", "open_graph", "none")
