# Architecture

How the pipeline is put together, and the alternatives that were considered and set aside.
`docs/data-source.md` describes where the data comes from, `docs/DB.md` what it becomes,
`docs/protocol.md` how it is monitored, `docs/runbook.md` how to run the orchestration and
`docs/interface.md` what the dashboard shows.

## One implementation of each step

`src/multimodal_etl/pipeline.py` holds five functions, one per step. The command-line scripts
and the five `PythonOperator` tasks of the Airflow DAG call these functions. The notebooks
import lower-level functions of the package directly, such as `collect_sources`, `process` and
`compute_kpis`, so each step is implemented in one place only. The DAG file has 57 lines of code
after its docstring: the imports, the default arguments, the five task declarations, the chain
between them, and one wrapper that records Airflow as the orchestrator of the run.

As a result, the DAG can be replaced without touching the pipeline, and the tests exercise the
code the DAG runs.

## How the steps hand data to each other

The steps exchange files through a working area, `data/interim/`, managed by
`src/multimodal_etl/transit.py`. The extract and transform steps archive their result under
`data/raw/` or `data/processed/` and copy it into the working area for the next step. The
transform and load steps read their input from the working area. When the working file is
missing, because the cleanup step has removed it or because a step is being replayed later, the
step reads the last archived artefact.

An in-memory hand-off would have been simpler to write, and it would have required every task to
run in the same process as the one before it. Replaying a single step is one of the reasons for
using an orchestrator here, and `docs/runbook.md` shows the transform step replayed on its own
after the working area was emptied.

The cost is two writes per step where an in-memory hand-off needs none, and archive directories
that keep growing. The cleanup step empties the working area and keeps the archives, because a
replay reads them.

## Where idempotency is enforced

Idempotency rests on the schema, whichever writer runs first. Each table declares a primary key,
and the insert statement ignores any row whose key is stored already. `docs/DB.md` gives the six
keys.

An earlier version of the loader asked the database which identifiers it already held and then
wrote the remaining rows. Two writers working in that interval would both find a row absent and
both write it, and a pipeline designed for replaying tasks makes such an overlap possible. The
loader now counts the rows of each table before and after the insert and reports the difference,
so the number of rows written is measured.

## How a failing source is isolated

The extract step calls each connector inside its own `try/except`, and records for each source a
count and a cause: `ok`, `quota`, `network`, `malformed`, `empty` or `disabled`. An exception
raised by a connector is classified as `quota`, `network` or `malformed`, and only these three
causes count as incidents.

Before the cause was recorded, a run in which one of the four connectors returned nothing looked
like a successful run. The opposite mistake was also possible: NewsData.io without a key stands
down by configuration, and counting it as an outage would leave every run without a key at the
`watch` level of the failed-sources indicator.

The classification applies to the exceptions that reach the extract step, and the RSS reader,
the NewsData.io client and the FakeNewsNet downloader let their request failures through. A
network error or an HTTP error status is recorded as `network`, and as `quota` when the status
is 429. A NewsData.io answer that cannot be parsed as JSON, or whose payload reports an error, is
recorded as `malformed`. The RSS reader and the FakeNewsNet downloader each read several feeds or
files. They log the one that fails, keep the others, and raise the first failure only when none
of them delivered a publication. A connector that ran without an error and returned no
publication is recorded as `empty`.

## Where configuration lives

`src/multimodal_etl/config.py` holds the paths as module constants and the run parameters as
frozen dataclasses. `src/multimodal_etl/utils/paths.py` decides where the project root is. It
takes `MULTIMODAL_ETL_ROOT` when that variable is set, then the first parent directory of the
package that holds `pyproject.toml`, and the working directory as a last resort. Half a dozen
modules used to work the root out for themselves, and the DAG used to patch `sys.path` by hand.

Three environment variables let the whole pipeline run in a test with no access to the
network. `MULTIMODAL_ETL_DATA_DIR` sets the directory for the data, the database and the run
records, `MULTIMODAL_ETL_SOURCES` lists the connectors to run, and `MULTIMODAL_ETL_RSS_FEEDS`
replaces the shipped feeds. `tests/system/test_pipeline_end_to_end.py` uses them to run the
whole chain against a feed that the test serves on the loopback interface.

## Alternatives set aside

Five alternatives were considered and set aside.

**A message queue between the steps.** Kafka or Redis would decouple the steps further, and would
add a service to run, monitor and document. Files on disk already allow replay and inspection,
and the measured runs showed no need for more.

**Parallel extraction.** The four sources are read one after another. The repository publishes no
timing of the extraction alone, only the 66.41 s that extract, transform and load took together in
the published run, and reading the sources in parallel was expected to save only seconds at this
volume. Parallel reads become worthwhile as the number of sources grows, and they are one of the
two changes `docs/protocol.md` lists for scaling out.

**Airflow's XCom for the hand-off.** XCom belongs to Airflow, so using it would tie the steps to
the orchestrator, and the command-line scripts could no longer call the same functions. The
working area works the same way under Airflow and from a script.

**A retry policy per source, in addition to Airflow's retry per task.** Airflow retries a failed
task once, two minutes later. A policy per source would be more precise, but it would make a
source that is down and a failed run look alike from inside the extraction.

**Object storage for the images.** The images are kept on the local disk of a single machine.
Moving them to object storage is the other change that `docs/protocol.md` lists for scaling out,
and the current code would need changes to support it.
