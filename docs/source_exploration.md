# Data source exploration report

Which sources feed the pipeline, how they are reached, and why the others were left out.

---

## 1. What the pipeline has to produce

This pipeline feeds a **multimodal** model: one that reads a publication's text and the
image beside it together. So for every publication the dataset has to supply **a text and
an image that genuinely belong together**.

The scope of this project is **data engineering**: collect, normalise, store. The
*true / false* annotation is not part of it — that comes later, and the sources that do
provide one are a bonus, not a selection criterion.

### Indispensable fields

| Field | Role | Why |
|---|---|---|
| `title`, `text` | NLP input | the textual signal the language model reads |
| `image_path` | vision input | **the image file on disk**, not merely its URL |
| `url` | traceability | get back to the article, deduplicate |
| `published_at` | freshness | measure topicality, build time-based features |
| `language` | routing | filter by language |
| `domain` | reliability | the publisher's domain is a signal in itself |
| `label` | target | when the source provides one |

The full schema is in `data_schema.md`.

---

## 2. The possible access methods

Before choosing sources, you have to choose **how** you reach them. Five methods were
conceivable, and they do not commit you to the same maintenance effort:

| Method | What it is | Maintenance cost |
|---|---|---|
| **RSS feed** | a standard format the publisher issues to be redistributed | very low: the format does not move |
| **REST API** | an official endpoint, authenticated by key | low: versioned, with explicit quotas |
| **Repository download** | files published in the clear on GitHub | none: the files are frozen |
| **Kaggle dataset download** | an export of a reference dataset, done once | none: the dataset is versioned |
| **Multimodal extraction** | reading a page's `Open Graph` metadata | low: a standard tag |
| **HTML scraping** | parsing the page structure to pull the content out | **high and permanent** (see §3) |

The first four rows are **official channels**: the data producer intended it to be
consumed this way. Those are the ones kept.

---

## 3. Why the pipeline does not scrape

Scraping is technically within reach (Scrapy, Selenium, Beautiful Soup). It was ruled out
for three reasons, in this order of importance.

**The maintenance cost is permanent and unpredictable.** An extractor resting on a site's
HTML structure breaks at every redesign, every A/B test, every CSS class rename. The team
maintaining it spends its time repairing what worked the day before, never moving forward.
That way of working — a permanent race behind the target platforms' changes — durably
weakens the products depending on it: the data can stop overnight, without notice and
without recourse. Building this pipeline's ingestion on that means accepting an operating
risk that nothing compensates for.

**Terms of use.** Most publishers forbid automated extraction of their content in their
terms, while publishing an RSS feed or an API *right next to it*, meant for exactly this
use. Taking the official channel is both simpler and legally safer.

**The effort-to-gain ratio is bad here.** The same publishers' RSS feeds already expose
each article's title, summary and image: scraping would only add the full article body,
which the multimodal model does not need first.

### AI-assisted scraping tools

Two recent tools were looked at, because they change the nature of the problem:

- **ScrapeGraphAI**: describe the data you want in natural language and let a language
  model find where it sits in the page. This does genuinely remove the breakage at every
  structural change.
- **An agent-driven browser**: the same principle, with a real browser able to handle
  pages that build their content in JavaScript.

They solve the maintenance problem, but introduce others that are disqualifying for a
daily pipeline: a **cost per page** (a model call), a **latency** on a different scale
from reading a feed, and above all **non-reproducibility** — two runs on the same page may
not extract exactly the same thing. A pipeline whose output cannot be guaranteed is not
industrialisable. They stay noted as an option for a one-off source with no official
equivalent.

---

## 4. The four sources kept

They were chosen to complement each other: two bring **freshness**, two bring **labelled,
stable volume**.

### 4.1 Press RSS feeds — the multimodal backbone

| | |
|---|---|
| Access | `rss_feed` — `feedparser`, no key |
| Modalities | title + summary, image in `media:content`, `enclosure` or `<img>` |
| Format | RSS / XML |
| Language | English (The Guardian, BBC News, ABC News) |
| Labels | none |
| Rights | public feeds, designed for redistribution |

