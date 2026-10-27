# What is measured, and what is done about it

The indicators this repository publishes about its runs, how each one is computed, the bound it
is read against, and what happens when that bound is crossed. `metrics.yaml` describes the same
nine indicators in machine-readable form, with the business reading of each, together with two
measures of the data quality report.

The bounds are defined once, with the reason for each, in the `THRESHOLDS` dictionary of
`src/multimodal_etl/kpi.py`, and the dashboard reads them from there. The table below repeats
them by hand, and `tests/integration/test_documentation.py` fails if this document stops naming
one of the indicators.

## What the indicators are meant to detect

The dataset is meant to train a fake-news detector. An outright breakdown is easy to see, and
the indicators target the slower kinds of degradation: a feed that changes format and stops
returning images, an expired API key, or a dataset that ends up fed by a single publisher. In
each of these cases the pipeline keeps running with every task marked as a success, and the model
would be trained on data that has lost its value.

## The nine indicators and their bounds

The table repeats the bounds of the n = 9 indicators in `THRESHOLDS`. `metrics.yaml` gives each
one its definition, its business reading and its uncertainty, and the Bounds column gives the
three levels the dashboard uses for the status of each row.

<!-- source: src/multimodal_etl/kpi.py -->
| Indicator | Unit | Bounds | What its drift gives away |
|---|---|---|---|
| Validity rate | % | healthy at or above 60, watch to 45, act below | a source has changed format |
| Text-image pairing | % | healthy at or above 90, watch to 75, act below | the dataset is losing its multimodal nature |
| Images downloaded | % | healthy at or above 80, watch to 60, act below | the media are becoming unreachable: a CDN, a 403 |
| Volume ingested | publications | healthy at or above 80, watch to 40, act below | a source has gone silent |
| Share of the dominant source | % | healthy at or below 50, watch to 70, act above | the dataset is inheriting one publisher's editorial bias |
| Median age | h | healthy at or below 48, watch to 168, act above | the feed has frozen, and the past is being re-ingested |
| Duplicate rate | % | healthy at or below 5, watch to 15, act above | over-ingestion, or an identifier that has become unstable |
| Total duration | s | healthy at or below 90, watch to 300, act above | the daily window is about to be exceeded |
| Failed sources | sources | healthy at 0, watch at 1, act at 2 or more | an incident reaching a source |

`src/multimodal_etl/kpi.py` computes each indicator from the run record and the exported
dataset. The dashboard then labels it `within bounds`, `watch` or `act now`. The total duration
is the sum of the extract, transform and load durations.

**The bound of the validity rate is deliberately low.** The bound was set when the rate sat around
65 %, and the two runs of 2026-09-15 recorded in `docs/runbook.md` reached 69.0 % and 74.3 %.
Almost every rejection comes from an image that could not be obtained: the FakeNewsNet URLs go
back at least to 2018, when the dataset first appeared, and a good share of them no longer answer.
A bound at 85 % would have put both runs outside the healthy range. The bound sits below the
measured rates, so that a rate falling under it points to a source that has broken.

**A source turned off on purpose is not a failed source.** The extract step records a cause next
to each count, one of `ok`, `quota`, `network`, `malformed`, `empty` and `disabled`, and counts
only `quota`, `network` and `malformed` as incidents. The comment above `_OPTIONAL` in
`src/multimodal_etl/extract.py` says which connector may stand down, and why. These three incident
causes are assigned when a connector raises an exception. The RSS, NewsData.io and FakeNewsNet
connectors raise their request failures, so RSS feeds that cannot be reached, FakeNewsNet CSVs
that fail to download or a NewsData.io quota used up count towards the failed-sources indicator.
The RSS and FakeNewsNet connectors raise only when none of their feeds or files delivered a
publication. One feed that fails while the others deliver is written to the log and leaves the
count at zero, and its absence can still show up in the volume ingested.

## What the published run measured

<!-- source: reports/indicators.json -->
The published run is the second Airflow run of 2026-09-15. It collected n = 171 publications
from three of the four connectors, and all nine indicators were within their bounds. The
validity rate was **74.3 %**, with 127 of 171 publications kept. Of 136 attempted image
downloads, **94.9 %** succeeded. Extract, transform and load took **66.41 s** in total.
`reports/indicators.json` holds the value, the unit and the bound of each indicator, and
`uv run python scripts/quality_report.py --measure` rewrites it from the latest dataset and run
record on disk.

Some runs cross bounds. `docs/images/dashboard-status.png` shows the same page against the
twenty-four-row demonstration sample, where three bounds are crossed and the page names them.

