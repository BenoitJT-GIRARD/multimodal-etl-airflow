# Plan de monitoring du pipeline ETL

stratégie de surveillance du pipeline en production.

Ce plan décrit comment on surveille le pipeline d'extraction multimodale : quels
indicateurs, à partir de quels seuils on s'inquiète, que fait le pipeline quand ça se
passe mal, et à quelle fréquence on vérifie.

## 1. Ce qu'on cherche à éviter

La performance du détecteur dépend directement de la qualité du jeu de données qui
l'alimente. Le risque n'est pas la panne franche — elle se voit — mais la **dégradation
silencieuse** : un flux RSS qui change de format et ne renvoie plus d'image, une clé
d'API expirée, un jeu qui n'est plus alimenté que par une seule source. Le pipeline
continue de tourner, les tâches restent vertes, et le modèle est entraîné sur des données
qui ne valent plus rien.

Le monitoring existe pour rendre cette dégradation visible.

## 2. Indicateurs suivis

Chaque indicateur listé ici est calculé par `src/multimodal_etl/kpi.py` et affiché par le
tableau de bord. Aucun n'est décoratif : chacun déclenche une action s'il dérive.

| Indicateur | Ce qu'il mesure | Ce qu'il révèle quand il dérive |
|---|---|---|
| **Taux de validité** | part des publications collectées qui passent les contrôles | une source a changé de format |
| **Association texte-image** | part des publications retenues dont l'image est sur disque | le jeu de données perd sa nature multimodale |
| **Images téléchargées** | part des URL d'image qui ont donné un vrai fichier | les médias deviennent inaccessibles (CDN, 403) |
| **Volume ingéré** | nombre de publications produites par exécution | une source s'est tue |
| **Part de la source dominante** | concentration du jeu de données | le jeu hérite du biais éditorial d'un seul émetteur |
| **Âge médian** | ancienneté des publications ingérées | le flux s'est figé, on ré-ingère du passé |
| **Taux de doublons** | part des publications écartées en double | sur-ingestion, ou identifiant devenu instable |
| **Durée totale** | temps d'exécution du pipeline | la fenêtre quotidienne va être dépassée |
| **Sources en échec** | connecteurs muets ou en erreur | incident d'accès à une source |
| **Appels d'API consommés** | quota NewsData.io utilisé | coût externe, risque d'épuisement du quota |
| **Poids des images** | disque occupé par les médias | coût de stockage |
| **Apport de l'exécution** | part des publications réellement nouvelles en base | le pipeline tourne à vide et ré-ingère les mêmes contenus |

## 3. Seuils d'alerte

| Indicateur | Normal | Avertissement | Critique |
|---|---|---|---|
| Taux de validité | ≥ 60 % | 45 – 60 % | < 45 % |
| Association texte-image | ≥ 90 % | 75 – 90 % | < 75 % |
| Images téléchargées | ≥ 80 % | 60 – 80 % | < 60 % |
| Volume ingéré | ≥ 80 | 40 – 80 | < 40 |
| Part de la source dominante | ≤ 50 % | 50 – 70 % | > 70 % |
| Âge médian | ≤ 48 h | 48 h – 7 j | > 7 j |
| Taux de doublons | ≤ 5 % | 5 – 15 % | > 15 % |
| Durée totale | ≤ 90 s | 90 – 300 s | > 300 s |
| Sources en échec | 0 | 1 | ≥ 2 |

> Ces seuils ne sont pas recopiés à la main dans ce document : ils sont définis **une
> seule fois**, dans le dictionnaire `SEUILS` de `src/multimodal_etl/kpi.py`, avec la
> justification de chacun. Le tableau de bord les lit au même endroit — le document et
> l'application ne peuvent donc pas se contredire.

Un mot sur le **taux de validité**, dont le seuil peut surprendre : il tourne autour de
65 %, et c'est son fonctionnement normal. Le rejet vient presque toujours d'une image
indisponible — les URL de FakeNewsNet datent de 2016-2018 et une bonne partie ne répond
plus. Un seuil placé à 85 % aurait mis l'indicateur au rouge en permanence, et un
indicateur toujours rouge n'est plus lu par personne. Il est donc calé sur le
comportement mesuré, ce qui lui permet de signaler une vraie rupture.

Un franchissement **orange** produit un log `WARNING` et une notification non bloquante.
Un franchissement **rouge** produit un log `ERROR` et une alerte immédiate ; selon
l'indicateur, le chargement est suspendu plutôt que de polluer la base.

Une précision utile : une source **volontairement désactivée** n'est pas une source en
échec. NewsData.io ne s'active que si une clé d'API est fournie ; son absence est un
choix de configuration, pas un incident, et le pipeline ne déclenche pas d'alerte pour
elle.

## 4. Gestion des erreurs

Le pipeline est conçu pour continuer à fonctionner dégradé plutôt que de s'arrêter.

- **Isolation des sources.** Chaque connecteur est encapsulé dans un `try/except` : une
  source en panne est journalisée et comptée, elle n'interrompt pas les autres.
