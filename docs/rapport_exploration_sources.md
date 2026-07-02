# Rapport d'exploration des sources de données

**Projet :** Extraction de données multimodales pour un détecteur de fake news
**Auteur :** Benoit Girard
---

## 1. Contexte et objectif

Le projet alimente un détecteur automatique de désinformation. Pour entraîner un
modèle **multimodal**, il faut un jeu de données associant, pour chaque publication,
**un texte et une image**, idéalement accompagné d'un **label de vérité terrain**
(*real* / *fake*).

Ce rapport qualifie les sources candidates selon cinq critères :

1. **Modalités** disponibles (texte, image) ;
2. **Format** technique (API REST, JSON, CSV, flux RSS) ;
3. **Langue** des contenus ;
4. **Qualité des labels** (présence et fiabilité d'une vérité terrain) ;
5. **Méthode d'extraction** recommandée et **droits d'usage**.

Il définit aussi les **champs indispensables** à chaque publication et le **format
de sortie** retenu pour le pipeline.

> **Cadrage méthodologique — ne pas confondre opinion et désinformation.**
> Une **opinion controversée** est un jugement subjectif relevant de la liberté
> d'expression ; une **désinformation** est une information *objectivement fausse*
> diffusée pour tromper. Le pipeline cible la seconde catégorie : on privilégie donc
> les sources qui fournissent un **label vérifiable** (FakeNewsNet) et des contenus
> factuels datés, et non des tribunes d'opinion.

---

## 2. Sources retenues

Quatre sources ont été qualifiées, dont **trois sont intégrées au pipeline** (RSS,
NewsData.io, FakeNewsNet) et une quatrième documentée comme piste d'enrichissement
(Hugging Face Datasets). Cette combinaison respecte la recommandation de la mission :
**privilégier les canaux officiels** (API, flux RSS, datasets publics) avant tout
scraping.

### 2.1 Flux RSS de sites de presse *(source intégrée — socle multimodal)*

| Critère | Valeur |
|---|---|
| Modalités | **Texte** (titre + résumé) + **image** (`media:content`, `enclosure`, `<img>`) |
| Format | **RSS/XML** (flux standardisé) |
| Langue | Anglais (The Guardian, BBC News, ABC News) |
| Labels | ❌ Aucun label vrai/faux (presse généraliste) |
| Méthode d'extraction | `feedparser` (lecture du flux) + `BeautifulSoup` (extraction de l'image) |
| Droits d'usage | ✅ Flux **publics et officiels**, conçus pour la rediffusion |

**Pourquoi ?** Les flux RSS sont gratuits, sans clé, mis à jour en continu et
**multimodaux par nature**. Ils garantissent la *fraîcheur* du dataset. Ils ne
fournissent pas de label : ils alimentent la partie « contenu » et servent de flux
de production à étiqueter ultérieurement.

### 2.2 API NewsData.io *(source intégrée — actualité multimodale)*

| Critère | Valeur |
|---|---|
| Modalités | **Texte** (`title`, `description`, `content`) + **image** (`image_url`) |
| Format | **API REST → JSON** |
| Langue | Multilingue (paramètre `language`, ici `en`) |
| Labels | ❌ Pas de label vrai/faux fiable |
| Méthode d'extraction | `requests` sur l'endpoint `/api/1/news`, paramètre `image=1` |
| Droits d'usage | ✅ API officielle, **clé requise**, quota gratuit limité |

**Points de vigilance API** : le palier gratuit limite le nombre d'articles par
requête et impose un **quota journalier**. Le connecteur lit une seule page, pose un
*timeout*, et se désactive proprement si aucune clé n'est fournie — sans jamais
interrompre le pipeline.

### 2.3 Dataset FakeNewsNet *(source intégrée — vérité terrain)*

| Critère | Valeur |
|---|---|
| Modalités | **Texte** (`title`, `text`) + **image** (`images` dans `news content.json`) |
| Format | **CSV** (version minimale) + **JSON** (contenu complet) |
| Langue | Anglais |
| Labels | ✅ **Label fiable** *real* / *fake* (vérité terrain PolitiFact & GossipCop) |
| Méthode d'extraction | Lecture CSV (`csv`/`pandas`) ; téléchargement via le dépôt officiel |
| Droits d'usage | ⚠️ Données sociales (tweets) non redistribuables — **on n'utilise que les CSV labellisés** |

