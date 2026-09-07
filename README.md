# Multimodal ETL

An ETL pipeline that collects **text-and-image publications** from four sources, cleans
them into a typed dataset, loads them into a relational database, and reports on itself.
Orchestrated by Apache Airflow, watched by a KPI dashboard.

The rule that defines the dataset: **no image on disk, no publication**. A URL is not an
image, so every image is downloaded and opened by Pillow before the publication is kept.

![The KPI dashboard after a run](docs/img/dashboard.png)

## Project status

**Deliberately finished.** This is a lab project: it was built to work end to end, it was
then audited, and the defects the audit found were fixed. It is not maintained beyond
that, and its CI does not run on a schedule.

What that means concretely:

- the pipeline runs today, against live sources, with one command;
- the figures below come from a real run and are dated, because the sources are live news
  feeds — the same command tomorrow returns different numbers, and that is the point;
- three architectural promises are **not yet proven**, and are listed under *What this does
  not prove*. The design and plan for proving them are written but not executed.

## What one run does

Four sources, four access methods:

| Source | Access | What it brings |
|---|---|---|
| RSS feeds (The Guardian, BBC, ABC News) | `rss_feed` | volume and freshness |
| NewsData.io API | `rest_api` | structured news |
| FakeNewsNet | `github_download` | academic ground truth |
| Fakeddit | `kaggle_download` | annotated multimodal volume |

The FakeNewsNet CSVs carry no image, so the pipeline recovers one from the article's Open
Graph metadata. Publications without a usable image are dropped at the transform step.

**One run, 2026-09-03** — no NewsData key, so that source turned itself off cleanly:

| | |
|---|---|
| Publications collected | 164 (RSS 92, FakeNewsNet 48, Fakeddit 24) |
| Kept after cleaning | 122 — the 42 dropped had no usable image |
| Text-image pairing | 100% |
| Images obtained | 124 of 129 attempted |
| of which recovered from Open Graph | 8 |
| Labelled with ground truth | 31 |
| Total duration | 56.9 s |

**The load is incremental.** Running it twice in a row, back to back:

| Run | Collected | New in database | Total in database |
|---|---|---|---|
| first | 164 | 112 | 112 |
| second | 164 | **12** | 124 |

The second run collected the same 164 publications and wrote 12 — the articles the feeds
had published in between. Nothing was duplicated.

![The dataset the pipeline produces](docs/img/dataset_sample.png)

## What the audit found

The repository was audited before publication. Three findings were worth the trouble.

**The load step could not run.** `pipeline.py` imported `load.etape_chargement` and then
defined a function of the same name. In Python the definition rebinds the module-level
name, so the inner call resolved to the pipeline's own function, which takes one argument
instead of two:

```
TypeError: run_load() takes from 0 to 1 positional arguments but 2 were given
```

**The third task of the Airflow DAG could not complete**, and no test covered that path —
the 82 existing tests exercised the modules in isolation, never the pipeline step that
chains them. The database looked healthy because it had been filled before the shadowing
was introduced. The loader is now called `load_dataset`, which says what it does and no
longer collides, and a regression test covers the path.

*Transferable lesson: a populated database does not prove a pipeline works.*

**A copy of the whole repository was committed inside itself.** A 72-file archive built for
submission, purged from the full history. The repository dropped to 491 KiB.

**The code was French and the documentation English.** 34 Python files out of 35 had French
docstrings, and the run records, the statistics files and three SQL tables used French
keys. All of it is now English — which is how the stale task names in the runbook came to
light: it still told the reader to run `airflow tasks test multimodal_etl transformation`,
a task that had been renamed to `transform`.

## What this does not prove

The DAG's documentation makes four promises. One is demonstrated, three are not.

**Demonstrated — the tasks are independent.** `docs/airflow_run_evidence.md` shows a single
task replayed on its own, falling back to the last archived artefact after the working area
had been cleared, and succeeding without replaying the extraction.

