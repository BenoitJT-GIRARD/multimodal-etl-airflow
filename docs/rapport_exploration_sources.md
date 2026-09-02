# Rapport d'exploration des sources de données

**Projet :** Multimodal ETL — extraction de données multimodales pour un détecteur de fake news
**Auteur :** Benoit Girard — ingénieur data junior
étape 1 de la mission

---

## 1. Ce que le pipeline doit produire

Multimodal ETL entraîne un modèle **multimodal** : il analyse conjointement le texte d'une
publication et l'image qui l'accompagne. Le jeu de données doit donc fournir, pour
chaque publication, **un texte et une image réellement associés**.

Le périmètre de ce projet est l'**ingénierie de la donnée** : collecter, normaliser,
stocker. L'annotation *vrai / faux* n'en fait pas partie — elle interviendra plus tard,
et les sources qui en fournissent une sont un bonus, pas un critère de sélection.

### Champs indispensables

| Champ | Rôle | Pourquoi |
|---|---|---|
| `title`, `text` | entrée NLP | signal textuel analysé par le modèle de langage |
| `image_path` | entrée vision | **le fichier image sur disque**, pas seulement son URL |
| `url` | traçabilité | remonter à l'article, dédupliquer |
| `published_at` | fraîcheur | mesurer l'actualité, construire des features temporelles |
| `language` | routage | filtrer par langue |
| `domain` | fiabilité | le domaine de l'éditeur est un signal en soi |
| `label` | cible | quand la source en fournit une |

Le schéma complet figure dans `schema_donnees.md`.

---

## 2. Les méthodes d'accès possibles

Avant de choisir des sources, il faut choisir **comment** on y accède. Cinq méthodes
étaient envisageables, et chacune n'engage pas le même effort de maintenance :

| Méthode | Ce que c'est | Coût de maintenance |
|---|---|---|
| **Flux RSS** | format standardisé publié par l'éditeur pour être rediffusé | très faible : le format ne bouge pas |
| **API REST** | point d'accès officiel, authentifié par clé | faible : versionné, avec quotas explicites |
| **Téléchargement d'un dépôt** | fichiers publiés en clair sur GitHub | nul : les fichiers sont figés |
| **Téléchargement d'un jeu Kaggle** | export d'un jeu de référence, fait une fois | nul : le jeu est versionné |
| **Extraction multimodale** | lire les métadonnées `Open Graph` d'une page d'article | faible : balise standardisée |
| **Scraping HTML** | analyser la structure de la page pour en extraire le contenu | **élevé et permanent** (voir §3) |

Les quatre premières lignes sont des **canaux officiels** : le producteur de la donnée a
prévu qu'on la consomme ainsi. Ce sont celles retenues.

---

## 3. Pourquoi le pipeline n'utilise pas de scraping

Le scraping est techniquement à portée (Scrapy, Selenium, Beautiful Soup). Il a été
écarté pour trois raisons, dans cet ordre d'importance.

**Le coût de maintenance est permanent et imprévisible.** Un extracteur qui repose sur
la structure HTML d'un site casse à chaque refonte, à chaque test A/B, à chaque
changement de nom de classe CSS. L'équipe qui le maintient passe son temps à réparer ce
qui fonctionnait la veille, sans jamais avancer. Ce mode de fonctionnement — une course
permanente derrière les évolutions des plateformes ciblées — fragilise durablement les
produits qui en dépendent : la donnée peut s'interrompre du jour au lendemain, sans
préavis et sans recours. Bâtir l'ingestion de Multimodal ETL là-dessus, c'est accepter un
risque d'exploitation que rien ne compense.

**Les conditions d'utilisation.** La plupart des éditeurs interdisent l'extraction
automatisée de leur contenu dans leurs CGU, tout en publiant *à côté* un flux RSS ou une
API prévus pour cet usage. Utiliser le canal officiel est à la fois plus simple et plus
sûr juridiquement.

