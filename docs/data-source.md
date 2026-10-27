# Where the data comes from

Which sources feed the pipeline, how each one is reached, what it may be used for, and why other
sources were left out. The sources were reviewed on 2026-09-03, and every URL below answered on
that day.

## What the pipeline has to produce

The pipeline is meant to feed a multimodal model, one that reads a publication's text and the
image beside it together. For every publication, the dataset therefore has to supply a text and
an image that belong together.

The scope is data engineering: collecting, normalising and storing. Annotating publications as
true or false belongs to a later stage. Two of the sources provide such a label, which is useful,
and the sources were chosen without requiring one.

| Field | Role | Why |
|---|---|---|
| `title`, `text` | NLP input | the textual signal the language model reads |
| `image_path` | vision input | **the path of the image file on disk**, which the URL alone does not guarantee |
| `url` | traceability | get back to the article, deduplicate |
| `published_at` | freshness | measure topicality, build time-based features |
| `language` | routing | filter by language |
| `domain` | reliability | the publisher's domain is a signal in itself |
| `label` | target | when the source provides one |

`docs/DB.md` gives every field with its type and its role.

## How a source is reached, and what that costs to maintain

| Method | What it is | Maintenance cost |
|---|---|---|
| **RSS feed** | a standard format the publisher issues to be redistributed | very low: the format does not move |
| **REST API** | an official endpoint, authenticated by key | low: versioned, with explicit quotas |
| **Repository download** | files published in the clear on GitHub | none: the files are frozen |
| **Kaggle dataset download** | an export of a reference dataset, done once | none: the dataset is versioned |
| **Open Graph extraction** | reading a page's `og:image` metadata | low: a standard tag |
| **HTML scraping** | parsing the page structure to pull the content out | **high and permanent** |

The first five are official channels, the ways the data producers intended their data to be
consumed, and the pipeline uses only these five.

### Why HTML scraping was ruled out

Scraping is technically possible, with Scrapy, Selenium or Beautiful Soup. It was ruled out for
three reasons, listed from the most important.

**The maintenance cost is permanent and hard to predict.** An extractor built on a site's HTML
structure can break at each redesign, A/B test or renamed CSS class. Maintaining it means
repairing, again and again, code that worked the day before, and the data can stop overnight,
without notice and without recourse.

**Terms of use.** Most publishers forbid the automated extraction of their content in their
terms, and publish an RSS feed or an API for that use. The official channel is simpler and
legally safer.

**The gain is small here.** The publishers' RSS feeds already expose each article's title,
summary and image. Scraping would add the full article body, which the multimodal model does
not need at this stage.

Two scraping tools built on language models were also considered: ScrapeGraphAI, which locates
the wanted data with a language model, and a browser driven by a language-model agent, which can
handle pages that build their content in JavaScript. Both tolerate changes in page structure.
Both also add a cost per page, a latency far above that of reading a feed, and results that can
differ between two runs on the same page. They remain an option for a one-off source that has no
official equivalent.

## The four sources kept

The four sources complement each other: two bring freshness, and two bring labelled, stable
volume.

### Press RSS feeds

| | |
|---|---|
| Access | `rss_feed`, downloaded with `requests` and parsed with `feedparser`, no key |
| Read on | The Guardian, BBC News, ABC News, 2026-09-03 |
| Modalities | title + summary, image in `media:content`, `media:thumbnail`, `enclosure` or `<img>` |
| Format | RSS / XML |
| Language | English |
| Labels | none |
| Rights | public feeds, designed for redistribution; the content is read at run time |

The feeds are free, have no quota and are renewed continuously. They supply most of the volume,
99 of the 127 publications kept by the second run of 2026-09-15, and they keep the dataset
recent.

The difficulty is technical: publishers put the image in different tags. The connector looks in
four places in order, and records an empty image URL when none of them holds one.

The three feeds are the shipped default, and `MULTIMODAL_ETL_RSS_FEEDS=label=url,label=url`
points the reader at another set.

### The NewsData.io API

| | |
|---|---|
| Access | `rest_api`, `requests` on <https://newsdata.io/api/1/news>, parameter `image=1` |
| Read on | 2026-09-03, without a key: the source turned itself off |
| Modalities | `title`, `description`, `content`, `image_url` |
| Format | JSON |
| Language | multilingual, set to `en` |
| Labels | none |
| Rights | official API, key required, limited free tier |

The API returns data that is already normalised, image field included, within a daily quota. The
connector requests one page per run, sets a timeout on the request, and stands down when no key
is present. The dashboard shows the number of API calls each run spends. A failed call raises an
error, which the extract step classifies. An HTTP 429 answer is recorded as `quota`, another
HTTP error or a network error as `network`, and an answer that is not valid JSON, or whose
payload reports an error, as `malformed`.

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

FakeNewsNet is the academic reference dataset of the field. Two of its properties required work.

**The files contain no image.** The CSVs hold `id, news_url, title, tweet_ids`, so the connector
reads an image from each article's Open Graph metadata, the image the publisher declares for
previews of its page. It visits at most 40 articles per run. The measured yield is about one
image for every three articles visited, 14 of 40 in the first run of 2026-09-15. The links are
several years old, collected for a dataset first published in 2018, and a large share of them
are dead. In
the second run of that day, 8 of the 16 GossipCop links visited led to a kept publication, and
none of the 24 PolitiFact links did. A row without an image does not enter the dataset.

