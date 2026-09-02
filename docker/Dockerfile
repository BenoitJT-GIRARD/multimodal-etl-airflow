# The Airflow image, with the Multimodal ETL pipeline's dependencies added.
#
# The Airflow documentation advises against installing packages at container start
# (the _PIP_ADDITIONAL_REQUIREMENTS variable): the install is redone on every
# restart, and a single network hiccup fails the service. So we build an image,
# once and for all.
#
# The install uses Airflow's official constraints file: it pins the versions of the
# libraries Airflow depends on. Without it, pip would install SQLAlchemy 2.x, say,
# which Airflow 2.10 cannot work with, and the scheduler would stop at startup.
#
# Build with: docker compose -f docker/docker-compose.airflow.yaml build

FROM apache/airflow:2.10.4

ARG AIRFLOW_VERSION=2.10.4
ARG PYTHON_VERSION=3.12

COPY requirements-airflow.txt /tmp/requirements-airflow.txt

# pip runs as the `airflow` user the official image provides.
USER airflow
RUN pip install --no-cache-dir -r /tmp/requirements-airflow.txt \
    --constraint "https://raw.githubusercontent.com/apache/airflow/constraints-${AIRFLOW_VERSION}/constraints-${PYTHON_VERSION}.txt"