**Le rapport effort / gain est mauvais ici.** Les flux RSS des mêmes éditeurs exposent
déjà le titre, le résumé et l'image de chaque article : le scraping n'apporterait que le
corps complet de l'article, dont le modèle multimodal n'a pas besoin en priorité.

### Les outils de scraping assisté par IA

Deux outils récents ont été regardés, car ils changent la nature du problème :

- **ScrapeGraphAI** : décrit la donnée voulue en langage naturel et laisse un modèle de
  langage trouver où elle se situe dans la page. Cela supprime effectivement la casse à
  chaque changement de structure.
- **Chrome for AI / navigateur piloté par un agent** : même principe, avec un navigateur
  réel capable de traiter les pages qui construisent leur contenu en JavaScript.

Ils règlent le problème de maintenance, mais en introduisent d'autres, rédhibitoires
pour un pipeline quotidien : un **coût par page** (appel de modèle), une **latence** sans
commune mesure avec une lecture de flux, et surtout une **non-reproductibilité** — deux
exécutions sur la même page peuvent ne pas extraire exactement la même chose. Un
pipeline dont on ne peut pas garantir la sortie n'est pas industrialisable. Ils restent
notés comme piste pour une source ponctuelle, sans équivalent officiel.

---

## 4. Les quatre sources retenues

Elles ont été choisies pour être complémentaires : deux apportent de la **fraîcheur**,
deux apportent du **volume labellisé et stable**.

### 4.1 Flux RSS de presse — le socle multimodal

| | |
|---|---|
| Accès | `flux_rss` — `feedparser`, aucune clé |
| Modalités | titre + résumé, image dans `media:content`, `enclosure` ou `<img>` |
| Format | RSS / XML |
| Langue | anglais (The Guardian, BBC News, ABC News) |
| Labels | aucun |
| Droits | flux publics, conçus pour la rediffusion |

C'est la source la plus régulière : gratuite, sans quota, renouvelée en continu. Elle
fournit l'essentiel du volume et garantit la fraîcheur du jeu de données.

La difficulté est technique : **l'image n'est pas au même endroit selon l'éditeur**. Le
connecteur la cherche successivement dans quatre emplacements avant d'abandonner.

### 4.2 API NewsData.io — actualité structurée

| | |
|---|---|
| Accès | `api_rest` — `requests` sur `/api/1/news`, paramètre `image=1` |
| Modalités | `title`, `description`, `content`, `image_url` |
| Format | JSON |
| Langue | multilingue (paramétrée sur `en`) |
| Labels | aucun |
| Droits | API officielle, clé requise, palier gratuit limité |

L'API renvoie une donnée déjà normalisée, avec un champ image explicite. En contrepartie
elle impose un **quota journalier** : le connecteur ne lit qu'une page, pose un délai
d'attente maximal, et se désactive proprement si aucune clé n'est fournie. La
consommation de quota est suivie comme un KPI de coût.

### 4.3 FakeNewsNet — jeu labellisé récupéré sur GitHub

| | |
|---|---|
| Accès | `telechargement_github` — les CSV sont publiés en clair dans le dépôt officiel |
| Modalités | titre + URL de l'article ; **aucune image dans les fichiers** |
| Format | CSV (4 fichiers : PolitiFact et GossipCop, `fake` et `real`) |
| Langue | anglais |
| Labels | vérité terrain PolitiFact / GossipCop |
| Droits | index redistribuable ; les données Twitter associées ne le sont pas et ne sont pas utilisées |

C'est la référence académique du domaine. Deux points ont demandé du travail :

**Les fichiers ne sont pas multimodaux.** Les CSV contiennent `id, news_url, title,
tweet_ids` — pas d'image. Le connecteur va donc la chercher dans les métadonnées
**Open Graph** de l'article (`og:image`), c'est-à-dire l'image que l'éditeur publie
lui-même pour l'aperçu de sa page. Le rendement mesuré est d'environ **une image
retrouvée sur trois articles consultés** : les URL de PolitiFact datent de 2016-2018 et
beaucoup ne répondent plus, tandis que celles de GossipCop, plus récentes, aboutissent
une fois sur deux. Les publications sans image sont écartées à la transformation.

