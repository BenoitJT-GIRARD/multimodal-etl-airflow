# Where the data comes from

Which sources feed the pipeline, how each one is reached, what it is allowed to be used for,
and why the others were left out. Read on 2026-09-03; every URL below was answering that day.

## What the pipeline has to produce

This pipeline feeds a **multimodal** model: one that reads a publication's text and the image
beside it together. So for every publication the dataset has to supply **a text and an image
that genuinely belong together**.

The scope is data engineering: collect, normalise, store. The *true / false* annotation is not
part of it: that comes later, and the sources that do provide one are a bonus and not a
selection criterion.

| Field | Role | Why |
|---|---|---|
| `title`, `text` | NLP input | the textual signal the language model reads |
| `image_path` | vision input | **the image file on disk**, not merely its URL |
| `url` | traceability | get back to the article, deduplicate |
| `published_at` | freshness | measure topicality, build time-based features |
| `language` | routing | filter by language |
| `domain` | reliability | the publisher's domain is a signal in itself |
| `label` | target | when the source provides one |

Every field, its type and its role are in `docs/DB.md`.

## How a source is reached, and what that costs to maintain

| Method | What it is | Maintenance cost |
|---|---|---|
| **RSS feed** | a standard format the publisher issues to be redistributed | very low: the format does not move |
| **REST API** | an official endpoint, authenticated by key | low: versioned, with explicit quotas |
| **Repository download** | files published in the clear on GitHub | none: the files are frozen |
| **Kaggle dataset download** | an export of a reference dataset, done once | none: the dataset is versioned |
| **Open Graph extraction** | reading a page's `og:image` metadata | low: a standard tag |
| **HTML scraping** | parsing the page structure to pull the content out | **high and permanent** |

The first five are official channels: the data producer intended it to be consumed this way.
Those are the ones kept.

### Why the pipeline does not scrape

Scraping is technically within reach, with Scrapy, Selenium or Beautiful Soup, and it was ruled
out for three reasons, in this order of importance.

**The maintenance cost is permanent and unpredictable.** An extractor resting on a site's HTML
structure breaks at every redesign, every A/B test, every CSS class rename. The team
maintaining it spends its time repairing what worked the day before. The data can stop
overnight, without notice and without recourse.

**Terms of use.** Most publishers forbid automated extraction of their content in their terms,
while publishing an RSS feed or an API right next to it, meant for exactly this use. Taking
the official channel is both simpler and legally safer.

**The effort-to-gain ratio is bad here.** The same publishers' RSS feeds already expose each
article's title, summary and image. Scraping would add the full article body, which the
multimodal model does not need first.

Two AI-assisted tools were looked at, because they change the nature of the problem:
**ScrapeGraphAI**, which locates the wanted data with a language model, and an agent-driven
browser able to handle pages that build their content in JavaScript. Both remove the breakage
at every structural change, and both introduce a cost per page, a latency on a different scale
from reading a feed, and **non-reproducibility**: two runs on the same page may not extract
exactly the same thing. They stay noted for a one-off source with no official equivalent.

## The four sources kept

They complement each other: two bring freshness, two bring labelled, stable volume.

### Press RSS feeds: the multimodal backbone

| | |
|---|---|
| Access | `rss_feed`, through `feedparser`, no key |
| Read on | The Guardian, BBC News, ABC News, 2026-09-03 |
| Modalities | title + summary, image in `media:content`, `enclosure` or `<img>` |
| Format | RSS / XML |
| Language | English |
| Labels | none |
| Rights | public feeds, designed for redistribution; the content is read at run time and never committed |

The steadiest source: free, no quota, continuously renewed. It supplies most of the volume and
guarantees the dataset's freshness.

The difficulty is technical: **no two publishers put the image in the same tag**. The connector
tries four locations in order, then gives up.

The three feeds are the shipped default and not a constraint of the code:
`MULTIMODAL_ETL_RSS_FEEDS=label=url,label=url` points the reader at any other set.

### The NewsData.io API: structured news

| | |
|---|---|
| Access | `rest_api`, `requests` on <https://newsdata.io/api/1/news>, parameter `image=1` |
| Read on | 2026-09-03, without a key: the source turned itself off |
| Modalities | `title`, `description`, `content`, `image_url` |
| Format | JSON |
| Language | multilingual, set to `en` |
| Labels | none |
| Rights | official API, key required, limited free tier |

The API returns already-normalised data, image field included, against a daily quota. One page
per run, a timeout on the request, and a clean stand-down when no key is present; what the quota
costs is tracked as an indicator of its own.

### FakeNewsNet: a labelled index fetched from GitHub

| | |
|---|---|
| Access | `github_download`, the CSVs being published in the clear at <https://github.com/KaiDMML/FakeNewsNet> |
| Read on | 2026-09-03 |
| Modalities | title + article URL; **no image in the files** |
| Format | CSV, four files: PolitiFact and GossipCop, `fake` and `real` |
| Language | English |
| Labels | PolitiFact / GossipCop ground truth |
| Rights | the index is redistributable; the associated Twitter data is not, and is not used |

The academic reference of the field. Two points took work.