- **Délais d'attente.** Toute requête HTTP a un délai maximal configurable — un serveur
  qui ne répond plus ne bloque pas l'exécution.
- **Validation des médias.** Une image est ouverte par Pillow avant d'être conservée ; un
  fichier illisible est supprimé plutôt que d'entrer dans le jeu de données.
- **Reprises Airflow.** Chaque tâche est configurée avec `retries=1` et un délai de
  2 minutes, ce qui absorbe les incidents réseau passagers.
- **Reprise d'une tâche seule.** Les étapes s'échangent leurs résultats par fichiers ;
  n'importe quelle tâche peut être relancée isolément, et retombe sur le dernier artefact
  archivé si le fichier de transit a été nettoyé.
- **Chargement incrémental.** Seules les publications absentes sont ajoutées : rejouer
  une exécution ne crée jamais de doublon et n'écrase jamais l'historique.
- **Journalisation centralisée.** Tous les événements sont écrits dans `logs/` avec
  niveau, horodatage et module d'origine, en console et en fichier.

## 5. Fréquence des vérifications

| Vérification | Fréquence | Moyen |
|---|---|---|
| Exécution du DAG | quotidienne (`schedule="@daily"`) | ordonnanceur Airflow |
| Contrôle des KPI | après chaque exécution | tableau de bord Streamlit |
| Revue des logs d'erreur | quotidienne | `logs/multimodal_etl.log` et logs Airflow |
| Suivi du quota d'API | hebdomadaire | KPI « appels d'API consommés » |
| Revue de tendance | hebdomadaire | historique des exécutions du tableau de bord |
| Audit de dérive des données | mensuel | comparaison de distributions (§6) |

## 6. Détection de dérive

Au-delà des seuils instantanés, on surveille l'**évolution** des distributions dans le
temps : répartition des langues, des sources, longueur des textes, part d'images. Une
valeur isolée se lit mal ; un taux de validité de 80 % n'a pas le même sens selon qu'il
monte ou qu'il descend. C'est le rôle de l'historique des exécutions, alimenté par une
fiche JSON par exécution dans `data/processed/runs/`.

Pour aller plus loin, **Evidently** produit des rapports de dérive automatisés et se
branche directement sur l'historique des jeux de données de `data/processed/`.

## 7. Alerting

- **Canaux** : e-mail et webhook (Slack ou Teams) sur seuil rouge. Airflow fournit
  nativement `on_failure_callback` et les notifications par e-mail.
- **Contenu d'une alerte** : nom du DAG et de la tâche, horodatage, indicateur en cause,
  valeur observée face au seuil, lien vers les logs de la tâche.

## 8. Sécurité de la base de données

- **Authentification** : aucun secret en dur. Les identifiants passent par variables
  d'environnement (`MULTIMODAL_ETL_DB_URL`), et par un gestionnaire de secrets en production.
- **Rôles** : un compte applicatif limité en lecture/écriture aux tables du pipeline,
  distinct du compte administrateur.
- **Chiffrement** : TLS pour les connexions, chiffrement au repos — proposé par défaut
  sur les PostgreSQL managés.
- **Injection SQL** : les requêtes qui composent un nom de table le valident contre la
  liste des tables du schéma avant exécution ; aucun nom ne peut venir d'une saisie
  extérieure.
- **Traçabilité** : le champ `ingested_at` et l'historique des exécutions permettent de
  savoir quand et par quelle exécution chaque ligne est entrée en base.

## 9. Industrialisation : au-delà de la machine de développement

Le pipeline tourne aujourd'hui sur un poste, avec Airflow en Docker et une base SQLite.
Le passage à l'échelle ne remet pas en cause sa conception — les étapes sont déjà
découplées et communiquent par fichiers — mais change l'infrastructure qui l'exécute.

**Sur une plateforme de données managée (Databricks).** C'est la cible la plus directe :
les mêmes fonctions Python deviennent les tâches d'un *Job* Databricks, le stockage passe
de `data/` à un stockage objet, et la base cible devient une table Delta. On y gagne
l'élasticité du calcul, la gestion des versions de données et un catalogue. La
transposition est faible : la logique métier ne bouge pas, seule la couche d'exécution
change.

**Sur Kubernetes.** Alternative quand l'infrastructure est déjà là et qu'on veut rester
maître de l'environnement. Airflow s'y déploie avec le `KubernetesExecutor` : chaque
tâche s'exécute dans son propre pod, isolé et dimensionné à son besoin — l'extraction est
limitée par le réseau, la transformation par le processeur. La zone de transit passe
alors d'un dossier local à un volume partagé ou à un stockage objet.

Dans les deux cas, deux points sont à reprendre : le **stockage des images**, qui doit
migrer vers un stockage objet plutôt que le disque local, et la **parallélisation de
l'extraction**, aujourd'hui séquentielle source par source, qui devient rentable dès que
le nombre de sources augmente.
