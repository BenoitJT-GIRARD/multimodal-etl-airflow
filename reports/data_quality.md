# Data quality report

Generated from the most recent dataset, by `scripts/quality_report.py`.

123 publications kept out of 164 collected.
**100.0%** carry an image on disk — the multimodal requirement — and
**26.0%** carry a ground-truth label.

## Completeness

How many rows carry a real value for each field. An empty string counts as missing.

| field | filled | filled_pct |
|---|---|---|
| title | 123 | 100.0 |
| text | 123 | 100.0 |
| image_path | 123 | 100.0 |
| image_url | 123 | 100.0 |
| label | 32 | 26.0 |
| label_source | 32 | 26.0 |
| published_at | 115 | 93.5 |
| domain | 123 | 100.0 |
| language | 123 | 100.0 |

## By source

What each source contributes, not merely how much.

| source | publications | with_image | labelled | mean_text_length |
|---|---|---|---|---|
| rss:the_guardian | 45 | 45 | 0 | 602 |
| fakeddit | 24 | 24 | 24 | 54 |
| rss:abc_news | 24 | 24 | 0 | 131 |
| rss:bbc_news | 22 | 22 | 0 | 120 |
| fakenewsnet:gossipcop | 8 | 8 | 8 | 57 |

### What the labelled subset really looks like

The 32 labelled publications average **54.9 characters** of text, against 361.3 for the unlabelled ones. The labels come from FakeNewsNet and Fakeddit, which publish a headline and no article body: the only rows usable for supervised training are also the textually poorest. A model trained on this dataset would be learning from headlines.

## Duplicates

Publications the current identifier treats as distinct although their normalised URL and
title match. Measured, not assumed — see `multimodal_etl.quality.duplicates`.

| Measure | Pairs missed | What it would catch |
|---|---|---|
| Same normalised URL **and** title | 0 | one article reached twice through variant URLs |
| Same normalised title, any URL | 0 | one wire story republished by two outlets |

Measured on 123 publications.
