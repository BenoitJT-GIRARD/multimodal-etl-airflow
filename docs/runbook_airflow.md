# Runbook — exécuter le DAG `multimodal_etl` avec Airflow

Ce guide décrit pas à pas comment lancer l'orchestration en local avec Apache Airflow, et
comment produire les journaux d'exécution du DAG.

Le DAG réutilise exactement les fonctions du package `multimodal_etl` : la logique métier est
déjà couverte par les tests unitaires et par `scripts/run_etl.py`. Airflow n'ajoute que
la couche d'orchestration, de planification et de reprise.

## 1. Prérequis

- Docker Desktop installé et démarré (Docker ≥ 24, Compose v2).
- **Le projet doit se trouver sur un disque local.** Docker ne sait pas monter un dossier
  situé sur un lecteur virtuel de synchronisation (Google Drive, OneDrive) : les montages
  sont créés vides, sans erreur, et le DAG n'est jamais découvert. Si le projet est
  stocké sur un tel lecteur, en copier ou en cloner une version dans un dossier local
  (`C:\dev\multimodal_etl`, par exemple) et lancer Airflow depuis cette copie.

## 2. Préparer la configuration

```powershell
Copy-Item docker/.env.example docker/.env
```

Puis renseigner dans `docker/.env` :

- `AIRFLOW_UID` — `0` sous Windows, sortie de `id -u` sous Linux et macOS. Sans cela, le
  conteneur ne peut pas écrire dans `data/`.
- `NEWSDATA_API_KEY` — facultatif, la même clé que dans le `.env` du projet. Sans clé, la
  source NewsData.io se désactive proprement et les trois autres continuent.

## 3. Construire l'image et démarrer

```powershell
docker compose -f docker/docker-compose.airflow.yaml build
docker compose -f docker/docker-compose.airflow.yaml up -d
```

L'image est construite une fois à partir de `docker/Dockerfile` : elle installe les
dépendances du pipeline en respectant le fichier de contraintes officiel d'Airflow. On
n'utilise pas `_PIP_ADDITIONAL_REQUIREMENTS` — l'installation serait refaite à chaque
redémarrage, et pip y remplacerait des bibliothèques dont Airflow dépend lui-même.

Vérifier que les services sont en bonne santé :

```powershell
docker compose -f docker/docker-compose.airflow.yaml ps
```

## 4. Vérifier que le DAG est chargé

```powershell
docker compose -f docker/docker-compose.airflow.yaml exec airflow-scheduler airflow dags list
docker compose -f docker/docker-compose.airflow.yaml exec airflow-scheduler airflow dags list-import-errors
```

La première commande doit afficher `multimodal_etl`, la seconde ne rien renvoyer.

## 5. Depuis l'interface

1. Ouvrir <http://localhost:8080> — identifiants `airflow` / `airflow`.
2. Activer le DAG **`multimodal_etl`** puis cliquer sur **Trigger DAG**.
3. Ouvrir la vue **Graph** : les cinq tâches s'enchaînent
   `extraction → transformation → chargement → metriques → nettoyage` et passent au vert.

Captures d'écran utiles :

- la vue **Graph** avec les cinq tâches en succès ;
- la vue **Grid** montrant une exécution complète ;
- le **log** de la tâche `chargement`, où apparaît la ligne
  `Chargement : N nouvelles publications`.

## 6. En ligne de commande (preuves reproductibles)

Exécuter le DAG entier :

```powershell
docker compose -f docker/docker-compose.airflow.yaml exec airflow-scheduler `
  airflow dags test multimodal_etl 2026-08-20
```

Rejouer **une seule tâche**, pour vérifier qu'elle est bien indépendante des autres :

```powershell
docker compose -f docker/docker-compose.airflow.yaml exec airflow-scheduler `
  airflow tasks test multimodal_etl transformation 2026-08-20
```

Le résultat de ces deux commandes est archivé dans `docs/preuve_execution_airflow.md`.

## 7. Ce que produit une exécution

- un JSON brut dans `data/raw/`, et les images dans `data/raw/images/` ;
- un jeu de données et ses statistiques dans `data/processed/` ;
- les tables peuplées dans `data/db/multimodal_etl.db` ou la base `MULTIMODAL_ETL_DB_URL` ;
- une fiche d'exécution dans `data/processed/runs/`, lue par le tableau de bord ;
- une zone de transit `data/interim/` **vide**, la tâche `nettoyage` l'ayant purgée.

## 8. Arrêter

```powershell
docker compose -f docker/docker-compose.airflow.yaml down
# Pour tout supprimer, base de métadonnées et journaux compris :
# docker compose -f docker/docker-compose.airflow.yaml down -v
```

## 9. En cas de problème

| Symptôme | Cause probable | Correction |
|---|---|---|
| `airflow dags list` ne renvoie rien | le dossier `dags/` monté est vide | le projet est sur un lecteur virtuel : travailler depuis une copie locale (§1) |
| Le scheduler redémarre en boucle | droits d'écriture sur les journaux ou sur `data/` | vérifier `AIRFLOW_UID` dans `docker/.env` |
| `MappedAnnotationError` au démarrage | une dépendance a écrasé la version de SQLAlchemy d'Airflow | reconstruire l'image : elle installe sous contrainte officielle |
| Une tâche échoue sur une source | incident réseau ou clé d'API absente | consulter le log de la tâche ; les autres sources ont continué |

## 10. Sécurité de la base

Les identifiants `airflow` / `airflow` du fichier compose ne conviennent qu'à une
exécution locale. En production : secrets gérés hors du dépôt, rôle applicatif limité aux
tables du pipeline, TLS sur les connexions et chiffrement au repos — voir le §8 du plan
de monitoring.