This is the steadiest source: free, no quota, continuously renewed. It supplies most of the
volume and guarantees the dataset's freshness.

The difficulty is technical: **the image is not in the same place from one publisher to the
next**. The connector looks for it in four locations in turn before giving up.

### 4.2 The NewsData.io API — structured news

| | |
|---|---|
| Access | `rest_api` — `requests` on `/api/1/news`, parameter `image=1` |
| Modalities | `title`, `description`, `content`, `image_url` |
| Format | JSON |
| Language | multilingual (set to `en`) |
| Labels | none |
| Rights | official API, key required, limited free tier |

The API returns already-normalised data, with an explicit image field. In exchange it
imposes a **daily quota**: the connector reads a single page, sets a timeout, and disables
itself cleanly when no key is supplied. Quota consumption is tracked as a cost KPI.

### 4.3 FakeNewsNet — a labelled dataset fetched from GitHub

| | |
|---|---|
| Access | `github_download` — the CSVs are published in the clear in the official repository |
| Modalities | title + article URL; **no image in the files** |
| Format | CSV (4 files: PolitiFact and GossipCop, `fake` and `real`) |
| Language | English |
| Labels | PolitiFact / GossipCop ground truth |
| Rights | the index is redistributable; the associated Twitter data is not, and is not used |

This is the academic reference of the field. Two points took work:

**The files are not multimodal.** The CSVs hold `id, news_url, title, tweet_ids` — no
image. So the connector goes and looks for one in the article's **Open Graph** metadata
(`og:image`), that is, the image the publisher itself issues for its page preview. The
measured yield is roughly **one image recovered per three articles visited**: the
PolitiFact URLs date from 2016-2018 and many no longer answer, while GossipCop's, more
recent, succeed about half the time. Publications without an image are dropped at the
transform step.

**The `tweet_ids` column exceeds the `csv` module's field limit.** It holds thousands of
identifiers; `csv.field_size_limit` has to be raised explicitly, or the read fails.

The files are cached under `data/raw/fakenewsnet/`: later runs no longer need the network.

### 4.4 Fakeddit — a multimodal dataset fetched from Kaggle

| | |
|---|---|
| Access | `kaggle_download` — export downloaded once, read locally |
| Modalities | `clean_title` + `image_url` (column `hasImage`) |
| Format | TSV |
| Language | English |
| Labels | 3 levels (`2_way`, `3_way`, `6_way`) |
| Rights | research use, citation of the original paper |

Fakeddit (Nakamura *et al.*, 2020) gathers more than a million **natively multimodal**
Reddit publications. It is the source closest to the need.

Downloading a Kaggle dataset requires an account and an API key. Rather than add a
dependency and a secret to the pipeline for a reference dataset that does not change, we do
what a company does: **the file is downloaded once, by hand**, and dropped into
`data/raw/kaggle/`. The connector only reads it.

> **How to fetch it**
> 1. Get a `*.tsv` file from the `multimodal_only_samples` folder, either at
>    <https://www.kaggle.com/datasets/vanshikavmittal/fakeddit-dataset> (account required)
>    or from the authors' distribution, linked from
>    <https://github.com/entitize/Fakeddit>.
> 2. Drop it into `data/raw/kaggle/`.
>
> The file used here is `multimodal_test_public.tsv` (15.6 MB, 16 columns): it brings 29
> labelled multimodal publications from about fifteen subreddits. It is not versioned —
> `data/` is ignored by git — so it has to be re-downloaded on another machine.
>
> In its absence, the connector falls back to a **versioned demonstration sample**
> (`data/samples/fakeddit_sample.tsv`): the same columns and the same label encoding as the
> real dataset, made-up titles, and royalty-free images hosted by Wikimedia Commons. The
> pipeline therefore stays immediately runnable by anyone, and switches back to the real
> data on its own as soon as it is present.
>
> One detail handled along the way: Fakeddit encodes `created_utc` as a float
> (`1425138660.0`) where other sources use an integer. Without that, the date was lost, and
> with it the freshness computation.

