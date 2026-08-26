# Extraction de données multimodales pour la détection de fake news

Objectif : construire un **pipeline ETL automatisé** qui récupère des
publications **multimodales (texte + image)** depuis plusieurs sources, les transforme en
un jeu de données propre et structuré, puis les charge dans une base — le tout orchestré
par **Apache Airflow** et suivi par un **tableau de bord KPI**.

## Ce que fait le pipeline

Quatre sources, quatre méthodes d'accès, et pour chaque publication **le texte et le
fichier image téléchargé côte à côte** :

| Source | Accès | Apport |
|---|---|---|
| Flux RSS (The Guardian, BBC, ABC News) | `flux_rss` | volume et fraîcheur |
| API NewsData.io | `api_rest` | actualité structurée |
| FakeNewsNet | `telechargement_github` | vérité terrain académique |
| Fakeddit | `telechargement_kaggle` | volume multimodal annoté |

Les CSV de FakeNewsNet ne contiennent pas d'image : le pipeline la retrouve dans les
métadonnées Open Graph de l'article. Toutes les images sont téléchargées, validées par
Pillow, et une publication sans image n'entre pas dans le jeu de données.

## Structure

```
multimodal-etl-airflow/
├── src/multimodal_etl/          # le pipeline
│   ├── config.py           # chemins et paramètres (dataclasses immuables)
│   ├── logging_setup.py    # journalisation centralisée
│   ├── schema.py           # schéma des publications — source unique de vérité
│   ├── sources/            # un module par source + l'enrichissement Open Graph
│   ├── images.py           # téléchargement et validation des images
│   ├── extract.py          # étape E : collecte → JSON brut + fichiers image
│   ├── transform.py        # étape T : nettoyage, validation, normalisation
│   ├── load.py             # étape L : chargement relationnel incrémental
│   ├── transit.py          # zone d'échange entre étapes (indépendance des tâches)
│   ├── pipeline.py         # les 5 étapes, appelées par les scripts ET par le DAG
│   └── kpi.py              # indicateurs et seuils d'alerte
├── scripts/                # points d'entrée en ligne de commande
├── dags/                   # DAG Airflow
├── docker/                 # image et docker-compose Airflow
├── dashboard/              # application Streamlit
├── notebooks/              # déroulé étape par étape
├── docs/                   # rapport, schéma, monitoring, preuves, démonstration
├── data/                   # raw / interim / processed / db / samples (ignorés par git)
└── tests/                  # tests unitaires (pytest)
```

## Installation

```powershell
uv sync --extra dev          # crée .venv (Python 3.12) et installe tout
uv run pre-commit install    # active les hooks qualité
Copy-Item .env.example .env  # renseigner NEWSDATA_API_KEY (facultatif)
```

## Exécution

Chaque étape est exécutable indépendamment, sans intervention manuelle :

```powershell
uv run python scripts/run_extraction.py      # 1. collecte → data/raw/ (+ images)
uv run python scripts/run_transformation.py  # 2. nettoyage → data/processed/
uv run python scripts/run_chargement.py      # 3. chargement en base
uv run python scripts/run_etl.py             # ou tout d'un coup
uv run streamlit run dashboard/app.py        # 4. tableau de bord KPI
```

Une étape relancée seule reprend le dernier artefact archivé si le fichier temporaire de
l'étape précédente a été nettoyé.

Orchestration Airflow — voir `docs/runbook_airflow.md` :

```powershell
docker compose -f docker/docker-compose.airflow.yaml build
docker compose -f docker/docker-compose.airflow.yaml up -d
# Interface : http://localhost:8080  (DAG : multimodal_etl)
```

## Qualité

```powershell
uv run pytest                # tests unitaires
uv run ruff check .          # lint
uv run ruff format .         # formatage
uv run bandit -c pyproject.toml -r src
```


## Licence

MIT