**The files are not multimodal.** The CSVs hold `id, news_url, title, tweet_ids` and no image,
so the connector fetches one from the article's **Open Graph** metadata, which is the image the
publisher itself issues for its page preview. Measured yield: about one image per three articles
visited. The PolitiFact links are seven to nine years old and a large share of them are dead,
where GossipCop's, more recent, answer roughly half the time. A row with no image does not reach
the dataset.

**The `tweet_ids` column exceeds the `csv` module's field limit.** It holds thousands of
identifiers; `csv.field_size_limit` has to be raised explicitly, or the read fails.

The files are cached under `data/raw/fakenewsnet/`: later runs no longer need the network.

### Fakeddit: a multimodal dataset fetched from Kaggle

| | |
|---|---|
| Access | `kaggle_download`, export downloaded once by hand, read locally |
| Read on | 2026-09-03 |
| Modalities | `clean_title` + `image_url`, column `hasImage` |
| Format | TSV |
| Language | English |
| Labels | three levels: `2_way`, `3_way`, `6_way` |
| Rights | research use, citation of the original paper |

Fakeddit (Nakamura *et al.*, 2020) gathers more than a million natively multimodal Reddit
publications. It is the source closest to the need.

Downloading it requires a Kaggle account and an API key. The docstring of
`src/multimodal_etl/sources/kaggle_fakeddit.py` says why neither is worth adding to the
pipeline: the file is fetched **once, by hand**, dropped into `data/raw/kaggle/`, and the
connector only reads it.

> **How to fetch it**
> 1. Get a `*.tsv` file from the `multimodal_only_samples` folder, either at
>    <https://www.kaggle.com/datasets/vanshikavmittal/fakeddit-dataset> (account required) or
>    from the authors' distribution, linked from <https://github.com/entitize/Fakeddit>.
> 2. Drop it into `data/raw/kaggle/`.
>
> The file used here is `multimodal_test_public.tsv`, sixteen columns. It is not versioned,
> since `data/` is ignored by git, so it has to be re-downloaded on another machine.
>
> One detail handled along the way: Fakeddit encodes `created_utc` as a float where the other
> sources use an integer. Without that, the date was lost, and with it the freshness
> computation.

## The one data file this repository ships

`data/samples/fakeddit_sample.tsv` is **synthetic**: twenty-four invented rows with the real
column structure and the real label encoding, illustrated by freely-licensed files on
Wikimedia Commons. It is what the Fakeddit connector falls back to when the real export is
absent, so the pipeline is immediately runnable by anyone, and it switches back to the real
data on its own as soon as that is present.

The captures and the smoke run use it too, and for the same reason: a picture of the product
and a record of it running must not carry a publisher's work.

## Sources examined and left out

**Reddit and live social networks.** Very rich in multimodal content, but API access has
become restrictive and paid, redistribution rights are uncertain, and the line between
contested opinion and disinformation is particularly blurred there. Fakeddit brings the same
material, already collected and annotated.

**PDF sources.** Fact-checking organisations publish part of their analyses as PDFs, and the
format really is a multimodal medium, workable with `pdfplumber` or `PyMuPDF`. Ruled out for
two reasons: the volume is small and irregular, a few documents a month, and the text-image
pairing is **implicit**: an illustration on page 3 is not necessarily tied to the paragraph
before it, where the use case demands an unambiguous couple. A lead for enriching metadata,
not for supplying volume.

**Hugging Face Datasets.** An official channel, often multimodal and labelled, technically
simple. Not kept because it would duplicate Fakeddit on the same need. It is the natural
extension should the volume need to grow.

Directories consulted to find these sources: Google Dataset Search, Kaggle, public-apis.io.

## What is stored, and in which format

**Raw data: JSON, alongside the image files.** A CSV would do for text alone. Here every
publication pairs a text and an image file: the images are downloaded into
`data/raw/images/`, and the JSON keeps, for each publication, its text and the **path of its
image**, relative to the project root, so the dataset stays valid on another machine and
inside the Airflow container.

```json
{
  "source": "rss:bbc_news",
  "title": "…",
  "text": "…",
  "image_url": "https://…/photo.jpg",
  "image_path": "data/raw/images/9b7c024c13d467b6.jpg",
  "image_source": "native"
}
```

**Transformed dataset: Parquet.** Columnar, typed and compact: the schema is fixed by this
stage and the file is meant for analytical reads. A CSV export stays available through a
configuration parameter.

**Final storage: a relational database**, SQLite locally and PostgreSQL in production. The
data is tabular, of stable schema, and queried by filters. `docs/DB.md` gives the tables.

## References

- Shu, K., Mahudeswaran, D., Wang, S., Lee, D., Liu, H. (2018). *FakeNewsNet: A Data Repository
  with News Content, Social Context and Dynamic Information for Studying Fake News on Social
  Media*. arXiv:1809.01286 — <https://github.com/KaiDMML/FakeNewsNet>
- Nakamura, K., Levy, S., Wang, W. Y. (2020). *Fakeddit: A New Multimodal Benchmark Dataset for
  Fine-grained Fake News Detection*. LREC 2020 — <https://github.com/entitize/Fakeddit>
- Zidan, M., Sleem, A., Nabil, A. *et al.* (2025). *Multimodal Fake News Detection: A Survey of
  Text and Visual Content Integration Methods*. International Journal of Computers and
  Information, vol. 7, p. 13-25.
- The Open Graph protocol — <https://ogp.me/>
