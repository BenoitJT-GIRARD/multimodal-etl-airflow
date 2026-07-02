# Plan de monitoring du pipeline ETL

Stratégie de surveillance du pipeline en production.

Ce plan décrit **comment surveiller** le pipeline d'extraction multimodale une fois
en production : quels indicateurs suivre, quels **seuils d'alerte**, comment **gérer
les erreurs** et à quelle **fréquence vérifier**. Il est cohérent avec le contexte
professionnel : alimenter en continu un détecteur de fake news avec des
données fraîches, valides et correctement multimodales.

## 1. Pourquoi monitorer ce pipeline ?

La performance du détecteur dépend directement de la **qualité du dataset**. Un
pipeline non surveillé peut silencieusement se dégrader : une source qui tombe, une
clé d'API expirée, un changement de format RSS, une chute du taux d'images valides…
Le monitoring garantit la **fiabilité**, la **fraîcheur** et la **traçabilité** des
données livrées au modèle.

## 2. Indicateurs suivis (alignés sur le tableau de bord KPI)

| Indicateur | Définition | Pourquoi c'est critique |
|---|---|---|
| **Taux de validité** | % de publications brutes retenues après nettoyage | Mesure la qualité globale de l'ingestion |
| **Taux d'association texte-image** | % de publications retenues avec image valide | Cœur du cas d'usage multimodal |
| **Volume ingéré** | Nombre de publications chargées par run | Détecte une source en panne |
| **Durée par étape** | Temps d'extraction / transformation / chargement | Détecte un ralentissement |
| **Appels API consommés** | Nombre d'appels NewsData.io | Surveille le quota et le coût |
| **Taux de doublons** | % de doublons écartés | Révèle une sur-ingestion ou un bug d'identifiant |
| **Fraîcheur** | Âge médian des publications (`published_at`) | Garantit l'actualité du dataset |

## 3. Seuils d'alerte

| Indicateur | 🟢 Normal | 🟠 Avertissement | 🔴 Critique |
|---|---|---|---|
| Taux de validité | ≥ 85 % | 70–85 % | < 70 % |
| Taux d'association texte-image | ≥ 90 % | 75–90 % | < 75 % |
| Volume ingéré (par run) | ≥ 80 | 40–80 | < 40 |
| Durée totale du run | < 30 s | 30–120 s | > 120 s |
| Appels API restants (quota) | > 30 % | 10–30 % | < 10 % |
| Échec d'une source | 0 source en échec | 1 source | ≥ 2 sources |

Un franchissement de seuil **orange** déclenche un log `WARNING` et une notification
non bloquante ; un seuil **rouge** déclenche un log `ERROR`, une alerte immédiate et,
selon le cas, l'arrêt du chargement pour ne pas polluer la base.

## 4. Gestion des erreurs

Le pipeline est conçu pour être **robuste par construction** :

- **Isolation des sources** : chaque connecteur est encapsulé dans un `try/except` ;
  une source défaillante est journalisée et n'interrompt pas les autres.
- **Timeouts réseau** : toute requête HTTP a un délai maximal configurable.
- **Reprises Airflow** : chaque tâche du DAG est configurée avec `retries=1` et un
  `retry_delay` de 2 minutes (incident réseau transitoire).
- **Idempotence** : le chargement utilise `if_exists="replace"` ; relancer un run
  régénère une table propre sans doublon.
- **Journalisation centralisée** : tous les événements sont écrits dans `logs/` avec
  niveau, horodatage et module d'origine (console + fichier).

## 5. Fréquence des vérifications

| Vérification | Fréquence | Moyen |
|---|---|---|
| Exécution du DAG | **Quotidienne** (`schedule="@daily"`) | Airflow scheduler |
| Contrôle des KPI | Après chaque run | Tableau de bord Streamlit |
| Revue des logs d'erreur | Quotidienne | `logs/multimodal_etl.log` + logs Airflow |
| Suivi du quota API | Hebdomadaire | KPI « appels API consommés » |
| Audit de dérive des données | Mensuel | Comparaison de distributions (voir §6) |

## 6. Détection de dérive (*data drift*)

Au-delà des KPI instantanés, on surveille l'**évolution** des distributions dans le
temps (langues, sources, longueur de texte, taux d'images) pour repérer une dérive
qui dégraderait le modèle. Outil recommandé : **Evidently** (rapports de dérive
automatisés), branché sur l'historique des datasets de `data/processed/`.

## 7. Alerting

- **Canaux** : e-mail et webhook (Slack/Teams) déclenchés sur seuil rouge. Airflow
  fournit nativement `on_failure_callback` et les notifications par e-mail.
- **Contenu d'une alerte** : nom du DAG/tâche, horodatage, indicateur en cause,
  valeur observée vs seuil, lien vers les logs.

## 8. Sécurité et conformité (base de données)

Conformément aux points de vigilance de la mission :

- **Authentification** forte sur la base (pas de secrets en dur, gestion via
  variables d'environnement / *secret manager*).
- **Rôles** : un compte applicatif limité à la table `publications`, distinct de
  l'administrateur.
- **Chiffrage** : TLS en transit et chiffrage au repos (par défaut sur Supabase /
  PostgreSQL managé).
- **Traçabilité** : le champ `ingested_at` et l'historique des runs (`runs/`)
  permettent d'auditer toute donnée chargée.

## 9. Synthèse

Le pipeline est surveillé sur trois axes — **qualité** (validité, multimodalité),
**performance** (durée, débit, coût) et **fiabilité** (sources, erreurs, dérive) —
avec des seuils explicites, une gestion d'erreurs robuste et des vérifications
planifiées. Cette stratégie garantit que le détecteur de fake news est alimenté en
continu par des données fiables et à jour.