---

## 5. Sources examined and left out

**Reddit and live social networks.** Very rich in multimodal content, but API access has
become restrictive and paid, redistribution rights are uncertain, and the line between
contested opinion and disinformation is particularly blurred there. Fakeddit brings the
same material, already collected and annotated.

**PDF sources.** Fact-checking organisations publish part of their analyses as PDFs
(reports, rulings, notes). The format really is a multimodal medium — text and
illustrations in the same document — and it is workable with `pdfplumber` or `PyMuPDF`.
Ruled out here for two reasons: the volume is small and irregular (a few documents a
month), and the text-image pairing is **implicit** — an illustration on page 3 is not
necessarily tied to the paragraph before it, whereas the use case demands an unambiguous
text-image couple. It is a lead for enriching metadata, not for supplying volume.

**Hugging Face Datasets.** An official channel, often multimodal and labelled, technically
simple (`datasets.load_dataset`). Not kept because it would duplicate Fakeddit on the same
need. It is the natural extension should the volume need to grow.

**Directories consulted** to find these sources: Google Dataset Search, Kaggle,
public-apis.io.

---

## 6. Storage formats chosen

The choice of format follows directly from the multimodal nature of the data.

**Raw data: JSON, alongside the image files.** A CSV would do for text alone. Here every
publication pairs a text **and an image file**: the images are downloaded into
`data/raw/images/`, and the JSON keeps, for each publication, its text and the **path of
its image**. That path is relative to the project root, so the dataset stays valid
somewhere other than the machine that produced it — the pipeline runs locally as well as
inside an Airflow container.

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

**Final storage: a relational database** (SQLite locally, PostgreSQL in production). The
data is tabular, of stable schema, and queried by filters — the textbook case for
relational. It is loaded in two shapes: an exploded model of tables joined by keys, and a
flat table ready for training.

---

## 7. Summary

| Source | Access | Text | Image | Label | Main contribution |
|---|---|:---:|:---:|:---:|---|
| RSS feeds (3 publishers) | RSS feed | yes | native | no | volume and freshness |
| NewsData.io | REST API | yes | native | no | structured news |
| FakeNewsNet | GitHub repository | yes | via Open Graph | yes | academic ground truth |
| Fakeddit | Kaggle dataset | yes | native | yes | annotated multimodal volume |

On a real pipeline run: **205 publications collected** from the four sources, of which
**143 kept** after cleaning and checking the text-image pairing, and **97% of the requested
images actually obtained**. The dropped publications almost all go for a single, expected
reason: no usable image — mostly FakeNewsNet articles whose URL, dated 2016-2018, no longer
answers.

Split by access method: 97 publications through RSS feeds, 29 from the Kaggle dataset, 10
from the API and 7 from the GitHub repository. The imbalance is deliberate: the feeds
supply the daily volume, the datasets bring the labels.

---

## References

- Shu, K., Mahudeswaran, D., Wang, S., Lee, D., Liu, H. (2018). *FakeNewsNet: A Data
  Repository with News Content, Social Context and Dynamic Information for Studying Fake
  News on Social Media*. arXiv:1809.01286 —
  <https://github.com/KaiDMML/FakeNewsNet>
- Nakamura, K., Levy, S., Wang, W. Y. (2020). *Fakeddit: A New Multimodal Benchmark
  Dataset for Fine-grained Fake News Detection*. LREC 2020 —
  <https://github.com/entitize/Fakeddit>
- Zidan, M., Sleem, A., Nabil, A. *et al.* (2025). *Multimodal Fake News Detection: A
  Survey of Text and Visual Content Integration Methods*. International Journal of
  Computers and Information, vol. 7, p. 13-25.
- The Open Graph protocol — <https://ogp.me/>
- NewsData.io — <https://newsdata.io/>
