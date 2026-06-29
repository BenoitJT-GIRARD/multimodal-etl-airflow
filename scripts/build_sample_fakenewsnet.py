"""Genere un echantillon representatif et reproductible de FakeNewsNet.

Le jeu complet FakeNewsNet ne peut pas etre redistribue (droits Twitter / editeurs).
Pour que le pipeline reste executable hors-ligne et de maniere deterministe, on
versionne un petit echantillon **illustratif** respectant le schema de la source :
identifiant, news_source (politifact/gossipcop), label (real/fake), titre, texte,
url et image_url. Les contenus sont volontairement synthetiques et neutres.

Usage :
    uv run python scripts/build_sample_fakenewsnet.py
"""

from __future__ import annotations

import csv
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from multimodal_etl.config import SAMPLES_DIR, ensure_dirs

# (news_source, label, titre, texte, slug) — contenus synthetiques illustratifs.
_RECORDS: tuple[tuple[str, str, str, str, str], ...] = (
    (
        "politifact",
        "fake",
        "Officials announce free electricity for every household next month",
        "A widely shared post claims the government will supply electricity at no cost to all homes "
        "starting next month. No official source confirms the measure.",
        "free-electricity",
    ),
    (
        "politifact",
        "real",
        "Central bank keeps its key interest rate unchanged",
        "The central bank confirmed during its scheduled meeting that the main policy rate stays "
        "the same, citing stable inflation expectations.",
        "rate-unchanged",
    ),
    (
        "politifact",
        "fake",
        "Viral image claims a new law bans all private cars in the capital",
        "An edited screenshot circulating online states that private vehicles are now forbidden "
        "downtown. City officials have issued no such regulation.",
        "ban-private-cars",
    ),
    (
        "politifact",
        "real",
        "National weather agency issues a storm warning for the coast",
        "The meteorological service published an official alert ahead of strong winds expected "
        "along the coastline this weekend.",
        "storm-warning",
    ),
    (
        "politifact",
        "fake",
        "Post says a common spice was secretly approved as a vaccine",
        "A misleading article asserts that a kitchen spice received medical approval as a vaccine. "
        "Health authorities have not made any such statement.",
        "spice-vaccine",
    ),
    (
        "politifact",
        "real",
        "Parliament passes the annual budget after final vote",
        "Lawmakers approved the yearly budget following the concluding session, with the text now "
        "moving to publication.",
        "budget-passed",
    ),
    (
        "politifact",
        "fake",
        "Rumor claims the moon will disappear for a full week",
        "Several accounts spread the claim that the moon will be invisible for seven days. "
        "Astronomers confirm no such event is possible.",
        "moon-disappear",
    ),
    (
        "politifact",
        "real",
        "Transport ministry launches a new high-speed rail line",
        "The ministry inaugurated a high-speed connection between two major cities, reducing the "
        "travel time significantly.",
        "rail-line",
    ),
    (
        "gossipcop",
        "fake",
        "Celebrity reportedly buys an entire private island overnight",
        "A tabloid-style post claims a famous singer purchased a whole island in a single day. "
        "Representatives have not confirmed the story.",
        "private-island",
    ),
    (
        "gossipcop",
        "real",
        "Award ceremony announces this year's list of nominees",
        "Organizers released the official nominee list for the upcoming ceremony across the main "
        "film categories.",
        "award-nominees",
    ),
    (
        "gossipcop",
        "fake",
        "Actor allegedly quits acting to become a full-time astronaut",
        "A viral article states that a well-known actor abandoned cinema to join a space program. "
        "No agency has corroborated the claim.",
        "actor-astronaut",
    ),
    (
        "gossipcop",
        "real",
        "Music festival confirms its headliners for the summer edition",
        "The festival's organizing team officially announced the main performers scheduled for the "
        "summer line-up.",
        "festival-headliners",
    ),
    (
        "gossipcop",
        "fake",
        "Photo claims two rival stars secretly opened a restaurant together",
        "An unverified post asserts that two competing celebrities co-own a new restaurant. "
        "Neither party has acknowledged the rumor.",
        "rival-restaurant",
    ),
    (
        "gossipcop",
        "real",
        "Streaming platform renews a popular series for a new season",
        "The platform confirmed the renewal of a successful show, with production expected to start "
        "later this year.",
        "series-renewed",
    ),
    (
        "gossipcop",
        "fake",
        "Report says a film was shot entirely on a single phone in one day",
        "A sensational claim states that a feature film was recorded on one smartphone within "
        "twenty-four hours. The studio denies the account.",
        "phone-film",
    ),
    (
        "gossipcop",
        "real",
        "Director shares the official release date of the next blockbuster",
        "During a press event, the director revealed the confirmed theatrical release date for the "
        "upcoming blockbuster.",
        "release-date",
    ),
    (
        "politifact",
        "fake",
        "Message claims tap water will be replaced by sparkling water citywide",
        "A chain message asserts that the city will switch its entire tap supply to sparkling water. "
        "The utility company calls it false.",
        "sparkling-water",
    ),
    (
        "politifact",
        "real",
        "Education department updates the national exam calendar",
        "The department published the revised schedule for national examinations, available on its "
        "official website.",
        "exam-calendar",
    ),
    (
        "gossipcop",
        "fake",
        "Star supposedly trademarks a common everyday word",
        "A misleading post claims a celebrity legally trademarked an ordinary word everyone uses. "
        "No trademark filing supports this.",
        "trademark-word",
    ),
    (
        "gossipcop",
        "real",
        "Theatre company announces a national tour for its new play",
        "The company confirmed the cities and venues for the upcoming tour of its latest stage "
        "production.",
        "theatre-tour",
    ),
    (
        "politifact",
        "fake",
        "Viral claim says public transport will run backwards on weekends",
        "A joke-turned-rumor states that trains will operate in reverse on weekends. The operator "
        "confirms schedules are unchanged.",
        "reverse-transport",
    ),
    (
        "politifact",
        "real",
        "Health ministry opens a new vaccination campaign for the season",
        "The ministry launched its seasonal vaccination campaign, detailing eligible groups and "
        "available locations.",
        "vaccination-campaign",
    ),
    (
        "gossipcop",
        "fake",
        "Singer reportedly cancels a world tour to open a bakery",
        "An unverified article claims a pop singer scrapped a global tour to run a bakery full time. "
        "The management team has not confirmed it.",
        "bakery-tour",
    ),
    (
        "gossipcop",
        "real",
        "Studio releases the official trailer for its animated feature",
        "The studio published the first official trailer of its forthcoming animated film on its "
        "verified channels.",
        "animated-trailer",
    ),
)


def build() -> Path:
    """Ecrit l'echantillon CSV et renvoie son chemin."""
    ensure_dirs()
    output = SAMPLES_DIR / "fakenewsnet_sample.csv"
    fieldnames = ["id", "news_source", "label", "title", "text", "url", "image_url", "published_at"]

    with output.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for index, (news_source, label, title, text, slug) in enumerate(_RECORDS, start=1):
            writer.writerow(
                {
                    "id": f"{news_source}-{label}-{index:03d}",
                    "news_source": news_source,
                    "label": label,
                    "title": title,
                    "text": text,
                    "url": f"https://example-news.org/{news_source}/{slug}",
                    "image_url": f"https://picsum.photos/seed/{slug}/800/600.jpg",
                    "published_at": f"2026-05-{(index % 28) + 1:02d}T09:00:00Z",
                }
            )
    print(f"[ok] echantillon FakeNewsNet ecrit : {output} ({len(_RECORDS)} lignes)")
    return output


if __name__ == "__main__":
    build()
