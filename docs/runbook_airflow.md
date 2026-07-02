# Runbook — exécuter le DAG `multimodal_etl` avec Airflow (Docker)

Ce guide décrit, pas à pas, comment lancer l'orchestration ETL en local avec Apache
Airflow et comment produire les **preuves d'exécution** attendues (logs + captures
d'écran de l'interface Airflow).

> Le DAG réutilise exactement les fonctions du package `multimodal_etl` (extraction,
> transformation, chargement) ; la logique métier est donc déjà validée par les
> tests unitaires et par `scripts/run_etl.py`. Airflow ajoute uniquement la couche
> d'orchestration et de planification.

## 1. Prérequis

- Docker Desktop installé et démarré (Docker ≥ 24, Compose v2).
- Le partage de fichiers Docker doit autoriser le dossier du projet.

## 2. Préparer la configuration

```powershell
# Depuis la racine du projet
Copy-Item docker/.env.example docker/.env
# Renseigner éventuellement NEWSDATA_API_KEY dans docker/.env (même clé que le .env racine).
```

## 3. Démarrer Airflow

```powershell
docker compose -f docker/docker-compose.airflow.yaml up -d
```

Le premier démarrage télécharge l'image `apache/airflow:2.10.4`, initialise la base
de métadonnées PostgreSQL, crée l'utilisateur `airflow`, puis installe les
dépendances runtime du pipeline. Comptez quelques minutes.

Vérifier que les services sont sains :

```powershell
docker compose -f docker/docker-compose.airflow.yaml ps
```

## 4. Ouvrir l'interface et déclencher le DAG

1. Aller sur **http://localhost:8080** — se connecter avec `airflow` / `airflow`.
2. Dans la liste des DAGs, repérer **`multimodal_etl`**.
3. Activer le DAG (interrupteur à gauche) puis cliquer sur **▶ Trigger DAG**.
4. Ouvrir la vue **Graph** : les quatre tâches s'enchaînent
   `extract → transform → load → metriques` et passent au vert.

### Captures d'écran à fournir (preuves d'exécution)

- La vue **Graph** avec les quatre tâches en succès (vert).
- La vue **Grid** montrant un run complet.
- Le **log** de la tâche `load` (clic sur la tâche → onglet *Logs*), où l'on voit
  la ligne `Chargement : N lignes ecrites dans la table 'publications'`.

## 5. Preuve d'exécution sans interface (optionnel mais recommandé)

Pour générer des logs de tâches sans passer par l'UI :

```powershell
docker compose -f docker/docker-compose.airflow.yaml run --rm airflow-scheduler \
  airflow dags test multimodal_etl 2026-06-29
```

Cette commande exécute le DAG de bout en bout et écrit les journaux de chaque tâche
dans `docker/airflow/logs/`. Ces fichiers constituent une preuve d'exécution
reproductible.

## 6. Résultats attendus

- Un nouveau JSON brut dans `data/raw/`.
- Un dataset transformé dans `data/processed/` (+ son fichier `_stats.json`).
- La table `publications` peuplée dans `data/db/multimodal_etl.db` (ou la base
  `MULTIMODAL_ETL_DB_URL` configurée).
- Un fichier de métriques `data/processed/runs/run_airflow_*.json` pour le
  tableau de bord KPI.

## 7. Arrêter Airflow

```powershell
docker compose -f docker/docker-compose.airflow.yaml down
# Pour tout supprimer, y compris la base de métadonnées :
# docker compose -f docker/docker-compose.airflow.yaml down -v
```

## 8. Sécurité de la base de données (points de vigilance)

- **Authentification** : PostgreSQL exige un identifiant/mot de passe ; en
  production, ne jamais utiliser `airflow/airflow` mais des secrets gérés
  (variables d'environnement, *secret manager*).
- **Rôles** : limiter les accès — un rôle applicatif en lecture/écriture sur la
  seule table `publications`, distinct du rôle administrateur.
- **Chiffrage** : activer TLS pour les connexions et le chiffrage au repos (proposé
  par défaut sur Supabase / PostgreSQL managé).
