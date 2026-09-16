# Running the orchestration, and what a real run left behind

How to start Apache Airflow locally and run the `multimodal_etl` DAG, followed by the captured
output of the run of 2026-09-15, the one every figure in this repository is dated from.

The DAG reuses exactly the functions of the `multimodal_etl` package: the business logic is
covered by the test suite and by `scripts/run_etl.py`, and Airflow adds the orchestration,
scheduling and retry layer on top. `docs/architecture.md` says why the DAG holds no logic of
its own.

## Prerequisites

- Docker Desktop installed and running: Docker ≥ 24, Compose v2.
- **The project has to sit on a local disk.** Docker cannot mount a folder located on a virtual
  sync drive such as Google Drive or OneDrive: the mounts are created empty, with no error, and
  the DAG is never discovered. If the project is stored on such a drive, clone or copy it into a
  local folder such as `C:\dev\multimodal_etl`, and start Airflow from that copy.

> **Copy the whole tree, `pyproject.toml` included.** Without that one file in the mount, the
> package used to settle on `/opt/airflow` as the root, write everything a level too high, and
> report five green tasks while doing it. `MULTIMODAL_ETL_ROOT` is set in the compose file for
> exactly this reason.

## Prepare the configuration

```powershell
Copy-Item infra/.env.example infra/.env
```

Then fill in `infra/.env`:

- `AIRFLOW_UID`: `0` on Windows, the output of `id -u` on Linux and macOS. Without it, the
  container cannot write into `data/`.
- `NEWSDATA_API_KEY`: optional, the same key as in the project's `.env`. Without a key the
  NewsData.io source turns itself off cleanly and the other three carry on.

## Build the image and start

```powershell
docker compose -f infra/docker-compose.airflow.yaml build
docker compose -f infra/docker-compose.airflow.yaml up -d
docker compose -f infra/docker-compose.airflow.yaml ps
```

The image is built once from `infra/Dockerfile`: it installs the pipeline's dependencies while
honouring Airflow's official constraints file. `_PIP_ADDITIONAL_REQUIREMENTS` is deliberately
not used: the installation would be redone on every restart, and pip would replace libraries
Airflow itself depends on.

## Check that the DAG is loaded

```powershell
docker compose -f infra/docker-compose.airflow.yaml exec airflow-scheduler airflow dags list
docker compose -f infra/docker-compose.airflow.yaml exec airflow-scheduler airflow dags list-import-errors
```

The first has to display `multimodal_etl`, the second has to return nothing.

```
dag_id         | fileloc                                 | owners         | is_paused
===============+=========================================+================+==========
multimodal_etl | /opt/airflow/dags/multimodal_etl_dag.py | multimodal_etl | True
```

## From the web interface

1. Open <http://localhost:8080>, credentials `airflow` / `airflow`, which are fit for a local
   run and nothing else.
2. Enable the **`multimodal_etl`** DAG, then click **Trigger DAG**.
3. Open the **Graph** view and select the run in the grid on the left: the five tasks chain as
   `extract → transform → load → metrics → cleanup`.

<!-- source: docs/images/MANIFEST.json -->
![The Airflow graph view after the run of 2026-09-15, with the five tasks chained left to right and each one reporting success under its operator name](images/airflow_graph.png)

## From the command line

Run the whole DAG:

```powershell
docker compose -f infra/docker-compose.airflow.yaml exec airflow-scheduler `
  airflow dags test multimodal_etl 2026-09-15
```

Replay **a single task**, to check it really is independent of the others:

```powershell
docker compose -f infra/docker-compose.airflow.yaml exec airflow-scheduler `
  airflow tasks test multimodal_etl transform 2026-09-15
```

## What a run produces

- a raw JSON under `data/raw/`, and the images under `data/raw/images/`;
- a dataset and its statistics under `data/processed/`;
- the populated tables in `data/db/multimodal_etl.db`, or in the `MULTIMODAL_ETL_DB_URL`
  database;
