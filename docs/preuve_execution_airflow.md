# Preuve d'exécution du DAG dans Apache Airflow

journaux d'exécution du DAG `multimodal_etl`.

Environnement : Apache Airflow 2.10.4, `LocalExecutor`, base de métadonnées PostgreSQL,
image construite depuis `docker/Dockerfile`. Procédure complète dans
`docs/runbook_airflow.md`.

---

## 1. Le DAG est chargé, sans erreur d'import

```
$ airflow dags list
dag_id        | fileloc                                | owners    | is_paused
==============+========================================+===========+==========
multimodal_etl | /opt/airflow/dags/multimodal_etl_dag.py | multimodal_etl | None

$ airflow dags list-import-errors
No data found

$ airflow tasks list multimodal_etl --tree
<Task(PythonOperator): extraction>
    <Task(PythonOperator): transformation>
        <Task(PythonOperator): chargement>
            <Task(PythonOperator): metriques>
                <Task(PythonOperator): nettoyage>
```

Cinq tâches distinctes, une par étape du pipeline.

---

## 2. Exécution complète du DAG

```
$ airflow dags test multimodal_etl 2026-08-20
```

Extrait des journaux — les lignes de progression d'Airflow sont conservées, les lignes de
débogage retirées.

```
[DAG TEST] starting task_id=extraction map_index=-1
multimodal_etl.pipeline   | === ÉTAPE 1 — EXTRACTION ===
multimodal_etl.extract    | Extraction : source 'rss' -> 97 publications
multimodal_etl.extract    | Extraction : source 'newsdata' -> 10 publications
multimodal_etl.opengraph  | Open Graph : 11 images retrouvées sur 40 articles consultés
multimodal_etl.extract    | Extraction : source 'fakenewsnet' -> 48 publications
multimodal_etl.extract    | Extraction : source 'kaggle_fakeddit' -> 24 publications
multimodal_etl.extract    | Extraction : 179 publications brutes au total
multimodal_etl.images     | Images : 136 téléchargées, 5 échecs, 38 ignorées (10.8 Mo sur disque)
multimodal_etl.extract    | Extraction : 179 publications écrites dans data/raw/raw_publications_20260820_101629.json
multimodal_etl.transit    | Transit : 'extraction.json' déposé pour l'étape suivante
Marking task as SUCCESS. task_id=extraction

[DAG TEST] starting task_id=transformation map_index=-1
multimodal_etl.pipeline   | === ÉTAPE 2 — TRANSFORMATION ===
multimodal_etl.transform  | Transformation : 179 publications brutes lues
multimodal_etl.transform  | Transformation : 134/179 publications valides après nettoyage
multimodal_etl.transform  | Transformation : 0 doublons retirés
multimodal_etl.transform  | Transformation : dataset de 134 lignes exporté vers data/processed/publications_20260820_101630.parquet
multimodal_etl.transit    | Transit : 'dataset.parquet' déposé pour l'étape suivante
Marking task as SUCCESS. task_id=transformation

[DAG TEST] starting task_id=chargement map_index=-1
multimodal_etl.pipeline   | === ÉTAPE 3 — CHARGEMENT ===
multimodal_etl.load       | Chargement : 134 lignes ajoutées dans 'publication'
multimodal_etl.load       | Chargement : 7 lignes ajoutées dans 'source'
multimodal_etl.load       | Chargement : 134 lignes ajoutées dans 'contenu_texte'
multimodal_etl.load       | Chargement : 134 lignes ajoutées dans 'contenu_image'
multimodal_etl.load       | Chargement : 28 lignes ajoutées dans 'label'
multimodal_etl.load       | Chargement : 134 lignes ajoutées dans 'publications'
multimodal_etl.load       | Chargement : 134 nouvelles publications, 0 déjà présentes
Marking task as SUCCESS. task_id=chargement

[DAG TEST] starting task_id=metriques map_index=-1
multimodal_etl.pipeline   | === ÉTAPE 4 — MÉTRIQUES ===
multimodal_etl.pipeline   | Métriques : fiche d'exécution écrite dans data/processed/runs/run_20260820_101630.json
Marking task as SUCCESS. task_id=metriques

[DAG TEST] starting task_id=nettoyage map_index=-1
multimodal_etl.pipeline   | === ÉTAPE 5 — NETTOYAGE ===
multimodal_etl.transit    | Transit : 5 fichiers temporaires supprimés
Marking task as SUCCESS. task_id=nettoyage

DagRun Finished: dag_id=multimodal_etl, run_id=manual__2026-08-20T00:00:00+00:00,
state=success, run_type=manual
```

Les cinq tâches sont en `SUCCESS` et le `DagRun` se termine en `state=success`. Les
quatre sources ont contribué, 136 images ont été téléchargées, les six tables du modèle
relationnel ont été peuplées, et la zone de transit a été vidée par la dernière tâche.

---

## 3. Une tâche rejouée seule

C'est le point qui justifie l'orchestration : chaque tâche doit pouvoir être relancée
indépendamment des autres. La zone de transit vient d'être vidée par la tâche
`nettoyage`, donc `transformation` n'a plus son fichier d'entrée.

```
$ airflow tasks test multimodal_etl transformation 2026-08-20
```

```
airflow.task         | Executing <Task(PythonOperator): transformation> on 2026-08-20
multimodal_etl.pipeline   | === ÉTAPE 2 — TRANSFORMATION ===
multimodal_etl.transit    | Transit : 'extraction.json' absent, reprise de l'archive raw_publications_20260820_101629.json
multimodal_etl.transform  | Transformation : 179 publications brutes lues
multimodal_etl.transform  | Transformation : 134/179 publications valides après nettoyage
multimodal_etl.transform  | Transformation : dataset de 134 lignes exporté vers data/processed/publications_20260820_101643.parquet
multimodal_etl.transit    | Transit : 'dataset.parquet' déposé pour l'étape suivante
Marking task as SUCCESS. task_id=transformation
```

La tâche a détecté l'absence du fichier de transit, est repartie de la dernière
extraction archivée, et s'est terminée en succès — **sans rejouer l'extraction**, qui
prend une minute et consomme un appel d'API.

---

## 4. Chargement incrémental

Une seconde exécution ne recharge pas les mêmes données :

```
[ok] publications extraites  : 179
[ok] nouvelles en base       : 11
[ok] total accumulé en base  : 148
```

Sur 179 publications collectées, seules 11 étaient absentes de la base — les flux RSS
n'avaient publié que quelques articles entre les deux exécutions. Le jeu de données
s'enrichit au fil des exécutions quotidiennes, sans doublon et sans écraser l'historique.

---

## 5. Captures d'écran de l'interface

Prises sur une exécution déclenchée depuis l'interface et exécutée par l'ordonnanceur —
`reports/Girard_Benoit_12_202600820/Girard_Benoit_5_flux_etl_airflow_captures_082026/`.

| Capture | Ce qu'elle montre |
|---|---|
| `01_liste_dags.png` | Le DAG `multimodal_etl` actif, planifié `@daily`, avec ses exécutions récentes en succès. |
| `02_vue_grid.png` | La vue *Grid* : quatre exécutions, cinq tâches vertes chacune, et le détail de la dernière (`success`, 1 min 23 s). |
| `03_vue_graph.png` | La vue *Graph* : les cinq `PythonOperator` enchaînés, tous en `success`. |
| `04_log_chargement.png` | Le log de la tâche `chargement` : les six tables peuplées, et `16 nouvelles publications, 120 déjà présentes` — le chargement incrémental à l'œuvre. |
| `05_code_dag.png` | Le code du DAG tel qu'Airflow l'a chargé. |
