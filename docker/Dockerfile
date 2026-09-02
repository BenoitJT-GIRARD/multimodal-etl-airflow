# Image Airflow enrichie des dependances du pipeline Multimodal ETL.
#
# La documentation Airflow deconseille d'installer des paquets au demarrage du
# conteneur (variable _PIP_ADDITIONAL_REQUIREMENTS) : l'installation est refaite a
# chaque redemarrage et un simple incident reseau fait echouer le service. On
# construit donc une image, une fois pour toutes.
#
# L'installation utilise le fichier de contraintes officiel d'Airflow : il fige les
# versions des bibliotheques dont Airflow depend. Sans lui, pip installerait par
# exemple SQLAlchemy 2.x, incompatible avec Airflow 2.10, et le scheduler
# s'arreterait au demarrage.
#
# Construction : docker compose -f docker/docker-compose.airflow.yaml build

FROM apache/airflow:2.10.4

ARG AIRFLOW_VERSION=2.10.4
ARG PYTHON_VERSION=3.12

COPY requirements-airflow.txt /tmp/requirements-airflow.txt

# pip est execute avec l'utilisateur `airflow` fourni par l'image officielle.
USER airflow
RUN pip install --no-cache-dir -r /tmp/requirements-airflow.txt \
    --constraint "https://raw.githubusercontent.com/apache/airflow/constraints-${AIRFLOW_VERSION}/constraints-${PYTHON_VERSION}.txt"
