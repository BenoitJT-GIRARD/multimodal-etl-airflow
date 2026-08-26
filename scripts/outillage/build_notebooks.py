"""Construit les notebooks du projet.

⚠️ **Script d'outillage.** Il ne fait pas partie du pipeline : il ne sert qu'à
(re)générer les notebooks de `notebooks/`. Voir `scripts/outillage/README.md`.

Les notebooks sont construits avec `nbformat` puis exécutés avec `nbconvert`, ce qui
garantit que le code qu'ils contiennent tourne réellement et que leurs sorties
correspondent à l'état courant du projet.

Usage :
    uv run python scripts/outillage/build_notebooks.py            # construit
    uv run python scripts/outillage/build_notebooks.py --execute  # construit puis exécute
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import nbformat as nbf

ROOT = Path(__file__).resolve().parents[2]
NOTEBOOKS_DIR = ROOT / "notebooks"

# Cellule d'amorçage commune : rend le package importable et active les logs.
_AMORCAGE = (
    "import sys\n"
    "from pathlib import Path\n"
    "\n"
    "RACINE = Path.cwd().parent if Path.cwd().name == 'notebooks' else Path.cwd()\n"
    "sys.path.insert(0, str(RACINE / 'src'))\n"
    "\n"
    "from dotenv import load_dotenv\n"
    "load_dotenv(RACINE / '.env')\n"
    "\n"
    "from multimodal_etl.logging_setup import setup_logging\n"
    "setup_logging()"
)


def md(texte: str) -> nbf.NotebookNode:
    """Cellule Markdown."""
    return nbf.v4.new_markdown_cell(texte)


def code(texte: str) -> nbf.NotebookNode:
    """Cellule de code."""
    return nbf.v4.new_code_cell(texte)


def _ecris(nb: nbf.NotebookNode, nom: str) -> Path:
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
    return chemin


# --------------------------------------------------------------------------- #
# 01 — Exploration des sources
# --------------------------------------------------------------------------- #
def notebook_exploration() -> None:
    nb = nbf.v4.new_notebook()
    nb.cells = [
        md(
            "# 01 — Exploration et qualification des sources\n\n"
            "Ce notebook accompagne le rapport d'exploration des sources. Il vérifie **concrètement**, source par "
            "source, que les données annoncées sont bien là : un texte, une image, et le cas "
            "échéant un label. Le raisonnement complet — pourquoi ces sources, pourquoi pas de "
            "scraping — est dans `docs/rapport_exploration_sources.md`."
        ),
        code(_AMORCAGE),
        md(
            "## Les quatre sources et leurs méthodes d'accès\n\n"
            "Une source du pipeline, c'est un module dans `multimodal_etl.sources` exposant une "
            "fonction `fetch_*`, et une ligne dans la table des connecteurs. Chacune passe par "
            "un canal différent, et c'est voulu : cela évite de dépendre d'un seul mode d'accès."
        ),
        code(
            "from multimodal_etl.extract import _CONNECTEURS\n"
            "\n"
            "for nom, fonction in _CONNECTEURS.items():\n"
            "    print(f'{nom:18s} -> {fonction.__module__}')"
        ),
        md(
            "## 1. Flux RSS — le socle multimodal\n\n"
            "Les flux RSS sont publiés par les éditeurs *pour être rediffusés* : gratuits, sans "
            "clé, mis à jour en continu. La difficulté est ailleurs — **l'image n'est jamais au "
            "même endroit** selon l'éditeur. Le connecteur la cherche successivement dans "
            "`media:content`, `media:thumbnail`, les pièces jointes, puis dans le HTML du résumé."
        ),
        code(
            "from multimodal_etl.config import ExtractionConfig\n"
            "from multimodal_etl.sources.rss import fetch_rss_feed\n"
            "\n"
            "config = ExtractionConfig()\n"
            "flux = dict(config.rss_feeds)\n"
            "publications = fetch_rss_feed('bbc_news', flux['bbc_news'], config)\n"
            "\n"
            "avec_image = [p for p in publications if p['image_url']]\n"
            "print(f'{len(publications)} publications lues, dont {len(avec_image)} avec une image')\n"
            "\n"
            "exemple = avec_image[0]\n"
            "for cle in ('title', 'url', 'image_url', 'access_method'):\n"
            "    print(f'{cle:14s}: {str(exemple[cle])[:88]}')"
        ),
        md(
            "## 2. API NewsData.io — actualité déjà normalisée\n\n"
            "L'API renvoie du JSON avec un champ `image_url` explicite. Elle impose en échange "
            "un quota journalier : le connecteur ne lit qu'une page, et **se désactive proprement** "
            "si aucune clé n'est fournie plutôt que de faire échouer le pipeline."
        ),
        code(
            "from multimodal_etl.sources import newsdata\n"
            "\n"
            "print('Clé API disponible :', newsdata.is_enabled())\n"
            "articles = newsdata.fetch_newsdata(config)\n"
            "print(f'{len(articles)} articles récupérés')\n"
            "if articles:\n"
            "    print('Titre :', articles[0]['title'][:88])\n"
            "    print('Image :', articles[0]['image_url'][:88])"
        ),
        md(
            "## 3. FakeNewsNet — un jeu labellisé, mais sans image\n\n"
            "Les CSV publiés sur GitHub contiennent `id, news_url, title, tweet_ids`. Il n'y a "
            "**aucune image** : ce que la fiche du jeu de données ne dit pas explicitement.\n\n"
            "Deux conséquences pratiques traitées par le connecteur :\n"
            "1. la colonne `tweet_ids` dépasse la taille de champ acceptée par défaut par le "
            "module `csv` — il faut relever la limite, sinon la lecture échoue ;\n"
            "2. l'image doit être retrouvée ailleurs : dans la balise `og:image` que l'éditeur "
            "publie lui-même sur la page de l'article."
        ),
        code(
            "from multimodal_etl.sources import fakenewsnet\n"
            "\n"
            "chemin = fakenewsnet.telecharge_csv('politifact_fake.csv', config)\n"
            "lignes = fakenewsnet.lit_csv(chemin)\n"
            "print('Colonnes réelles du fichier :', list(lignes[0].keys()))\n"
            "print(f'{len(lignes)} lignes labellisées disponibles')\n"
            "print('Exemple de titre :', lignes[0]['title'][:88])"
        ),
        md(
            "### Le rendement de l'enrichissement Open Graph\n\n"
            "On mesure ce que l'on récupère réellement : les URL de PolitiFact datent de "
            "2016-2018 et beaucoup ne répondent plus. C'est une contrainte à connaître, pas un "
            "défaut à cacher — les publications sans image seront écartées à la transformation."
        ),
        code(
            "from multimodal_etl.sources import opengraph\n"
            "\n"
            "echantillon = [\n"
            "    fakenewsnet._construit_record(ligne, 'politifact', 'fake')\n"
            "    for ligne in lignes[:10]\n"
            "]\n"
            "compteurs = opengraph.enrichit_publications(echantillon, config)\n"
            "print(compteurs)"
        ),
        md(
            "## 4. Fakeddit — le jeu multimodal de Kaggle\n\n"
            "Fakeddit associe nativement un titre et une image, avec trois niveaux de labels. "
            "Le fichier se télécharge une fois à la main depuis Kaggle et se dépose dans "
            "`data/raw/kaggle/` ; en son absence, le connecteur lit un échantillon de "
            "démonstration versionné, de structure identique."
        ),
        code(
            "import pandas as pd\n"
            "\n"
            "from multimodal_etl.sources import kaggle_fakeddit\n"
            "\n"
            "publications_kaggle = kaggle_fakeddit.fetch_fakeddit(config)\n"
            "df_kaggle = pd.DataFrame(publications_kaggle)\n"
            "print(f'{len(df_kaggle)} publications chargées')\n"
            "df_kaggle['label'].value_counts()"
        ),
        md(
            "## Bilan\n\n"
            "Les quatre sources sont complémentaires : les flux RSS et l'API apportent le "
            "**volume et la fraîcheur**, FakeNewsNet et Fakeddit apportent des **labels**. "
            "Aucune ne passe par du scraping : ce sont toutes des canaux que le producteur de "
            "la donnée a prévus pour cet usage."
        ),
    ]
    _ecris(nb, "01_exploration_sources.ipynb")


# --------------------------------------------------------------------------- #
# 02 — Extraction
# --------------------------------------------------------------------------- #
def notebook_extraction() -> None:
    nb = nbf.v4.new_notebook()
    nb.cells = [
        md(
            "# 02 — Extraction automatisée\n\n"
            ""
            "L'étape *Extract* du pipeline : collecter les publications des quatre sources "
            "**sans intervention manuelle**, télécharger les images, et écrire le tout en JSON."
        ),
        code(_AMORCAGE),
        md(
            "## 1. Une source en panne ne doit pas arrêter les autres\n\n"
            "`collecte_sources` appelle chaque connecteur dans son propre `try/except` et tient "
            "un bilan : nombre de publications par source, `-1` en cas d'erreur. C'est ce bilan "
            "qui alimente ensuite l'indicateur « sources en échec » du plan de monitoring."
        ),
        code(
            "from multimodal_etl.config import ExtractionConfig\n"
            "from multimodal_etl.extract import collecte_sources\n"
            "\n"
            "publications, bilan = collecte_sources(ExtractionConfig())\n"
            "print(f'{len(publications)} publications collectées')\n"
            "bilan"
        ),
        md(
            "## 2. Ce que renvoie un connecteur\n\n"
            "Tous les connecteurs produisent la **même structure**, quelle que soit l'origine. "
            "C'est ce qui permet à l'étape suivante de les traiter uniformément."
        ),
        code(
            "import pandas as pd\n"
            "\n"
            "df_brut = pd.DataFrame(publications)\n"
            "print('Colonnes :', list(df_brut.columns))\n"
            "df_brut[['source', 'source_type', 'access_method']].value_counts().to_frame('publications')"
        ),
        md(
            "## 3. Télécharger les images, pas seulement leurs URL\n\n"
            "Une URL d'image ne prouve rien : elle peut être morte, protégée, ou pointer vers "
            "une page HTML. Le pipeline **télécharge** donc chaque image et l'ouvre avec Pillow "
            "avant de la conserver. Trois contrôles, du moins cher au plus cher : type MIME "
            "annoncé, taille du fichier, puis décodage réel.\n\n"
            "C'est le chemin du fichier obtenu qui est enregistré à côté du texte."
        ),
        code(
            "from multimodal_etl.config import ImageConfig\n"
            "from multimodal_etl.images import telecharge_images\n"
            "\n"
            "compteurs = telecharge_images(publications, ImageConfig())\n"
            "compteurs"
        ),
        code(
            "avec_fichier = [p for p in publications if p.get('image_path')]\n"
            'print(f"{len(avec_fichier)} publications ont bien un fichier image")\n'
            "exemple = avec_fichier[0]\n"
            "print('Texte :', exemple['title'][:88])\n"
            "print('Image :', exemple['image_path'])"
        ),
        md("Le couple texte / image, affiché tel qu'il sera donné au modèle :"),
        code(
            "from IPython.display import Image, display\n"
            "\n"
            "from multimodal_etl.config import chemin_absolu\n"
            "\n"
            "print(exemple['title'])\n"
            "display(Image(filename=str(chemin_absolu(exemple['image_path'])), width=420))"
        ),
        md(
            "## 4. Sauvegarde du brut\n\n"
            "Le format retenu est le **JSON**, et non le CSV : une publication multimodale "
            "associe un texte et un chemin de fichier, et le JSON conserve cette structure sans "
            "ambiguïté. Le chemin enregistré est **relatif à la racine du projet**, pour rester "
            "valable ailleurs que sur la machine qui l'a produit — le pipeline tourne aussi bien "
            "en local que dans un conteneur Airflow."
        ),
        code(
            "import json\n"
            "\n"
            "from multimodal_etl.extract import save_raw\n"
            "\n"
            "chemin_brut = save_raw(publications)\n"
            "print('Écrit dans :', chemin_brut)\n"
            "print(json.dumps(exemple, ensure_ascii=False, indent=2)[:600])"
        ),
    ]
    _ecris(nb, "02_extraction.ipynb")


# --------------------------------------------------------------------------- #
# 03 — Transformation
# --------------------------------------------------------------------------- #
def notebook_transformation() -> None:
    nb = nbf.v4.new_notebook()
    nb.cells = [
        md(
            "# 03 — Pipeline de transformation\n\n"
            ""
            "L'étape *Transform* : passer de publications brutes hétérogènes à un jeu de données "
            "propre, typé et conforme au schéma. Le pipeline est organisé en trois temps — "
            "**lecture**, **traitement**, **export** — et chaque transformation unitaire est une "
            "petite fonction testable."
        ),
        code(_AMORCAGE),
        md(
            "## 1. Les fonctions unitaires\n\n"
            "Chacune fait une seule chose, ce qui les rend lisibles et testables séparément "
            "(`tests/test_transform.py`)."
        ),
        code(
            "from multimodal_etl.transform import (\n"
            "    extrait_domaine,\n"
            "    nettoie_texte,\n"
            "    normalise_date,\n"
            "    normalise_label,\n"
            ")\n"
            "\n"
            "print(nettoie_texte('<p>Un   résumé &amp; son <b>HTML</b></p>'))\n"
            "print(extrait_domaine('https://www.bbc.co.uk/news/article-123'))\n"
            "print(normalise_date('Mon, 29 Jun 2026 10:00:00 GMT'))\n"
            "print(normalise_date('1767225600'))\n"
            "print(normalise_label('FAKE'), normalise_label('Real'), normalise_label(''))"
        ),
        md(
            "Les dates méritent un mot : chaque source a son format — RFC 822 pour le RSS, ISO "
            "pour l'API, horodatage Unix pour Fakeddit. Sans normalisation, l'indicateur de "
            "fraîcheur serait tout simplement incalculable."
        ),
        md(
            "## 2. La règle qui définit le jeu de données\n\n"
            "`valide_image` ne regarde pas l'URL : elle vérifie que **le fichier est sur le "
            "disque**. Une publication sans image n'entre pas dans le jeu de données. C'est ce "
            "contrôle qui garantit l'association texte-image exigée par le cas d'usage."
        ),
        code(
            "from multimodal_etl.transform import valide_image\n"
            "\n"
            "print(valide_image('data/raw/images/inexistante.jpg'))\n"
            "print(valide_image(''))"
        ),
        md("## 3. Lecture → traitement → export"),
        code(
            "from multimodal_etl.config import RAW_DIR, TransformConfig\n"
            "from multimodal_etl.transform import exporte, lit_brut, traite\n"
            "\n"
            "config = TransformConfig()\n"
            "dernier_brut = sorted(RAW_DIR.glob('raw_publications_*.json'))[-1]\n"
            "brut = lit_brut(dernier_brut)\n"
            "print(f'{len(brut)} publications brutes lues')"
        ),
        code("df, stats = traite(brut, config)\nstats"),
        md(
            "Le taux de rejet est élevé, et c'est normal : presque toutes les publications "
            "écartées le sont pour une raison unique — aucune image exploitable. On le vérifie."
        ),
        code(
            "from multimodal_etl.transform import construit_publication\n"
            "\n"
            "raisons = {'titre vide': 0, 'texte trop court': 0, 'pas d\\'image': 0, 'retenue': 0}\n"
            "for publication in brut:\n"
            "    if not nettoie_texte(str(publication.get('title', ''))):\n"
            "        raisons['titre vide'] += 1\n"
            "    elif len(nettoie_texte(str(publication.get('text', '')))) < config.min_text_length:\n"
            "        raisons['texte trop court'] += 1\n"
            "    elif not valide_image(str(publication.get('image_path', ''))):\n"
            '        raisons["pas d\'image"] += 1\n'
            "    else:\n"
            "        raisons['retenue'] += 1\n"
            "raisons"
        ),
        md(
            "## 4. Le jeu de données produit\n\n"
            "Les colonnes viennent directement de `multimodal_etl.schema`, source unique de vérité "
            "partagée par le code, le diagramme et la documentation."
        ),
        code(
            "df[['source', 'access_method', 'title', 'image_source', 'has_image', 'label']].head(8)"
        ),
        code(
            "print('Répartition par méthode d\\'accès :')\n"
            "print(df['access_method'].value_counts().to_string())\n"
            "print()\n"
            "print('Origine des images :')\n"
            "print(df['image_source'].value_counts().to_string())"
        ),
        md(
            "## 5. Export\n\n"
            "Le format retenu est le **Parquet** : colonnaire, typé, compact. À ce stade le "
            "schéma est fixe et le fichier est destiné à de la lecture analytique. Les "
            "statistiques sont écrites à côté, sous le même nom : le tableau de bord charge "
            "toujours la paire, jamais un jeu de données orphelin."
        ),
        code(
            "chemin = exporte(df, config, stats)\n"
            "print('Dataset :', chemin.name)\n"
            "print('Statistiques :', chemin.with_name(chemin.stem + '_stats.json').name)"
        ),
    ]
    _ecris(nb, "03_transformation.ipynb")


# --------------------------------------------------------------------------- #
# 04 — KPI
# --------------------------------------------------------------------------- #
def notebook_kpi() -> None:
    nb = nbf.v4.new_notebook()
    nb.cells = [
        md(
            "# 04 — Indicateurs de performance du pipeline\n\n"
            ""
            "Les KPI répondent à trois questions : la donnée est-elle **bonne**, le pipeline "
            "est-il **rapide et économe**, et le jeu de données **progresse-t-il** ? Le tableau "
            "de bord interactif correspondant est `dashboard/app.py`."
        ),
        code(_AMORCAGE),
        md(
            "## 1. Charger les artefacts de la dernière exécution\n\n"
            "Trois éléments : le jeu de données, ses statistiques de transformation, et la fiche "
            "de la dernière exécution."
        ),
        code(
            "from multimodal_etl.kpi import charge_dernier_dataset, compute_kpis\n"
            "\n"
            "df, stats, run = charge_dernier_dataset()\n"
            'print(f\'{len(df)} publications, exécution du {run.get("run_at", "?")} \'\n'
            '      f\'({run.get("orchestrateur", "?")})\')\n'
            "kpis = compute_kpis(df, stats, run)"
        ),
        md(
            "## 2. Qualité de la donnée\n\n"
            "Le taux d'association texte-image est le plus important : c'est la définition même "
            "du jeu de données. Le taux de publications datées compte aussi — sans date, pas de "
            "mesure de fraîcheur possible."
        ),
        code("kpis['qualite']"),
        md(
            "## 3. Volume et diversité\n\n"
            "La part de la source dominante mérite une explication : un jeu de données capté à "
            "80 % par un seul éditeur transmet son biais éditorial au modèle. On surveille donc "
            "la concentration, pas seulement le volume."
        ),
        code("kpis['volume']"),
        md(
            "## 4. Fraîcheur\n\n"
            "Un détecteur de fake news doit voir l'actualité récente. Si l'âge médian grimpe, "
            "c'est que le flux s'est figé et qu'on ré-ingère du passé."
        ),
        code("kpis['fraicheur']"),
        md(
            "## 5. Performance et coût\n\n"
            "La rapidité (durée par étape, débit), le coût (appels d'API consommés sur le quota, "
            "disque occupé par les images) et l'apport réel de l'exécution."
        ),
        code("kpis['performance']"),
        md(
            "## 6. Confrontation aux seuils\n\n"
            "Les seuils sont définis dans `multimodal_etl.kpi.SEUILS`, avec la justification de "
            "chacun. Le plan de monitoring et le tableau de bord lisent le même dictionnaire : "
            "le document ne peut pas se désynchroniser de l'application."
        ),
        code(
            "import pandas as pd\n"
            "\n"
            "from multimodal_etl.kpi import evalue_seuils\n"
            "\n"
            "pd.DataFrame(evalue_seuils(kpis))[\n"
            "    ['libelle', 'valeur', 'attendu', 'statut', 'justification']\n"
            "]"
        ),
        md("## 7. Visualisations"),
        code(
            "import matplotlib.pyplot as plt\n"
            "\n"
            "repartition = kpis['volume']['repartition_sources']\n"
            "figure, (gauche, droite) = plt.subplots(1, 2, figsize=(13, 4.5))\n"
            "\n"
            "gauche.barh(list(repartition.keys())[::-1], list(repartition.values())[::-1],\n"
            "            color='#4C78A8')\n"
            'gauche.set_title("Publications par source")\n'
            "gauche.set_xlabel('Nombre de publications')\n"
            "\n"
            "etapes = ['Extraction', 'Transformation', 'Chargement']\n"
            "durees = [kpis['performance']['duree_extraction_sec'],\n"
            "          kpis['performance']['duree_transformation_sec'],\n"
            "          kpis['performance']['duree_chargement_sec']]\n"
            "droite.bar(etapes, durees, color='#F58518')\n"
            'droite.set_title("Temps par étape")\n'
            "droite.set_ylabel('Durée (s)')\n"
            "\n"
            "plt.tight_layout()\n"
            "plt.show()"
        ),
        md(
            "## 8. Historique des exécutions\n\n"
            "Une valeur isolée se lit mal : un taux de validité de 80 % n'a pas le même sens "
            "selon qu'il monte ou qu'il descend. C'est la tendance qui déclenche une action."
        ),
        code(
            "from multimodal_etl.kpi import historique_runs\n"
            "\n"
            "historique = historique_runs()\n"
            "historique[['date', 'orchestrateur', 'publications_extraites',\n"
            "            'publications_ajoutees', 'publications_en_base',\n"
            "            'duree_totale_sec', 'taux_validite_pct']]"
        ),
        md(
            "Le nombre de publications ajoutées décroît d'une exécution à l'autre alors que le "
            "total en base augmente : le chargement est **incrémental**, seules les publications "
            "encore inconnues sont écrites. C'est exactement le comportement attendu d'une "
            "ingestion quotidienne."
        ),
    ]
    _ecris(nb, "04_kpi.ipynb")


# --------------------------------------------------------------------------- #
def execute(chemins: list[Path]) -> None:
    """Exécute les notebooks pour y embarquer leurs sorties."""
    for chemin in chemins:
        print(f"[..] exécution de {chemin.name}")
        resultat = subprocess.run(
            [
                sys.executable,
                "-m",
                "nbconvert",
                "--to",
                "notebook",
                "--execute",
                "--inplace",
                "--ExecutePreprocessor.timeout=900",
                str(chemin),
            ],
            capture_output=True,
            text=True,
            cwd=ROOT,
        )
        if resultat.returncode == 0:
            print(f"[ok] {chemin.name} exécuté")
        else:
            print(f"[erreur] {chemin.name} : {resultat.stderr[-800:]}")


def main() -> None:
    """Construit les quatre notebooks, et les exécute si --execute est passé."""
    notebook_exploration()
    notebook_extraction()
    notebook_transformation()
    notebook_kpi()

    if "--execute" in sys.argv:
        execute(sorted(NOTEBOOKS_DIR.glob("0*.ipynb")))


if __name__ == "__main__":
    main()
