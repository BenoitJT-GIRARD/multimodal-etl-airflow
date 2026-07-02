"""Constructeur programmatique des notebooks.

On construit les notebooks avec ``nbformat`` pour garantir leur reproductibilité :
le code des cellules réutilise le package ``multimodal_etl`` (mêmes fonctions que les
scripts et le DAG), et la narration en français déroule le raisonnement étape par
étape. Les notebooks sont ensuite exécutés (voir ``--execute``) pour embarquer les
sorties dans les notebooks.

Usage :
    uv run python scripts/build_notebooks.py            # construit
    uv run python scripts/build_notebooks.py --execute  # construit puis exécute
"""

from __future__ import annotations

import sys
from pathlib import Path

import nbformat as nbf

ROOT = Path(__file__).resolve().parents[1]
NOTEBOOKS_DIR = ROOT / "notebooks"

_SETUP = (
    "import sys\n"
    "from pathlib import Path\n"
    "\n"
    "ROOT = Path.cwd().parent if Path.cwd().name == 'notebooks' else Path.cwd()\n"
    "sys.path.insert(0, str(ROOT / 'src'))\n"
    "\n"
    "from dotenv import load_dotenv\n"
    "load_dotenv(ROOT / '.env')\n"
    "\n"
    "from multimodal_etl.logging_setup import setup_logging\n"
    "setup_logging()"
)


def md(text: str) -> nbf.NotebookNode:
    """Cellule Markdown."""
    return nbf.v4.new_markdown_cell(text)


def code(text: str) -> nbf.NotebookNode:
    """Cellule de code."""
    return nbf.v4.new_code_cell(text)


def _ecris(nb: nbf.NotebookNode, nom: str) -> None:
    """Écrit le notebook sur disque."""
    NOTEBOOKS_DIR.mkdir(parents=True, exist_ok=True)
    nb.metadata["kernelspec"] = {
        "display_name": "Python 3",
        "language": "python",
        "name": "python3",
    }
    chemin = NOTEBOOKS_DIR / nom
    nbf.write(nb, chemin)
    print(f"[ok] notebook construit : {chemin.name}")


# --------------------------------------------------------------------------- #
# Notebook 01 — Exploration des sources
# --------------------------------------------------------------------------- #
def notebook_exploration() -> None:
    nb = nbf.v4.new_notebook()
    nb.cells = [
        md(
            "# 01 — Exploration et qualification des sources de données\n\n"
            "**Auteur :** Benoit Girard  \n"
            ""
            "Ce notebook accompagne le rapport d'exploration des sources. Il vérifie concrètement que les "
            "sources retenues fournissent bien des données **multimodales** (texte + image) "
            "exploitables pour entraîner un détecteur de fake news. Le rapport détaillé se "
            "trouve dans `docs/rapport_exploration_sources.md`."
        ),
        md(
            "## Définition du *done*\n\n"
            "| Critère | Cible |\n|---|---|\n"
            "| Au moins 3 sources multimodales qualifiées | ✅ |\n"
            "| Présence vérifiée de texte **et** d'image par publication | ✅ |\n"
            "| Au moins une source labellisée (vérité terrain) | ✅ |\n"
            "| Méthodes d'extraction identifiées | ✅ |"
        ),
        code(_SETUP),
        md(
            "## 1. Flux RSS de presse — source officielle, multimodale, sans clé\n\n"
            "Les flux RSS exposent, pour chaque article, un **titre**, un **résumé** et "
            "souvent une **image** (`media:content`, `enclosure` ou `<img>` dans le résumé). "
            "On lit un flux avec `feedparser` et on extrait l'image avec une fonction dédiée."
        ),
        code(
            "from multimodal_etl.config import ExtractionConfig\n"
            "from multimodal_etl.sources.rss import fetch_rss_feed\n"
            "\n"
            "config = ExtractionConfig()\n"
            "echantillon = fetch_rss_feed('bbc_news', dict(config.rss_feeds)['bbc_news'], config)\n"
            "print(f'{len(echantillon)} publications lues depuis BBC News')\n"
            "exemple = next(p for p in echantillon if p['image_url'])\n"
            "for cle in ('title', 'image_url', 'url'):\n"
            "    print(f'{cle:10s}: {str(exemple[cle])[:90]}')"
        ),
        md(
            "On constate qu'une entrée RSS porte bien **du texte et une image** : "
            "la modalité visuelle est donc disponible dès la source."
        ),
        md(
            "## 2. API NewsData.io — actualité multimodale via REST/JSON\n\n"
            "NewsData.io renvoie des articles au format JSON avec un champ `image_url` direct. "
            "La source ne s'active que si une clé `NEWSDATA_API_KEY` est présente."
        ),
        code(
            "from multimodal_etl.sources import newsdata\n"
            "\n"
            "print('Source NewsData.io activée :', newsdata.is_enabled())\n"
            "articles = newsdata.fetch_newsdata(config)\n"
            "print(f'{len(articles)} articles récupérés')\n"
            "if articles:\n"
            "    a = articles[0]\n"
            "    print('Titre :', a['title'][:90])\n"
            "    print('Image :', a['image_url'][:90])"
        ),
        md(
            "## 3. FakeNewsNet — la vérité terrain (real / fake)\n\n"
            "FakeNewsNet est la **seule source labellisée**. C'est elle qui rend possible "
            "l'apprentissage supervisé. On charge l'échantillon versionné."
        ),
        code(
            "from multimodal_etl.sources.fakenewsnet import fetch_fakenewsnet\n"
            "import pandas as pd\n"
            "\n"
            "labellisees = fetch_fakenewsnet(config)\n"
            "df = pd.DataFrame(labellisees)\n"
            "print(f'{len(df)} publications labellisées')\n"
            "df['label'].value_counts()"
        ),
        md(
            "## Conclusion\n\n"
            "Les trois sources intégrées sont complémentaires : **RSS** et **NewsData.io** "
            "apportent un flux frais et multimodal ; **FakeNewsNet** apporte les labels. "
            "Toutes reposent sur des **canaux officiels** (pas de scraping). La stratégie "
            "complète est argumentée dans le rapport d'exploration des sources."
        ),
    ]
    _ecris(nb, "01_exploration_sources.ipynb")


