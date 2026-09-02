# Monitoring plan for the ETL pipeline

How the pipeline is watched in production.

This plan describes how the multimodal extraction pipeline is monitored: which indicators,
from which thresholds we start worrying, what the pipeline does when things go wrong, and
how often we check.

## 1. What we are trying to avoid

The detector's performance depends directly on the quality of the dataset feeding it. The
risk is not the outright breakdown — that one is visible — but **silent degradation**: an
RSS feed that changes format and stops returning images, an expired API key, a dataset
that ends up fed by a single source. The pipeline keeps running, the tasks stay green, and
the model is trained on data that is no longer worth anything.

Monitoring exists to make that degradation visible.

## 2. Indicators tracked

Every indicator listed here is computed by `src/multimodal_etl/kpi.py` and displayed by the
dashboard. None is decorative: each one triggers an action when it drifts.

| Indicator | What it measures | What it reveals when it drifts |
|---|---|---|
| **Validity rate** | share of collected publications that pass the checks | a source has changed format |
| **Text-image pairing** | share of kept publications whose image is on disk | the dataset is losing its multimodal nature |
| **Images downloaded** | share of image URLs that yielded a real file | the media are becoming unreachable (CDN, 403) |
| **Volume ingested** | number of publications produced per run | a source has gone silent |
| **Share of the dominant source** | concentration of the dataset | the dataset inherits one publisher's editorial bias |
| **Median age** | how old the ingested publications are | the feed has frozen, we are re-ingesting the past |
| **Duplicate rate** | share of publications dropped as duplicates | over-ingestion, or an identifier that has become unstable |
| **Total duration** | execution time of the pipeline | the daily window is about to be exceeded |
| **Failed sources** | connectors silent or in error | an incident reaching a source |
| **API calls spent** | NewsData.io quota used | external cost, risk of exhausting the quota |
| **Image weight** | disk taken up by the media | storage cost |
| **What the run adds** | share of publications genuinely new in the database | the pipeline is spinning and re-ingesting the same contents |

## 3. Alert thresholds

| Indicator | Normal | Warning | Critical |
|---|---|---|---|
| Validity rate | ≥ 60% | 45 – 60% | < 45% |
| Text-image pairing | ≥ 90% | 75 – 90% | < 75% |
| Images downloaded | ≥ 80% | 60 – 80% | < 60% |
| Volume ingested | ≥ 80 | 40 – 80 | < 40 |
| Share of the dominant source | ≤ 50% | 50 – 70% | > 70% |
| Median age | ≤ 48 h | 48 h – 7 d | > 7 d |
| Duplicate rate | ≤ 5% | 5 – 15% | > 15% |
| Total duration | ≤ 90 s | 90 – 300 s | > 300 s |
| Failed sources | 0 | 1 | ≥ 2 |

> These thresholds are not copied by hand into this document: they are defined **once**, in
> the `THRESHOLDS` dictionary of `src/multimodal_etl/kpi.py`, each with its rationale. The
> dashboard reads them from the same place — so the document and the application cannot
> contradict each other.

A word on the **validity rate**, whose threshold may surprise: it sits around 65%, and that
is its normal behaviour. A rejection almost always comes from an unavailable image — the
FakeNewsNet URLs date from 2016-2018 and a good share of them no longer answer. A threshold
set at 85% would have kept the indicator permanently red, and an always-red indicator stops
being read by anyone. So it is calibrated on the measured behaviour, which is what lets it
signal a real break.

Crossing into **amber** produces a `WARNING` log and a non-blocking notification. Crossing
into **red** produces an `ERROR` log and an immediate alert; depending on the indicator,
the load is suspended rather than polluting the database.

One useful clarification: a source that is **deliberately turned off** is not a failed
source. NewsData.io only runs when an API key is supplied; its absence is a configuration
choice, not an incident, and the pipeline raises no alert for it.

## 4. Error handling

The pipeline is built to keep running degraded rather than to stop.

- **Source isolation.** Each connector is wrapped in a `try/except`: a source that is down
  is logged and counted, it does not interrupt the others.
- **Timeouts.** Every HTTP request has a configurable maximum delay — a server that stops
  answering does not block the run.
- **Media validation.** An image is opened by Pillow before being kept; an unreadable file
  is deleted rather than entering the dataset.
- **Airflow retries.** Each task is configured with `retries=1` and a 2-minute delay, which
  absorbs transient network incidents.
- **Replaying a single task.** The steps hand their results to each other through files; any
  task can be replayed on its own, and falls back to the last archived artefact when the
  working file has been cleared.
- **Incremental load.** Only the publications that are absent get added: replaying a run
  never creates a duplicate and never overwrites the history.
- **Central logging.** Every event is written to `logs/` with its level, timestamp and
  originating module, both to the console and to a file.

## 5. How often we check

| Check | Frequency | Means |
|---|---|---|
| DAG run | daily (`schedule="@daily"`) | the Airflow scheduler |
| KPI review | after every run | the Streamlit dashboard |
| Error log review | daily | `logs/multimodal_etl.log` and the Airflow logs |
| API quota tracking | weekly | the "API calls spent" KPI |
| Trend review | weekly | the dashboard's run history |
| Data drift audit | monthly | comparison of distributions (§6) |

## 6. Drift detection

Beyond the instantaneous thresholds, we watch how the distributions **evolve** over time:
spread of languages, of sources, text length, share of images. An isolated value reads
poorly; a validity rate of 80% does not mean the same thing depending on whether it is
climbing or falling. That is the job of the run history, fed by one JSON record per run
under `data/processed/runs/`.

To go further, **Evidently** produces automated drift reports and plugs straight into the
history of datasets under `data/processed/`.

## 7. Alerting

- **Channels**: e-mail and webhook (Slack or Teams) on a red threshold. Airflow natively
  provides `on_failure_callback` and e-mail notifications.
- **Contents of an alert**: DAG and task name, timestamp, indicator at fault, observed
  value against the threshold, link to the task logs.

## 8. Database security

- **Authentication**: no hard-coded secret. Credentials travel through environment
  variables (`MULTIMODAL_ETL_DB_URL`), and through a secret manager in production.
- **Roles**: an application account limited to read/write on the pipeline's tables,
  separate from the administrator account.
- **Encryption**: TLS for connections, encryption at rest — offered by default on managed
  PostgreSQL.
- **SQL injection**: the queries that build a table name validate it against the schema's
  table list before executing; no name can come from outside input.
- **Traceability**: the `ingested_at` field and the run history make it possible to know
  when, and through which run, every row entered the database.

## 9. Industrialisation: beyond the development machine

The pipeline currently runs on a single workstation, with Airflow in Docker and a SQLite
database. Scaling up does not call its design into question — the steps are already
decoupled and communicate through files — but it does change the infrastructure running it.

**On a managed data platform (Databricks).** This is the most direct target: the same
Python functions become the tasks of a Databricks *Job*, storage moves from `data/` to
object storage, and the target database becomes a Delta table. What we gain is elastic
compute, data versioning and a catalogue. The transposition is light: the business logic
does not move, only the execution layer changes.

**On Kubernetes.** The alternative when the infrastructure is already there and we want to
stay in control of the environment. Airflow deploys with the `KubernetesExecutor`: each
task runs in its own pod, isolated and sized to its need — extraction is bound by the
network, transformation by the CPU. The working area then moves from a local folder to a
shared volume or to object storage.

In both cases, two points need reworking: **image storage**, which has to move to object
storage rather than the local disk, and the **parallelisation of the extraction**, today
sequential source by source, which starts paying off as soon as the number of sources
grows.