## What crossing a bound does today

The pipeline does not evaluate the bounds while it runs. They are evaluated when the dashboard
is opened, when `scripts/quality_report.py --measure` writes `reports/indicators.json`, and when
`notebooks/04_kpi.ipynb` is executed.

| Bound crossed | What happens |
|---|---|
| Into `watch` | the status word of the row turns amber in the dashboard's status table |
| Into `act now` | the status word turns red, and a banner under the table names the indicator, its reading and its bound |

Crossing a bound writes nothing to the log and sends no alert. The pipeline runs on one machine
with no on-call rota, and the last section of this document describes what a deployment would add.

## How the pipeline handles failures

- Each connector runs in its own `try/except`. A connector that raises is logged, recorded in
  the per-source tally, and skipped, and the other sources still run.
- Every HTTP request goes through `requests`, with a configurable timeout of 15 seconds by
  default (`MULTIMODAL_ETL_REQUEST_TIMEOUT`). The RSS feeds are downloaded that way as well, and
  feedparser parses what was downloaded.
- Each image is opened with Pillow before it is kept, and an unreadable file is deleted before it
  can enter the dataset.
- Each Airflow task is configured with `retries=1` and a two-minute delay, so a task that fails
  runs once more two minutes later.
- Each of the transform and load tasks can be run again by itself, because the steps hand their
  results to each other through files and these two read the last archived artefact when the
  working file has been cleared. The metrics task has no such fallback, and replayed after the
  cleanup it writes a run record with zero counts.
- The load is incremental: only absent publications are added, so replaying a run never creates
  a duplicate and never overwrites an existing row.
- Every module logs through one configuration that writes each event, with its level, timestamp
  and originating module, to the console and to `var/logs/multimodal_etl.log`.

## The data quality report

`reports/data_quality.md` is the other place where this repository publishes numbers. It is
written for the person who decides whether to train on the output, and the header of
`src/multimodal_etl/quality/report.py` states the question it answers.

The report is rendered from `reports/data_quality.json`, which holds the measures of one dated
run. Live feeds return a different corpus at every run, so a report recomputed at each
publication could not be checked by any reader. Keeping the measures in a tracked file makes the
report reproducible. `uv run python scripts/quality_report.py --measure` takes a new measurement,
and `uv run python scripts/quality_report.py` renders the markdown from the tracked measures,
byte for byte, on any machine.

<!-- source: reports/data_quality.json -->
The report's most useful line concerns text length. Among the n = 127 publications kept by the
second run of 2026-09-15, the **28** with a label have a mean text length of **56.1** characters,
and the 99 without one a mean of **383.5**. The Fakeddit sample, which is synthetic, supplies
twenty of the 28 labelled rows. Annotation and text length pull in opposite directions in this
corpus, and `reports/data_quality.md` explains what that means for fitting a model.

## What a deployment would add

The sections above describe what the repository runs. This section describes additions that are
designed and not implemented.

**Alerting.** E-mail and a webhook to Slack or Teams when a red bound is crossed, carrying the DAG
and task name, the timestamp, the indicator at fault, its value against its bound, and a link to
the task logs. Airflow provides `on_failure_callback` and e-mail notification. The DAG does not
evaluate the bounds today, so a task would first have to read them and fail on a red one.

**Drift detection over time.** The distributions themselves are worth watching beyond the
instantaneous bounds: the spread of languages and of sources, text length, the share of images.
The check would compare the trend over the last ten runs, because a single figure cannot show a
drift. The run history under `data/processed/runs/` is the input such a check would read, and
Evidently could produce the reports from it. The history is already written, and the check is
not implemented.

**A review rhythm.** A daily run of the DAG, the indicators read after each run, the API quota
reviewed weekly, and a monthly comparison of distributions. The DAG already declares its
`@daily` schedule. The rest relies on a person assigned to the review, a role that a single
workstation does not have.

**Scaling out.** The pipeline runs on a single workstation, with Airflow in Docker and a SQLite
database. Two parts would have to be reworked first: the image storage, which would move from
the local disk to object storage, and the extraction, which reads the sources one after another
today and would read them in parallel. On a managed platform such as Databricks, the same
functions would become the tasks of a job, and the target a Delta table. On Kubernetes,
Airflow's `KubernetesExecutor` would run each task in its own pod, sized to its needs, since the
extraction waits mostly on the network and the transformation on the CPU. Apart from the two
changes above, the step functions would stay as they are, and only the execution layer would
move.