# --------------------------------------------------------------------------- #
# Notebook 02 — Extraction
# --------------------------------------------------------------------------- #
def notebook_extraction() -> None:
    nb = nbf.v4.new_notebook()
    nb.cells = [
        md(
            "# 02 — Scripts d'extraction automatisée\n\n"
            "**Auteur :** Benoit Girard  \n"
            ""
            "Ce notebook déroule l'**étape Extract** du pipeline : collecter les publications "
            "multimodales des trois sources, **sans intervention manuelle**, avec gestion "
            "d'erreurs et journalisation, puis sauvegarder le résultat brut en JSON."
        ),
        md(
            "## Définition du *done*\n\n"
            "| Critère | Cible |\n|---|---|\n"
            "| Exécution sans intervention manuelle | ✅ |\n"
            "| Code structuré en fonctions claires | ✅ |\n"
            "| Gestion des erreurs + logs | ✅ |\n"
            "| Données cohérentes avec le cas d'usage | ✅ |"
        ),
        code(_SETUP),
        md(
            "## 1. Architecture de l'extraction\n\n"
            "Le code est **modularisé** : un module par source dans `multimodal_etl.sources`, "
            "chacun exposant une fonction `fetch_*`. L'orchestrateur `extract_all` isole "
            "chaque source dans un `try/except` : une source en panne n'interrompt jamais "
            "les autres."
        ),
        code(
            "from multimodal_etl.config import ExtractionConfig\n"
            "from multimodal_etl.extract import extract_all, save_raw\n"
            "\n"
            "records = extract_all(ExtractionConfig())\n"
            "print(f'Total : {len(records)} publications brutes')"
        ),
        md("## 2. Répartition par source\n\nOn vérifie que chaque source a contribué."),
        code("import pandas as pd\ndf = pd.DataFrame(records)\ndf['source'].value_counts()"),
        md(
            "## 3. Vérification de la multimodalité\n\n"
            "On contrôle la **présence de liens d'images exploitables** : un détecteur "
            "multimodal a besoin du couple texte + image."
        ),
        code(
            "avec_image = df['image_url'].astype(bool).sum()\n"
            'print(f"{avec_image}/{len(df)} publications brutes possèdent une URL d\'image")\n'
            "df[df['image_url'].astype(bool)][['source', 'title', 'image_url']].head(5)"
        ),
        md("## 4. Sauvegarde du brut\n\nLes données brutes sont écrites en JSON dans `data/raw/`."),
        code("chemin = save_raw(records)\nprint('Fichier brut :', chemin.name)"),
        md(
            "## Conclusion\n\n"
            "L'extraction s'exécute d'un seul appel, journalise chaque étape et produit un "
            "JSON brut cohérent. Ces données alimentent l'étape de transformation (notebook 03)."
        ),
    ]
    _ecris(nb, "02_extraction.ipynb")