- a run record under `data/processed/runs/`, read by the dashboard;
- an **empty** working area `data/interim/`, the `cleanup` task having purged it.

## Stop

```powershell
docker compose -f infra/docker-compose.airflow.yaml down
# To remove everything, metadata database and logs included:
# docker compose -f infra/docker-compose.airflow.yaml down -v
```

## When something goes wrong

| Symptom | Likely cause | Fix |
|---|---|---|
| `airflow dags list` returns nothing | the mounted `dags/` folder is empty | the project is on a virtual drive: work from a local copy |
| The scheduler restarts in a loop | write permissions on the logs or on `data/` | check `AIRFLOW_UID` in `infra/.env` |
| `MappedAnnotationError` at startup | a dependency overwrote Airflow's SQLAlchemy version | rebuild the image: it installs under the official constraints |
| A task fails on one source | network incident or missing API key | read the task log; the other sources carried on |
| A run writes outside the project | `MULTIMODAL_ETL_ROOT` unset and `pyproject.toml` missing from the mount | copy the whole tree, and keep the variable in the compose file |

---

# The run of 2026-09-15

Apache Airflow 2.10.4 on the `LocalExecutor`, PostgreSQL metadata database, the image built
from `infra/Dockerfile`, an empty pipeline database at the start, and no NewsData.io key.

These are **captures**. The progress lines Airflow prints are kept, the debug lines and the
timestamps are dropped, and nothing is rewritten by hand: the file is regenerated by running
the DAG again.

## A full run, on an empty database

```
$ airflow dags test multimodal_etl 2026-09-15
```

```
multimodal_etl.pipeline   | === STEP 1 — EXTRACT ===
multimodal_etl.extract    | Extract: source 'rss' -> 99 publications (ok)
multimodal_etl.extract    | Extract: source 'newsdata' -> 0 publications (disabled)
multimodal_etl.opengraph  | Open Graph: 14 images recovered across 40 articles visited
multimodal_etl.extract    | Extract: source 'fakenewsnet' -> 48 publications (ok)
multimodal_etl.extract    | Extract: source 'kaggle_fakeddit' -> 24 publications (ok)
multimodal_etl.extract    | Extract: 171 raw publications in total
multimodal_etl.images     | Images: 120 downloaded, 16 failures, 35 skipped (5.3 MB on disk)
multimodal_etl.transit    | Working area: 'extraction.json' staged for the next step
Marking task as SUCCESS. task_id=extract

multimodal_etl.pipeline   | === STEP 2 — TRANSFORM ===
multimodal_etl.transform  | Transform: 118/171 publications valid after cleaning
multimodal_etl.transform  | Transform: 0 duplicates removed
multimodal_etl.transit    | Working area: 'dataset.parquet' staged for the next step
Marking task as SUCCESS. task_id=transform

multimodal_etl.pipeline   | === STEP 3 — LOAD ===
multimodal_etl.load       | Load: connecting to the database (sqlite:////opt/airflow/project/data/db/multimodal_etl.db)
multimodal_etl.load       | Load: 118 rows added to 'publication'
multimodal_etl.load       | Load: 5 rows added to 'source'
multimodal_etl.load       | Load: 118 rows added to 'text_content'
multimodal_etl.load       | Load: 118 rows added to 'image_content'
multimodal_etl.load       | Load: 19 rows added to 'label'
multimodal_etl.load       | Load: 118 rows added to 'publications'
multimodal_etl.load       | Load: 118 new publications, 0 already present
Marking task as SUCCESS. task_id=load

multimodal_etl.pipeline   | === STEP 4 — METRICS ===
multimodal_etl.pipeline   | Metrics: run record written to data/processed/runs/run_20260915_111445.json
Marking task as SUCCESS. task_id=metrics

multimodal_etl.pipeline   | === STEP 5 — CLEANUP ===
multimodal_etl.transit    | Working area: 5 temporary files deleted
Marking task as SUCCESS. task_id=cleanup

DagRun Finished: dag_id=multimodal_etl, run_id=manual__2026-09-15T00:00:00+00:00, state=success
```