**Pourquoi ?** FakeNewsNet (Shu et al., 2018) est **la référence académique** pour la
détection de fake news. C'est la **seule source à fournir un label de vérité terrain**,
indispensable à l'entraînement supervisé. Le jeu complet n'étant pas redistribuable,
le pipeline lit les CSV réels s'ils ont été téléchargés, sinon un **échantillon
représentatif versionné** (24 lignes équilibrées *real*/*fake*) garantissant une
exécution hors-ligne et reproductible.

### 2.4 Hugging Face Datasets *(piste d'enrichissement documentée)*

| Critère | Valeur |
|---|---|
| Modalités | Variables selon le dataset (souvent **texte + image**) |
| Format | Parquet/Arrow via la bibliothèque `datasets` |
| Langue | Variable (datasets multilingues disponibles) |
| Labels | ✅ Fréquents (datasets supervisés de fake/real news) |
| Méthode d'extraction | `datasets.load_dataset(...)` |
| Droits d'usage | Variables — vérifier la licence de chaque dataset |

Retenue comme **extension naturelle** : permettrait d'augmenter le volume labellisé
sans scraping, via un canal officiel.

---

## 3. Autres pistes explorées (et écartées)

- **Reddit / réseaux sociaux** : riches en multimodal mais labels absents, droits
  d'usage restrictifs et fort risque de confondre opinion et désinformation. Écarté.
- **Scraping direct de sites de news (Scrapy/Selenium)** : possible techniquement
  mais **peu apprécié des éditeurs** et juridiquement sensible. Conformément à la
  recommandation, on **préfère les canaux officiels** (RSS/API) qui exposent déjà les
  mêmes contenus de façon autorisée.
- **Annuaires consultés** : *Google Dataset Search*, *Kaggle*, *public-apis.io* —
  utilisés pour repérer les sources ci-dessus.

---

## 4. Champs indispensables à chaque publication

Pour servir le cas d'usage multimodal, chaque publication doit a minima contenir :

| Champ | Rôle | Indispensable |
|---|---|---|
| `title` / `text` | Entrée **NLP** (classification du texte) | ✅ |
| `image_url` | Entrée **vision** (analyse de l'image) | ✅ |
| `url` | Traçabilité et déduplication | ✅ |
| `published_at` | Fraîcheur, features temporelles | recommandé |
| `language` | Filtrage / routage par langue | ✅ |
| `domain` | Signal de fiabilité de la source | recommandé |
| `label` | **Cible** d'entraînement (real/fake) | si disponible |

Le schéma complet (types, rôles, relations) est détaillé dans le schéma de données
(`docs/schema_donnees.mmd`). Un contrôle clé du pipeline garantit l'**association
texte-image** : une publication sans image valide est écartée en mode multimodal
strict.

---

## 5. Format de sortie retenu

- **Stockage brut** : **JSON** (`data/raw/`) — souple, conserve la structure native
  hétérogène des sources.
- **Dataset transformé** : **Parquet** (`data/processed/`) — colonnaire, typé,
  compact et performant pour l'analyse et l'entraînement (export CSV également
  possible via un paramètre de configuration).
- **Base de chargement** : **base relationnelle** (SQLite en local, PostgreSQL/
  Supabase en production) — le dataset est tabulaire et fortement structuré.

---

## 6. Synthèse

| Source | Texte | Image | Label | Format | Intégrée |
|---|:---:|:---:|:---:|---|:---:|
| Flux RSS (presse) | ✅ | ✅ | ❌ | RSS/XML | ✅ |
| NewsData.io | ✅ | ✅ | ❌ | API/JSON | ✅ |
| FakeNewsNet | ✅ | ✅ | ✅ | CSV/JSON | ✅ |
| Hugging Face Datasets | ✅ | ✅* | ✅* | Parquet | piste |

\* selon le dataset choisi.

La stratégie combine **fraîcheur** (RSS, API) et **vérité terrain** (FakeNewsNet) :
les flux fournissent un volume continu de contenus multimodaux à étiqueter, tandis
que FakeNewsNet apporte les labels nécessaires à l'apprentissage supervisé. L'ensemble
repose exclusivement sur des **canaux officiels**, sans scraping.

---

## Références

- Zidan, M., Sleem, A., Nabil, A. *et al.* (2025). *Multimodal Fake News Detection:
  A Survey of Text and Visual Content Integration Methods*. International Journal of
  Computers and Information, Vol. 7, p. 13–25.
- Shu, K., Mahudeswaran, D., Wang, S., Lee, D., Liu, H. (2018). *FakeNewsNet: A Data
  Repository with News Content, Social Context and Dynamic Information for Studying
  Fake News on Social Media*. arXiv:1809.01286. — <https://github.com/KaiDMML/FakeNewsNet>
- NewsData.io — API d'actualités. <https://newsdata.io/>
- public-apis.io — annuaire d'API publiques.