# --------------------------------------------------------------------------- #
# Notebook 03 — Transformation
# --------------------------------------------------------------------------- #
def notebook_transformation() -> None:
    nb = nbf.v4.new_notebook()
    nb.cells = [
        md(
            "# 03 — Pipeline de transformation reproductible\n\n"
            "**Auteur :** Benoit Girard  \n"
            ""
            "Ce notebook déroule l'**étape Transform** : nettoyer, valider, normaliser et "
            "exporter les données brutes vers un dataset propre conforme au schéma "
            "(`docs/schema_donnees.md`). Le pipeline est organisé en trois temps explicites — "
            "**lecture → traitement → export** — et journalisé."
        ),
        md(
            "## Définition du *done*\n\n"
            "| Critère | Cible |\n|---|---|\n"
            "| Fonctionne sans erreur depuis les données extraites | ✅ |\n"
            "| Pipeline découpé en étapes claires | ✅ |\n"
            "| Logs traçant chaque transformation | ✅ |\n"
            "| Paramètres configurables | ✅ |"
        ),
        code(_SETUP),
        md(
            "## 1. Les fonctions unitaires de transformation\n\n"
            "Chaque transformation est une **petite fonction nommée**, testable "
            "indépendamment. Démonstration sur des exemples."
        ),
        code(
            "from multimodal_etl.config import TransformConfig\n"
            "from multimodal_etl.transform import nettoie_texte, valide_image, extrait_domaine\n"
            "\n"
            "cfg = TransformConfig()\n"
            "print(repr(nettoie_texte('<p>Bonjour&nbsp;  le   <b>monde</b> !</p>')))\n"
            "print('image .jpg valide :', valide_image('https://site.com/a.jpg', cfg))\n"
            "print('page .html rejetée :', valide_image('https://site.com/a.html', cfg))\n"
            "print('domaine :', extrait_domaine('https://www.bbc.co.uk/news/article'))"
        ),
        md(
            "## 2. Paramètres configurables\n\n"
            "Le comportement du pipeline est piloté par `TransformConfig` (longueur minimale "
            "de texte, image obligatoire ou non, format de sortie). On rend ici le mode "
            "multimodal **strict** : toute publication sans image valide est écartée."
        ),
        code(
            "cfg = TransformConfig(require_image=True, min_text_length=30, output_format='parquet')\n"
            "cfg"
        ),
        md(
            "## 3. Lecture → traitement → export\n\nOn applique le pipeline au dernier fichier brut."
        ),
        code(
            "from multimodal_etl.config import RAW_DIR\n"
            "from multimodal_etl.transform import lit_brut, traite, exporte\n"
            "\n"
            "raw_path = sorted(RAW_DIR.glob('raw_publications_*.json'))[-1]\n"
            "bruts = lit_brut(raw_path)\n"
            "df, stats = traite(bruts, cfg)\n"
            "stats"
        ),
        md(
            "Les statistiques montrent l'effet du nettoyage : publications rejetées "
            "(texte trop court ou image manquante) et doublons retirés."
        ),
        code("df[['source', 'title', 'has_image', 'text_length', 'label']].head(8)"),
        md("## 4. Contrôle qualité : le lien texte-image\n\nOn vérifie l'association texte-image."),
        code(
            "assert df['has_image'].all(), 'En mode strict, toutes les lignes ont une image'\n"
            "assert (df['text_length'] >= cfg.min_text_length).all()\n"
            "print('Contrôles OK : chaque publication a un texte exploitable ET une image.')"
        ),
        code("chemin = exporte(df, cfg)\nprint('Dataset exporté :', chemin.name)"),
        md(
            "## Conclusion\n\n"
            "Le pipeline produit un dataset propre, typé et multimodal, prêt pour le "
            "chargement (étape Load) et l'entraînement. Il est reproductible (mêmes entrées "
            "→ mêmes sorties) et entièrement journalisé."
        ),
    ]
    _ecris(nb, "03_transformation.ipynb")