All five tasks are `SUCCESS` and the `DagRun` ends `state=success`. Three of the four sources
contributed; the fourth reports `disabled` and not a failure, because no NewsData.io key was
supplied. That is a configuration choice, and the failed-sources indicator stays at zero.

Of the 171 publications collected, 118 survived. The 53 that did not had no image file behind
them, which is the one condition a row has to meet here.

## The same DAG again, immediately afterwards

```
$ airflow dags test multimodal_etl 2026-09-15
```

```
multimodal_etl.extract    | Extract: source 'rss' -> 99 publications (ok)
multimodal_etl.extract    | Extract: source 'newsdata' -> 0 publications (disabled)
multimodal_etl.extract    | Extract: source 'fakenewsnet' -> 48 publications (ok)
multimodal_etl.extract    | Extract: source 'kaggle_fakeddit' -> 24 publications (ok)
multimodal_etl.extract    | Extract: 171 raw publications in total
multimodal_etl.images     | Images: 129 downloaded, 7 failures, 35 skipped (9.1 MB on disk)
multimodal_etl.transform  | Transform: 127/171 publications valid after cleaning
multimodal_etl.transform  | Transform: 0 duplicates removed
multimodal_etl.load       | Load: 9 rows added to 'publication'
multimodal_etl.load       | Load: table 'source' already up to date
multimodal_etl.load       | Load: 9 rows added to 'text_content'
multimodal_etl.load       | Load: 9 rows added to 'image_content'
multimodal_etl.load       | Load: 9 rows added to 'label'
multimodal_etl.load       | Load: 9 rows added to 'publications'
multimodal_etl.load       | Load: 9 new publications, 118 already present
DagRun Finished: state=success
```

The same 171 raw publications, and 127 kept where the first run kept 118: nine images that had
failed to download the first time succeeded the second. **Of the 127 the run kept, 118 were
already in the database and 9 were new.** The `source` table did not move, the same five
sources, and nothing was written twice.

**Where the guarantee lives.** Not in that loop: `docs/DB.md` gives the six keys that carry it,
and `docs/architecture.md` says why the loader was rewritten to stop asking the database what it
already held.

The nine extra rows are also the honest answer to what a second run adds: on a live corpus, not
nothing. `tests/system/test_pipeline_end_to_end.py` runs the same chain against a feed it serves
itself, where the corpus does not move, and there the second run adds exactly zero.

## One task replayed on its own

This is the point that justifies the orchestration. The working area has just been emptied by
`cleanup`, so `transform` no longer has its input file.

```
$ airflow tasks test multimodal_etl transform 2026-09-15
```

```
airflow.task              | Executing <Task(PythonOperator): transform> on 2026-09-15
multimodal_etl.pipeline   | === STEP 2 — TRANSFORM ===
multimodal_etl.transit    | Working area: 'extraction.json' missing, falling back to archive raw_publications_20260915_112320.json
multimodal_etl.transform  | Transform: 171 raw publications read
multimodal_etl.transform  | Transform: 127/171 publications valid after cleaning
multimodal_etl.transform  | Transform: dataset of 127 rows exported to data/processed/publications_20260915_112330.parquet
multimodal_etl.transit    | Working area: 'dataset.parquet' staged for the next step
Marking task as SUCCESS. task_id=transform
```

The task noticed its working file was gone, fell back to the last archived extraction, and
finished — **without replaying the extraction**, which takes a minute and spends an API call.

That dataset of 127 rows is the one `reports/data_quality.json` was measured on.

## Credentials

The `airflow` / `airflow` pair in the compose file is fit for a local run and nothing else.
`docs/DB.md` says what a deployment does instead about the pipeline's own database.