**La colonne `tweet_ids` dépasse la limite de champ du module `csv`.** Elle contient des
milliers d'identifiants ; il faut relever explicitement `csv.field_size_limit`, sinon la
lecture échoue.

Les fichiers sont mis en cache dans `data/raw/fakenewsnet/` : les exécutions suivantes
n'ont plus besoin du réseau.

### 4.4 Fakeddit — jeu multimodal récupéré sur Kaggle

| | |
|---|---|
| Accès | `telechargement_kaggle` — export téléchargé une fois, lu localement |
| Modalités | `clean_title` + `image_url` (colonne `hasImage`) |
| Format | TSV |
| Langue | anglais |
| Labels | 3 niveaux (`2_way`, `3_way`, `6_way`) |
| Droits | usage recherche, citation de l'article d'origine |

Fakeddit (Nakamura *et al.*, 2020) rassemble plus d'un million de publications Reddit
**nativement multimodales**. C'est la source la plus proche du besoin.

Le téléchargement d'un jeu Kaggle demande un compte et une clé d'API. Plutôt que
d'ajouter une dépendance et un secret au pipeline pour un jeu de référence qui ne change
pas, on procède comme en entreprise : **le fichier est téléchargé une fois, à la main**,
et déposé dans `data/raw/kaggle/`. Le connecteur se contente de le lire.

> **Procédure de récupération**
> 1. Récupérer un fichier `*.tsv` du dossier `multimodal_only_samples`, au choix sur
>    <https://www.kaggle.com/datasets/vanshikavmittal/fakeddit-dataset> (compte requis)
>    ou dans la distribution des auteurs, liée depuis
>    <https://github.com/entitize/Fakeddit>.
> 2. Le déposer dans `data/raw/kaggle/`.
>
> Le fichier utilisé ici est `multimodal_test_public.tsv` (15,6 Mo, 16 colonnes) : il
> apporte 29 publications multimodales labellisées issues d'une quinzaine de sous-forums.
> Il n'est pas versionné — `data/` est ignoré par git — et doit donc être re-téléchargé
> sur une autre machine.
>
> En son absence, le connecteur bascule sur un **échantillon de démonstration versionné**
> (`data/samples/fakeddit_sample.tsv`) : mêmes colonnes et même codage des labels que le
> jeu réel, titres fabriqués, et images libres de droits hébergées par Wikimedia Commons.
> Le pipeline reste ainsi exécutable immédiatement par n'importe qui, et repasse tout seul
> sur les données réelles dès qu'elles sont présentes.
>
> Un détail traité au passage : Fakeddit encode `created_utc` comme un flottant
> (`1425138660.0`) là où d'autres sources emploient un entier. Sans quoi la date était
> perdue, et avec elle le calcul de fraîcheur.

---

## 5. Sources examinées et écartées

**Reddit et les réseaux sociaux en direct.** Très riches en contenu multimodal, mais
l'accès API est devenu restrictif et payant, les droits de rediffusion sont incertains,
et la frontière entre opinion controversée et désinformation y est particulièrement
floue. Fakeddit apporte la même matière, déjà collectée et annotée.

**Les sources PDF.** Les organismes de fact-checking publient une partie de leurs
analyses en PDF (rapports, décisions, notes). Le format est bien un support multimodal —
texte et illustrations dans le même document — et exploitable avec `pdfplumber` ou
`PyMuPDF`. Écarté ici pour deux raisons : le volume est faible et irrégulier (quelques
documents par mois), et l'association texte-image y est **implicite** — une illustration
en page 3 n'est pas nécessairement liée au paragraphe qui la précède, alors que le cas
d'usage exige un couple texte-image sans ambiguïté. C'est une piste pour enrichir les
métadonnées, pas pour alimenter le volume.

