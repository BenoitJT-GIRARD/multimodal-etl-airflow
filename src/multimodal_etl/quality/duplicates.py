"""Measure what the deduplication key lets through.

The publication identifier hashes the **exact** URL and the **exact** title. On a news
feed — which is the use case — that is fragile in two ways the audit called out:

* a title corrected by one character, a typo fixed or an editorial suffix added, produces a
  different identifier for the same article;
* equivalent URL variants (``utm_*`` tracking parameters, ``http`` against ``https``, a
  trailing slash, a ``www.`` prefix) produce different identifiers too.

The same wire story regularly arrives through several feeds with exactly those variations.
This module measures how many pairs the current key misses, **before** anything is
corrected: fixing it silently would produce no number, and a number is what makes the fix
worth publishing.
"""

from __future__ import annotations

import re
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

import pandas as pd

# Parameters that identify the referrer or the campaign, never the article.
_TRACKING = re.compile(r"^(utm_|fbclid$|gclid$|mc_cid$|mc_eid$|igshid$|ref$|ref_src$)")
_PUNCTUATION = re.compile(r"[^\w\s]", re.UNICODE)
_SPACES = re.compile(r"\s+")


def normalise_url(url: str) -> str:
    """Bring equivalent URL variants to a single form, so they can be compared.

    Deliberately conservative: the scheme, the ``www.`` prefix, a trailing slash and the
    tracking parameters are dropped, and the remaining parameters are sorted. Everything
    else is kept — dropping every parameter would merge genuinely different articles on the
    sites that identify them by a query string.
    """
    url = (url or "").strip()
    parsed = urlparse(url)
    if not parsed.netloc:
        return url.lower()

    kept = [(k, v) for k, v in parse_qsl(parsed.query) if not _TRACKING.match(k)]
    return urlunparse(
        (
            "https",
            parsed.netloc.lower().removeprefix("www."),
            parsed.path.rstrip("/"),
            "",
            urlencode(sorted(kept)),
            "",
        )
    )


def normalise_title(title: str) -> str:
    """Reduce a title to its words, lowercased.

    Case, punctuation and repeated spaces are removed: a fixed typo or an added em dash
    must not turn one article into two.
    """
    return _SPACES.sub(" ", _PUNCTUATION.sub(" ", (title or "").lower())).strip()


def _normalised(df: pd.DataFrame) -> pd.DataFrame:
    keys = pd.DataFrame(
        {
            "id": df["id"].astype(str),
            "url": df["url"].fillna("").astype(str).map(normalise_url),
            "title": df["title"].fillna("").astype(str).map(normalise_title),
        }
    )
    return keys


def missed_duplicates(df: pd.DataFrame) -> list[dict[str, object]]:
    """Return the groups of publications the current key treats as distinct.

    Each group is listed with its identifiers, so the finding can be checked by eye rather
    than believed: a normalisation that is too aggressive would show up here as a group of
    articles that are plainly different.
    """
    if df.empty:
        return []

    keys = _normalised(df)
    grouped = keys.groupby(["url", "title"])["id"].apply(list)
    return [
        {"normalised_url": url, "normalised_title": title, "ids": ids}
        for (url, title), ids in grouped.items()
        if len(ids) > 1
    ]


def duplicate_summary(df: pd.DataFrame) -> dict[str, int]:
    """Count the publications, the groups of duplicates, and the pairs missed.

    Pairs rather than groups: three records of the same article are three pairs the key
    should have caught, not one.
    """
    groups = missed_duplicates(df)
    pairs = sum(len(g["ids"]) * (len(g["ids"]) - 1) // 2 for g in groups)
    return {"publications": len(df), "groups": len(groups), "missed_pairs": pairs}


def missed_by_title(df: pd.DataFrame) -> list[dict[str, object]]:
    """Return the publications sharing a normalised title but not an identifier.

    This is the case URL normalisation cannot reach. The same wire story republished by two
    outlets carries two genuinely different URLs — different domains, different paths — so
    no amount of normalising brings them together. Only the text can.
    """
    if df.empty:
        return []

    keys = _normalised(df)
    keys = keys[keys["title"] != ""]
    grouped = keys.groupby("title")["id"].apply(list)
    return [
        {"normalised_title": title, "ids": ids} for title, ids in grouped.items() if len(ids) > 1
    ]


def title_summary(df: pd.DataFrame) -> dict[str, int]:
    """Count the duplicates that share a title but not a URL."""
    groups = missed_by_title(df)
    pairs = sum(len(g["ids"]) * (len(g["ids"]) - 1) // 2 for g in groups)
    return {"publications": len(df), "groups": len(groups), "missed_pairs": pairs}
