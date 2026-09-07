# Runbook — running the `multimodal_etl` DAG with Airflow

This guide walks step by step through starting the orchestration locally with Apache
Airflow, and through producing the DAG's run logs.

The DAG reuses exactly the functions of the `multimodal_etl` package: the business logic is
already covered by the unit tests and by `scripts/run_etl.py`. Airflow only adds the
orchestration, scheduling and retry layer.

## 1. Prerequisites

- Docker Desktop installed and running (Docker ≥ 24, Compose v2).
- **The project has to sit on a local disk.** Docker cannot mount a folder located on a
  virtual sync drive (Google Drive, OneDrive): the mounts are created empty, with no error,
  and the DAG is never discovered. If the project is stored on such a drive, copy or clone
  it into a local folder (`C:\dev\multimodal_etl`, say) and start Airflow from that copy.

## 2. Prepare the configuration

```powershell
Copy-Item docker/.env.example docker/.env
```

Then fill in `docker/.env`:

- `AIRFLOW_UID` — `0` on Windows, the output of `id -u` on Linux and macOS. Without it, the
  container cannot write into `data/`.
- `NEWSDATA_API_KEY` — optional, the same key as in the project's `.env`. Without a key the
  NewsData.io source turns itself off cleanly and the other three carry on.

## 3. Build the image and start

```powershell
docker compose -f docker/docker-compose.airflow.yaml build
docker compose -f docker/docker-compose.airflow.yaml up -d
```

The image is built once from `docker/Dockerfile`: it installs the pipeline's dependencies
while honouring Airflow's official constraints file. We do not use
`_PIP_ADDITIONAL_REQUIREMENTS` — the installation would be redone on every restart, and pip
would replace libraries Airflow itself depends on.

Check that the services are healthy:

```powershell
docker compose -f docker/docker-compose.airflow.yaml ps
```

## 4. Check that the DAG is loaded

```powershell
docker compose -f docker/docker-compose.airflow.yaml exec airflow-scheduler airflow dags list
docker compose -f docker/docker-compose.airflow.yaml exec airflow-scheduler airflow dags list-import-errors
```

The first command has to display `multimodal_etl`, the second has to return nothing.

## 5. From the web interface

1. Open <http://localhost:8080> — credentials `airflow` / `airflow`.
2. Enable the **`multimodal_etl`** DAG, then click **Trigger DAG**.
3. Open the **Graph** view: the five tasks chain as
   `extract → transform → load → metrics → cleanup` and turn green.

Screenshots worth taking:

- the **Graph** view with the five tasks successful;
- the **Grid** view showing a complete run;
- the **log** of the `load` task, where the line `Load: N new publications` appears.

## 6. From the command line (reproducible evidence)

Run the whole DAG:

```powershell
docker compose -f docker/docker-compose.airflow.yaml exec airflow-scheduler `
  airflow dags test multimodal_etl 2026-08-20
```

Replay **a single task**, to check it really is independent of the others:

```powershell
docker compose -f docker/docker-compose.airflow.yaml exec airflow-scheduler `
  airflow tasks test multimodal_etl transform 2026-08-20
```

The output of both commands is archived in `docs/airflow_run_evidence.md`.

## 7. What a run produces

- a raw JSON under `data/raw/`, and the images under `data/raw/images/`;
- a dataset and its statistics under `data/processed/`;
- the populated tables in `data/db/multimodal_etl.db`, or in the `MULTIMODAL_ETL_DB_URL`
  database;
- a run record under `data/processed/runs/`, read by the dashboard;
- an **empty** working area `data/interim/`, the `cleanup` task having purged it.

## 8. Stop

```powershell
docker compose -f docker/docker-compose.airflow.yaml down
# To remove everything, metadata database and logs included:
# docker compose -f docker/docker-compose.airflow.yaml down -v
```

## 9. When something goes wrong

| Symptom | Likely cause | Fix |
|---|---|---|
| `airflow dags list` returns nothing | the mounted `dags/` folder is empty | the project is on a virtual drive: work from a local copy (§1) |
| The scheduler restarts in a loop | write permissions on the logs or on `data/` | check `AIRFLOW_UID` in `docker/.env` |
| `MappedAnnotationError` at startup | a dependency overwrote Airflow's SQLAlchemy version | rebuild the image: it installs under the official constraints |
| A task fails on one source | network incident or missing API key | read the task log; the other sources carried on |

## 10. Database security

The `airflow` / `airflow` credentials in the compose file are only fit for a local run. In
production: secrets managed outside the repository, an application role limited to the
pipeline's tables, TLS on connections and encryption at rest — see §8 of the monitoring
plan.