**Hugging Face Datasets.** Canal officiel, souvent multimodal et labellisé, techniquement
simple (`datasets.load_dataset`). Non retenu car il ferait doublon avec Fakeddit sur le
même besoin. C'est l'extension naturelle si le volume devait augmenter.

**Annuaires consultés** pour repérer ces sources : Google Dataset Search, Kaggle,
public-apis.io.

---

## 6. Formats de stockage retenus

Le choix du format découle directement du caractère multimodal de la donnée.

**Données brutes : JSON, accompagné des fichiers image.** Un CSV suffirait pour du texte
seul. Ici, chaque publication associe un texte **et un fichier image** : les images sont
téléchargées dans `data/raw/images/`, et le JSON conserve pour chaque publication son
texte et le **chemin de son image**. Ce chemin est relatif à la racine du projet, afin
que le jeu de données reste valable ailleurs que sur la machine qui l'a produit — le
pipeline tourne aussi bien en local que dans un conteneur Airflow.

```json
{
  "source": "rss:bbc_news",
  "title": "…",
  "text": "…",
  "image_url": "https://…/photo.jpg",
  "image_path": "data/raw/images/9b7c024c13d467b6.jpg",
  "image_source": "native"
}
```

**Jeu de données transformé : Parquet.** Colonnaire, typé et compact : le schéma est
fixe à ce stade et le fichier est destiné à de la lecture analytique. L'export CSV reste
disponible via un paramètre de configuration.

**Stockage final : base relationnelle** (SQLite en local, PostgreSQL en production). La
donnée est tabulaire, de schéma stable, et interrogée par filtres — c'est le cas d'usage
type du relationnel. Elle est chargée sous deux formes : un modèle éclaté en tables
reliées par des clés de jointure, et une table à plat prête pour l'entraînement.

---

## 7. Synthèse

| Source | Accès | Texte | Image | Label | Apport principal |
|---|---|:---:|:---:|:---:|---|
| Flux RSS (3 éditeurs) | flux RSS | oui | native | non | volume et fraîcheur |
| NewsData.io | API REST | oui | native | non | actualité structurée |
| FakeNewsNet | dépôt GitHub | oui | via Open Graph | oui | vérité terrain académique |
| Fakeddit | jeu Kaggle | oui | native | oui | volume multimodal annoté |

Sur une exécution réelle du pipeline : **205 publications collectées** auprès des quatre
sources, dont **143 retenues** après nettoyage et vérification de l'association
texte-image, et **97 % des images demandées effectivement obtenues**. Les publications
écartées le sont presque toutes pour une raison unique et attendue : aucune image
exploitable — principalement des articles FakeNewsNet dont l'URL, datée de 2016-2018, ne
répond plus.

Répartition par méthode d'accès : 97 publications par flux RSS, 29 par le jeu Kaggle,
10 par l'API et 7 par le dépôt GitHub. Le déséquilibre est assumé : les flux fournissent
le volume quotidien, les jeux de données apportent les labels.

---

## Références

- Shu, K., Mahudeswaran, D., Wang, S., Lee, D., Liu, H. (2018). *FakeNewsNet: A Data
  Repository with News Content, Social Context and Dynamic Information for Studying Fake
  News on Social Media*. arXiv:1809.01286 —
  <https://github.com/KaiDMML/FakeNewsNet>
- Nakamura, K., Levy, S., Wang, W. Y. (2020). *Fakeddit: A New Multimodal Benchmark
  Dataset for Fine-grained Fake News Detection*. LREC 2020 —
  <https://github.com/entitize/Fakeddit>
- Zidan, M., Sleem, A., Nabil, A. *et al.* (2025). *Multimodal Fake News Detection: A
  Survey of Text and Visual Content Integration Methods*. International Journal of
  Computers and Information, vol. 7, p. 13-25.
- The Open Graph protocol — <https://ogp.me/>
- NewsData.io — <https://newsdata.io/>