**Not proven — idempotency is a property of the code, not of the schema.** The load reads
the existing keys, then writes the rows it did not find. There is no unique constraint in
the database, so two concurrent runs, or a crash between the read and the write, would
insert duplicates. The table above shows the mechanism working; it does not show it holding
under concurrency, because it would not.

**Not proven — the deduplication key is fragile.** The identifier hashes the exact URL and
the exact title. A fixed typo, or a `utm_source` parameter, produces a different identifier
for the same article. How many real duplicates that lets through has not been measured.

**Not proven — surviving a failing source.** Each connector is wrapped in its own
`try/except` and failures are counted, but no test simulates a source that is down.

**The volume tests none of this.** A few hundred publications reveal neither the memory
behaviour, nor the races, nor the collisions. The pipeline demonstrates an architecture,
not its resistance at scale.

The design and implementation plan for closing the three open points are written.

## Structure

```
├── src/multimodal_etl/
│   ├── config.py           # paths and parameters, as frozen dataclasses
│   ├── schema.py           # the publication schema — single source of truth
│   ├── sources/            # one module per source + the Open Graph enrichment
│   ├── images.py           # download and validation of the images
│   ├── extract.py          # step E: collect -> raw JSON + image files
│   ├── transform.py        # step T: clean, validate, normalise
│   ├── load.py             # step L: incremental relational load
│   ├── transit.py          # working area between steps (task independence)
│   ├── pipeline.py         # the 5 steps, called by the scripts AND by the DAG
│   └── kpi.py              # indicators and alert thresholds
├── dags/                   # the Airflow DAG — calls pipeline.py, holds no logic
├── docker/                 # image and compose file for a local Airflow
├── dashboard/              # the Streamlit application
├── notebooks/              # the steps, walked through one at a time
├── docs/                   # sources, schema, monitoring, run evidence
└── tests/                  # 83 tests
```

The schema is generated from one place: `schema.py` describes every field, and the diagram,
the data dictionary and the table split are all derived from it. A field added to the code
appears everywhere else on its own.

## Running it

```powershell
uv sync --extra dev
uv run python scripts/run_etl.py            # the whole pipeline, one command
uv run streamlit run dashboard/app.py       # the KPI dashboard
```

No key is needed: the pipeline runs on the RSS feeds and a versioned Fakeddit sample.
A NewsData.io key turns on the fourth source; without one it disables itself and the run
carries on. Each step also runs on its own:

```powershell
uv run python scripts/run_extract.py
uv run python scripts/run_transform.py
uv run python scripts/run_load.py
```

A step replayed on its own falls back to the last archived artefact when the previous
step's working file has been cleared.

Airflow, locally — the full walkthrough is in `docs/airflow_runbook.md`:

```powershell
docker compose -f docker/docker-compose.airflow.yaml build
docker compose -f docker/docker-compose.airflow.yaml up -d
# http://localhost:8080, DAG: multimodal_etl
```

## Documentation

| Document | What it answers |
|---|---|
| [`docs/source_exploration.md`](docs/source_exploration.md) | Why these four sources, and why no scraping |
| [`docs/data_schema.md`](docs/data_schema.md) | The conceptual model and every field's role |
| [`docs/monitoring_plan.md`](docs/monitoring_plan.md) | Which indicators, which thresholds, and what happens when one is crossed |
| [`docs/airflow_runbook.md`](docs/airflow_runbook.md) | Running the orchestration yourself |
| [`docs/airflow_run_evidence.md`](docs/airflow_run_evidence.md) | The captured logs of a real DAG run |

## Quality

```powershell
uv run python -m pytest      # 83 tests
uv run ruff check .
uv run bandit -c pyproject.toml -r src
```

The thresholds in the monitoring plan are not copied by hand: they live in
`multimodal_etl.kpi.THRESHOLDS`, and a test asserts the document names every one of them.
The same goes for the schema — a test asserts the data dictionary and the diagram cover
every field.

## Licence

MIT