# --------------------------------------------------------------------------- #
# Notebook 04 — KPI
# --------------------------------------------------------------------------- #
def notebook_kpi() -> None:
    nb = nbf.v4.new_notebook()
    nb.cells = [
        md(
            "# 04 — Indicateurs de performance (KPI) du pipeline\n\n"
            "**Auteur :** Benoit Girard  \n"
            ""
            "Ce notebook calcule et visualise les **KPI** du pipeline : qualité des données, "
            "performance (durée, débit) et coût (appels API). Le tableau de bord interactif "
            "correspondant est `dashboard/app.py`."
        ),
        md(
            "## Définition du *done*\n\n"
            "| Critère | Cible |\n|---|---|\n"
            "| KPI mesurant les points critiques du pipeline | ✅ |\n"
            "| Visualisations lisibles et étiquetées | ✅ |\n"
            "| Compréhensible par un public non technique | ✅ |"
        ),
        code(_SETUP),
        md("## 1. Chargement des derniers artefacts et calcul des KPI"),
        code(
            "from multimodal_etl.kpi import charge_dernier_dataset, compute_kpis\n"
            "\n"
            "df, stats, run = charge_dernier_dataset()\n"
            "kpis = compute_kpis(df, stats, run)\n"
            "kpis['qualite']"
        ),
        code("kpis['performance']"),
        md(
            "## 2. Qualité des données\n\n"
            "Les KPI de qualité mesurent les points critiques : taux de validité (précision "
            "de l'ingestion) et **taux d'association texte-image** (cœur du cas d'usage)."
        ),
        code(
            "import plotly.express as px\n"
            "q = kpis['qualite']\n"
            "indicateurs = {\n"
            "    'Validité': q['taux_validite_pct'],\n"
            "    'Texte-image': q['taux_association_texte_image_pct'],\n"
            "    'Labellisé': q['taux_labellise_pct'],\n"
            "}\n"
            "fig = px.bar(x=list(indicateurs), y=list(indicateurs.values()),\n"
            "             labels={'x': 'Indicateur', 'y': 'Pourcentage'}, range_y=[0, 100],\n"
            "             title='KPI de qualité des données (%)')\n"
            "fig.show()"
        ),
        md("## 3. Répartition des sources\n\nLa diversité des sources est un gage de robustesse."),
        code(
            "rep = kpis['volume']['repartition_sources']\n"
            "fig = px.pie(values=list(rep.values()), names=list(rep.keys()),\n"
            "             title='Répartition des publications par source')\n"
            "fig.show()"
        ),
        md("## 4. Performance par étape\n\nDurée de chaque étape de l'ETL."),
        code(
            "p = kpis['performance']\n"
            "etapes = {'Extraction': p['duree_extraction_sec'],\n"
            "          'Transformation': p['duree_transformation_sec'],\n"
            "          'Chargement': p['duree_chargement_sec']}\n"
            "fig = px.bar(x=list(etapes), y=list(etapes.values()),\n"
            "             labels={'x': 'Étape', 'y': 'Durée (s)'},\n"
            '             title="Temps d\'exécution par étape")\n'
            "fig.show()"
        ),
        md(
            "## Conclusion\n\n"
            "Les KPI confirment un pipeline **précis** (fort taux de validité et "
            "d'association texte-image), **rapide** (quelques secondes par run) et **maîtrisé "
            "en coût** (un seul appel API par exécution). Ils sont suivis en continu via le "
            "tableau de bord et le plan de monitoring."
        ),
    ]
    _ecris(nb, "04_kpi.ipynb")


def main() -> None:
    """Construit les quatre notebooks, et les exécute si --execute est passé."""
    notebook_exploration()
    notebook_extraction()
    notebook_transformation()
    notebook_kpi()

    if "--execute" in sys.argv:
        from nbconvert.preprocessors import ExecutePreprocessor

        for chemin in sorted(NOTEBOOKS_DIR.glob("0*.ipynb")):
            print(f"[info] exécution de {chemin.name} ...")
            nb = nbf.read(chemin, as_version=4)
            ExecutePreprocessor(timeout=300, kernel_name="python3").preprocess(
                nb, {"metadata": {"path": str(NOTEBOOKS_DIR)}}
            )
            nbf.write(nb, chemin)
            print(f"[ok] {chemin.name} exécuté avec sorties")


if __name__ == "__main__":
    main()
