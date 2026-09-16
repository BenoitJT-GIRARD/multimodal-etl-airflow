# Data quality report

Written by `scripts/quality_report.py` from `reports/data_quality.json`, measured on
2026-09-15. The sources are live: the numbers below describe the corpus of that
run, and a run today collects a different one.

Of n = 171 publications collected, 127 were kept. Of those,
**100.0%** carry an image file on disk, which is the multimodal
requirement, and **22.0%** carry a ground-truth label.

## Completeness

How many rows carry a real value for each field. An empty string counts as missing.

| field | filled | filled_pct |
|---|---|---|
| title | 127 | 100.0 |
| text | 127 | 100.0 |
| image_path | 127 | 100.0 |
| image_url | 127 | 100.0 |
| label | 28 | 22.0 |
| label_source | 28 | 22.0 |
| published_at | 119 | 93.7 |
| domain | 127 | 100.0 |
| language | 127 | 100.0 |

## By source

What each source contributes, not merely how much.

| source | publications | with_image | labelled | mean_text_length |
|---|---|---|---|---|
| rss:the_guardian | 45 | 45 | 0 | 697 |
| rss:bbc_news | 29 | 29 | 0 | 118 |
| rss:abc_news | 25 | 25 | 0 | 128 |
| fakeddit | 20 | 20 | 20 | 56 |
| fakenewsnet:gossipcop | 8 | 8 | 8 | 57 |

### What the labelled subset really looks like

The 28 labelled publications average **56.1 characters** of text, against 383.5 for the unlabelled ones. The labels come from FakeNewsNet and Fakeddit, which publish a headline and no article body: the only rows usable for supervised training are also the textually poorest. A model trained on this dataset would be learning from headlines.

## Duplicates

Publications the current identifier treats as distinct although their normalised URL and
title match, over n = 127 publications. Measured, not assumed: the
code is `multimodal_etl.quality.duplicates`.

| Measure | Pairs missed | What it would catch |
|---|---|---|
| Same normalised URL **and** title | 0 | one article reached twice through variant URLs |
| Same normalised title, any URL | 0 | one wire story republished by two outlets |

Measured on 127 publications.
