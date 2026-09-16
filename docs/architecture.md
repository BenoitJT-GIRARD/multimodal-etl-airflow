# Architecture

How the pipeline is put together, which choices were made deliberately, and what was ruled
out along the way. `docs/data-source.md` says where the data comes from, `docs/DB.md` what it
becomes, `docs/protocol.md` how it is watched, `docs/runbook.md` how to run the orchestration
and `docs/interface.md` what the dashboard shows.

## One copy of the logic, three ways to call it

`src/multimodal_etl/pipeline.py` holds five functions, one per step. The command-line scripts
call them, the Airflow DAG's five `PythonOperator` instances call them, and the notebooks call
them. There is no second implementation anywhere, and the DAG holds no business logic of its
own: it is thirty lines of wiring.

That is the reason the DAG can be replaced without touching the pipeline, and the reason the
tests exercise what production runs, and not a parallel path built for testing.

## The steps talk through files, not through memory

Each step reads its input from a working area (`src/multimodal_etl/transit.py`), archives its
own result under `data/raw/` or `data/processed/`, and stages a working copy for the next
step. When the working file is gone, because the fifth step cleared it or because the run is
being replayed a day later, the step falls back to the last archived artefact.

An in-memory hand-off between tasks would have been simpler to write and would have made every
task depend on the one before it in the same process. The replay of a single step is the
capability the whole orchestration exists for; `docs/runbook.md` shows one being replayed on
its own after the working area was emptied.

**What this costs.** Two writes per step where memory would need none, and a directory that
grows. The cleanup step empties the working area; the archives are kept on purpose, because
they are what a replay reads.

## The database refuses a duplicate; the code does not try to avoid one

Idempotency is a property of the schema, and not of whichever writer happens to run first:
`docs/DB.md` gives the six keys that carry it.

The version before this one asked the database which identifiers it already held, and then
wrote everything else. Two writers arriving in that interval both see the row as absent, and a
pipeline whose whole argument is that its tasks replay is precisely where two writers arrive.
The count of rows written is now read from the engine, before and after, and never predicted.

## A failing source is isolated, and its silence is qualified

Each connector runs inside its own `try/except`, and what comes back is a count and a cause:
`ok`, `quota`, `network`, `malformed`, `empty`, `disabled`. Only the first three of the failure
causes are incidents.

Without the cause, one silent connector out of four reads exactly like four working ones; and
the reverse mistake is as easy, since a source that stands down for want of a key is a
configuration choice, and calling that an outage leaves a healthy pipeline permanently amber.

## Configuration is read once, in one place

`src/multimodal_etl/config.py` holds every path and every tunable as frozen dataclasses, and
`src/multimodal_etl/utils/paths.py` answers the single question of where the project root is.
It is found by looking for `pyproject.toml`, and never counted upwards from a file. Half a
dozen modules each used to work it out for themselves, and the DAG patched `sys.path` by
hand.

Three variables steer a run without editing code, and they are what makes the pipeline
testable without a network: `MULTIMODAL_ETL_DATA_DIR` moves everything a run writes,
`MULTIMODAL_ETL_SOURCES` selects the connectors, `MULTIMODAL_ETL_RSS_FEEDS` points the feed
reader somewhere else. `tests/system/test_pipeline_end_to_end.py` runs the whole chain against
a feed served on loopback by the test itself.

## What was left out, and why

Four alternatives were looked at and rejected, and the reason is written down for each: a
design nobody can argue with is a design nobody considered.

**A message queue between the steps.** Kafka or Redis would decouple the steps further and
would add a service to run, to monitor and to explain. Files on disk already give replay and
inspection; nothing in the measured behaviour asks for more.

**Parallel extraction.** The four sources are read one after another. On this volume the
extraction is dominated by the image downloads, not by the feed reads, and parallelising the
sources would win seconds. It starts paying when the number of sources grows, and that is the
first thing to change if it does.

**Airflow's own `XCom` for the hand-off.** It is the orchestrator's mechanism, and using it
would tie the steps to Airflow, and the same functions would no longer run from a script or a
notebook. The working area works everywhere.

**A retry policy per source, in place of the one Airflow applies per task.** Airflow retries a
task once, two minutes later. A per-source policy would be more precise, and it would hide,
inside the extraction, the difference between a source that is down and a run that failed.

**Object storage for the images.** Local disk is what a single machine has. This is the first
thing that has to change to scale out, and `docs/protocol.md` names it as such: the current
design would not survive the move untouched.