**The `tweet_ids` column exceeds the default field limit of the `csv` module.** It holds
thousands of identifiers, so the connector sets a higher limit with `csv.field_size_limit`, and
without it the read fails.

The CSVs are cached under `data/raw/fakenewsnet/`, and later runs read them from there. The Open
Graph pages are still fetched over the network at every run.

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

Fakeddit (Nakamura *et al.*, 2020) is a collection of over a million Reddit posts, and its
multimodal subset pairs each title with an image. It is the source closest to the need. The
connector reads the `2_way` label.

A scripted download from Kaggle requires an account and an API key. The docstring of
`src/multimodal_etl/sources/kaggle_fakeddit.py` explains why the pipeline does not handle that
download: the file is fetched once by hand and placed in `data/raw/kaggle/`, and the connector
only reads it.

> **How to fetch it**
> 1. Get a `*.tsv` file from the `multimodal_only_samples` folder, either at
>    <https://www.kaggle.com/datasets/vanshikavmittal/fakeddit-dataset> (account required) or
>    from the authors' distribution, linked from <https://github.com/entitize/Fakeddit>.
> 2. Place it in `data/raw/kaggle/`.
>
> The file used during the exploration of the sources was `multimodal_test_public.tsv`, which
> has sixteen columns. It is not versioned, since `data/raw/` is ignored by git, so it has to be
> downloaded again on another machine. The runs recorded in this repository read the synthetic
> sample described below.
>
> Fakeddit writes `created_utc` as a Unix timestamp that can carry a decimal part, such as
> `1425138660.0`. The transform step reads both forms. Before that was handled, the date of
> these rows was lost, and the freshness computation with it.

## The data file in this repository

`data/samples/fakeddit_sample.tsv` is **synthetic**. It contains twenty-four made-up rows, which
use nine column names of the real export and its label encoding, and whose image links point to
freely licensed pictures on Wikimedia Commons. The Fakeddit connector reads it when no Kaggle
export is present, so anyone can run the pipeline straight away, and it switches to the real data
as soon as an export is placed in `data/raw/kaggle/`.

The dashboard screenshots and the smoke run use the sample too, so that a picture of the product
and a record of it running carry no publisher's work. The Fakeddit rows of both runs of 2026-09-15
also come from it.

The notebooks under `notebooks/` keep the outputs of an execution against the live sources. A
reader of those outputs sees a few headlines and links that the sources supplied, and the first
lines of one Guardian summary. No picture published by a source appears in them.

## Sources examined and left out

**Reddit and live social networks.** They carry a great deal of multimodal content, but API
access has become restrictive and paid, redistribution rights are uncertain, and the line between
contested opinion and disinformation is particularly blurred there. Fakeddit provides the same
kind of material, already collected and annotated.

**PDF sources.** Fact-checking organisations publish part of their analyses as PDFs, and the
format is a genuine multimodal medium that `pdfplumber` or `PyMuPDF` can read. It was ruled out
for two reasons. The volume is small and irregular, a few documents a month. The pairing of text
and image is also implicit, since an illustration on page 3 is not necessarily tied to the
paragraph before it, and the use case needs an explicit pair. PDFs remain an option for
enriching metadata.

**Hugging Face Datasets.** It is an official channel, often multimodal and labelled, and
technically simple, but it would duplicate Fakeddit for the same need, so it was left out. It is
the natural extension if the volume has to grow.

The sources were found through Google Dataset Search, Kaggle and public-apis.io.

## What is stored, and in which format

**Raw data: JSON, alongside the image files.** A CSV would be enough for text alone. Here every
publication pairs a text with an image file. The images are downloaded into `data/raw/images/`,
and the JSON keeps, for each publication, its text and the path of its image relative to the
project root, so the dataset stays valid on another machine and inside the Airflow container.

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

**Transformed dataset: Parquet.** The format is columnar, typed and compact. The schema is fixed
by this stage, and the file is meant for analytical reads. A configuration parameter can switch
the export to CSV.

**Final storage: a relational database**, SQLite by default, and PostgreSQL when
`MULTIMODAL_ETL_DB_URL` points to one. The data is tabular, its schema is stable, and it is
queried by filters. `docs/DB.md` describes the tables.

## References

- Shu, K., Mahudeswaran, D., Wang, S., Lee, D., Liu, H. (2018). *FakeNewsNet: A Data Repository
  with News Content, Social Context and Dynamic Information for Studying Fake News on Social
  Media*. arXiv:1809.01286, <https://github.com/KaiDMML/FakeNewsNet>
- Nakamura, K., Levy, S., Wang, W. Y. (2020). *Fakeddit: A New Multimodal Benchmark Dataset for
  Fine-grained Fake News Detection*. LREC 2020, <https://github.com/entitize/Fakeddit>
- Zidan, M., Sleem, A., Nabil, A. *et al.* (2025). *Multimodal Fake News Detection: A Survey of
  Text and Visual Content Integration Methods*. International Journal of Computers and
  Information, vol. 7, p. 13-25.
- The Open Graph protocol, <https://ogp.me/>
