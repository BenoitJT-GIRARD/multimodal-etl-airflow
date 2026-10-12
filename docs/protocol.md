# What is measured, and what is done about it

Every number this repository publishes, how it is computed, the bound it is read against, and
what happens when that bound is crossed. `metrics.yaml` carries the same nine indicators in
machine-readable form, with the business reading of each.

The thresholds are not copied here by hand: they are defined once, in the `THRESHOLDS`
dictionary of `src/multimodal_etl/kpi.py`, each with its rationale, and the dashboard reads
them from that same place. `tests/integration/test_documentation.py` fails if this document
stops naming one of them.

## What this exists to catch

The detector trained downstream is only as good as the dataset feeding it. An outright
breakdown is visible, so the risk is silent degradation: a feed that changes format and stops
returning images, an expired API key, a dataset that ends up fed by a single publisher. The
pipeline keeps running with every task green, and the model is trained on data that is no
longer worth anything.

## The nine indicators, and where each bound comes from

The bounds below, n = 9 indicators, are read from `THRESHOLDS`. `metrics.yaml` gives each one
its definition, its business reading and what its uncertainty is; the column below is the
ladder the dashboard colours a row by.

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

Each one is computed by `src/multimodal_etl/kpi.py` from the run record and the exported
dataset, and names an action when it drifts.

**The validity rate's bound is set low on purpose.** The rate sits around 65 % in normal operation, and a
rejection almost always comes from an image being unavailable: the FakeNewsNet URLs date from
2016-2018 and a good share of them no longer answer. A bound set at 85 % would have kept the
indicator permanently red, and an always-red indicator stops being read by anyone. It is
calibrated on the measured behaviour, which is what lets it signal a real break.

**A source deliberately turned off is not a failed source.** The extraction step returns a
*cause* alongside each count, one of `ok`, `quota`, `network`, `malformed`, `empty` and
`disabled`, and only the first three failure causes are counted as incidents. The comment above
`_OPTIONAL` in `src/multimodal_etl/extract.py` says which connectors may stand down, and why.

## What the published run read

<!-- source: reports/indicators.json -->
In the run of 2026-09-15, through the Airflow DAG, over n = 171 publications collected from
three of the four connectors, all nine indicators were within their bounds.
A reader would check three of them first: **74.3 %** validity,
**94.9 %** of the announced image URLs obtained, **66.41 s** end to end. `reports/indicators.json`
carries the value, the unit and the bound of each, and
`uv run python scripts/quality_report.py --measure` rewrites it from whatever run is on disk.

Not every run has all nine within bounds:
`docs/images/dashboard-status.png` photographs the same page against the twenty-four-row
demonstration sample, where three bounds are crossed and the page says which.

## What crossing a bound does today

| Bound crossed | What happens |
|---|---|
| Into `watch` | a `WARNING` line in `var/logs/multimodal_etl.log`, and an amber row on the dashboard |
| Into `act now` | an `ERROR` line, and a red row with a banner naming the indicator and its bound |

Nothing else happens: the pipeline runs on one machine, and there is nobody on call. The section below says what a deployment would add.

## How the pipeline degrades instead of stopping

- Each connector runs in its own `try/except`: a source that is down is logged and counted
  without interrupting the others.
- Every HTTP request has a configurable timeout, so a server that stops answering does not
  block the run.
- An image is opened by Pillow before being kept, and an unreadable file is deleted before it
  can enter the dataset.
- Each Airflow task is configured with `retries=1` and a two-minute delay, which absorbs a
  transient network incident.
- A single task can be replayed on its own, because the steps hand their results to each other
  through files and any task falls back to the last archived artefact when the working file has
  been cleared.
- The load is incremental: only absent publications are added, so replaying a run never
  creates a duplicate and never overwrites the history.
- Logging is central: every event is written to `var/logs/` with its level, timestamp and
  originating module, to the console and to a file.

## The published numbers, and what they were measured on

`reports/data_quality.md` is the other place this repository publishes numbers, and it is
written for whoever has to decide whether to train on the output. The header of
`src/multimodal_etl/quality/report.py` states the question it answers.

It is rendered from `reports/data_quality.json`, which holds the measures of one named run.
That separation is what makes the report reproducible. Live feeds do not hand back the same
corpus twice, and a report recomputed at every publication would be a file no reader could
check. `uv run python scripts/quality_report.py --measure` takes a new
measurement; `uv run python scripts/quality_report.py` republishes the markdown from it, byte
for byte, on any machine.

<!-- source: reports/data_quality.json -->
Its most useful line is about text length: over the n = 127 publications the run of
2026-09-15 kept, the **28** labelled ones average **56.1** characters of text against **383.5**
for the 99 unlabelled. Annotation and text length pull in opposite directions here, and
`reports/data_quality.md` says why that matters to whoever fits a model.

## What would be added in a deployment, and is not here

Everything above this line runs. Everything below it is design, and none of it is wired up.

**Alerting.** E-mail and webhook, on Slack or Teams, when a red bound is crossed, carrying the
DAG and task name, the timestamp, the indicator at fault, the observed value against its bound,
and a link to the task logs. Airflow provides `on_failure_callback` and e-mail notification
natively, so this is configuration and not code.

**Drift detection over time.** Beyond the instantaneous bounds, the distributions themselves
are worth watching: spread of languages, of sources, text length, share of images. A single
figure settles nothing here; the trend over the last ten runs is what to look at.
The run history under `data/processed/runs/` is the input such a check would read, and
Evidently produces the reports from it. The history exists; the check does not.

**A review rhythm.** A daily DAG run on `@daily`, the indicators read after each run, the API
quota looked at weekly, a monthly comparison of distributions. The schedule is declared on the
DAG; the rest happens when someone looks, and on one workstation that is nobody's job.

**Scaling out.** The pipeline runs on a single workstation, with Airflow in Docker and a
SQLite database. Two things have to be reworked before that changes: image storage, which
has to move to object storage and off the local disk, and the parallelisation of the
extraction, today sequential source by source. On a managed platform such as Databricks the
same functions become the tasks of a job and the target becomes a Delta table; on Kubernetes,
Airflow's `KubernetesExecutor` runs each task in its own pod, sized to its need: extraction is
bound by the network, transformation by the CPU. In both cases only the execution layer
moves, and the business logic stays as it is.
