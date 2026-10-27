# Running the orchestration, and what a real run left behind

How to start Apache Airflow locally and run the `multimodal_etl` DAG, followed by excerpts of the
output of the runs of 2026-09-15, from which the published figures of this repository come.

The DAG calls the functions of the `multimodal_etl` package, which the test suite and
`scripts/run_etl.py` also exercise, and Airflow adds orchestration, scheduling and retries on
top. `docs/architecture.md` explains why the DAG holds no logic of its own.

## Prerequisites

- Docker Desktop installed and running: Docker ≥ 24, Compose v2.
- **The project has to sit on a local disk.** Docker cannot mount a folder located on a virtual
  sync drive such as Google Drive or OneDrive. The mounts are created empty, with no error, and
  the DAG is never discovered. If the project is stored on such a drive, clone or copy it into a
  local folder such as `C:\dev\multimodal_etl`, and start Airflow from that copy.

> **Copy the whole tree, `pyproject.toml` included.** Without that file in the mount, the
> package used to take `/opt/airflow` as the project root, write everything one level too high,
> and report five successful tasks while doing so. The compose file sets `MULTIMODAL_ETL_ROOT`
> to prevent this.

## Prepare the configuration

```powershell
Copy-Item infra/.env.example infra/.env
```

Then fill in `infra/.env`:

- `AIRFLOW_UID`: `0` on Windows, the output of `id -u` on Linux and macOS. Without it, the
  container cannot write into `data/`.
- `NEWSDATA_API_KEY`: optional, the same key as in the project's `.env`. Without a key, the
  NewsData.io source turns itself off and the other three sources run as usual.

## Build the image and start

```powershell
docker compose -f infra/docker-compose.airflow.yaml build
docker compose -f infra/docker-compose.airflow.yaml up -d
docker compose -f infra/docker-compose.airflow.yaml ps
```

The image is built once from `infra/Dockerfile`, which installs the pipeline's dependencies under
Airflow's official constraints file. `_PIP_ADDITIONAL_REQUIREMENTS` is deliberately left unused,
because it would repeat the installation at every restart, and pip could replace libraries that
Airflow itself depends on.

## Check that the DAG is loaded

```powershell
docker compose -f infra/docker-compose.airflow.yaml exec airflow-scheduler airflow dags list
docker compose -f infra/docker-compose.airflow.yaml exec airflow-scheduler airflow dags list-import-errors
```

The first command has to list `multimodal_etl`, and the second has to report no import error.

```
dag_id         | fileloc                                 | owners         | is_paused
===============+=========================================+================+==========
multimodal_etl | /opt/airflow/dags/multimodal_etl_dag.py | multimodal_etl | True
```

## From the web interface

1. Open <http://localhost:8080> and sign in with `airflow` / `airflow`, credentials suitable for
   a local run only.
2. Enable the **`multimodal_etl`** DAG, then click **Trigger DAG**.
3. Open the **Graph** view and select the run in the grid on the left. The five tasks are chained
   as `extract → transform → load → metrics → cleanup`.

<!-- source: docs/images/MANIFEST.json -->
![The Airflow graph view after the run of 2026-09-15, with the five tasks chained left to right and each one marked success above its operator name](images/airflow_graph.png)

## From the command line

Run the whole DAG:

```powershell
docker compose -f infra/docker-compose.airflow.yaml exec airflow-scheduler `
  airflow dags test multimodal_etl 2026-09-15
```

Replay a single task, to check that it runs independently of the others:

```powershell
docker compose -f infra/docker-compose.airflow.yaml exec airflow-scheduler `
  airflow tasks test multimodal_etl transform 2026-09-15
```

## What a run produces

- a raw JSON file under `data/raw/`, and the images under `data/raw/images/`;
- a dataset and its statistics under `data/processed/`;
- the populated tables in `data/db/multimodal_etl.db`, or in the database given by
  `MULTIMODAL_ETL_DB_URL`;
- a run record under `data/processed/runs/`, which the dashboard reads;
- an empty working area, `data/interim/`, which the `cleanup` task has purged.

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
| A source brings back no publication | network incident, or no NewsData.io key | read the extract task's log; the other sources still ran |
| A run writes outside the project | `MULTIMODAL_ETL_ROOT` unset and `pyproject.toml` missing from the mount | copy the whole tree, and keep the variable in the compose file |

---

# The recorded runs

Apache Airflow 2.10.4 on the `LocalExecutor`, a PostgreSQL metadata database, the image built
from `infra/Dockerfile`, an empty pipeline database at the start, and no NewsData.io key.

The blocks below are excerpts of the console output. They keep a selection of the pipeline's
progress lines and of Airflow's task results, without timestamps, log levels or debug lines, and
the second run shows fewer lines than the first. The logger names are aligned and one of them is
shortened, and file paths are shown relative to the project root, except in the database URL
the load step prints.

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

All five tasks end in `SUCCESS`, and the `DagRun` ends with `state=success`. Three of the four
sources contributed. The fourth reports `disabled`, because no NewsData.io key was supplied, so
the failed-sources indicator stays at zero. With no Kaggle export in `data/raw/kaggle/`, Fakeddit
came from the 24 rows of the synthetic sample.

Of the 171 publications collected, 118 were kept. Of the 53 dropped at the transform step, 51 had
no image file: 16 image downloads failed, and 35 publications had no usable image URL. The other
2 had an image but failed the title or text-length check, which requires a title and at least
30 characters of text.

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

The second run collected 171 publications again, with the same count per source, and kept 127
where the first run kept 118. The difference comes from images: nine downloads that failed the
first time succeeded in the second run, as the failures fell from 16 to 7 and the downloads rose
from 120 to 129. Of the 127 publications kept, 118 were already in the database and 9 were new.
The `source` table did not change, since the same five sources were present, and no row was
written twice.

The database schema enforces this. `docs/DB.md` gives the six primary keys involved, and
`docs/architecture.md` explains why the loader was rewritten so that it no longer asks the
database which rows it already holds.

The nine extra rows also show that a second run on a live corpus can add rows.
`tests/system/test_pipeline_end_to_end.py` runs the same five steps through
`scripts/run_etl.py` against a feed that the test serves itself, so the corpus stays the same,
and there the second run adds exactly zero rows.

## One task replayed on its own

The `cleanup` task has just emptied the working area, so `transform` no longer finds its input
file there.

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

The task found its working file missing, read the last archived extraction instead, and finished
without running the extraction again, which would have repeated every image download, plus one
NewsData.io call with a key configured.

`reports/data_quality.json` was measured on this dataset of 127 rows.

## Credentials

The pipeline takes one credential from outside, and it is optional.

| Variable | Issuer | Getting one | Where to put it |
|---|---|---|---|
| `NEWSDATA_API_KEY` | NewsData.io | register at [newsdata.io/register](https://newsdata.io/register); the key is on the account's dashboard | `.env` at the root for `scripts/run_etl.py`, and `infra/.env` for Airflow |

Without it, the NewsData.io source turns itself off and the three other sources run, so a
demonstration works without a key. NewsData.io does not delete a key. It regenerates it from the
same dashboard, and regenerating is how a key that has been exposed is retired.

The `airflow` / `airflow` pair in the compose file is suitable for a local run only.
`docs/DB.md` describes how a deployment would handle the credentials of the pipeline's own
database.
