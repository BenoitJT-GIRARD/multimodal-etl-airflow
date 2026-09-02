"""Vérifie que la documentation reste alignée sur le code.

Le schéma, les seuils d'alerte et les documents livrés décrivent la même chose. Rien
n'empêche mécaniquement le code d'évoluer sans que les documents suivent : ces tests
comblent ce trou.
"""

from __future__ import annotations

from pathlib import Path

from multimodal_etl.config import PROJECT_ROOT
from multimodal_etl.kpi import SEUILS
from multimodal_etl.schema import COLUMNS

DOCS = PROJECT_ROOT / "docs"


def _lit(nom: str) -> str:
    chemin = DOCS / nom
    assert chemin.exists(), f"document manquant : {nom}"
    return chemin.read_text(encoding="utf-8")


def test_le_dictionnaire_des_champs_couvre_tout_le_schema() -> None:
    dictionnaire = _lit("schema_donnees.md")
    manquants = [champ for champ in COLUMNS if f"`{champ}`" not in dictionnaire]
    assert not manquants, f"champs absents du dictionnaire : {manquants}"


def test_le_diagramme_couvre_tout_le_schema() -> None:
    diagramme = _lit("schema_donnees.mmd")
    manquants = [champ for champ in COLUMNS if champ not in diagramme]
    assert not manquants, f"champs absents du diagramme : {manquants}"


def test_le_plan_de_monitoring_documente_chaque_seuil() -> None:
    plan = _lit("plan_monitoring.md")
    manquants = [seuil.libelle for seuil in SEUILS.values() if seuil.libelle not in plan]
    assert not manquants, f"seuils absents du plan de monitoring : {manquants}"


def test_the_documents_the_readme_points_at_all_exist() -> None:
    attendus = [
        DOCS / "rapport_exploration_sources.md",
        DOCS / "schema_donnees.mmd",
        DOCS / "schema_donnees.md",
        DOCS / "plan_monitoring.md",
        DOCS / "preuve_execution_airflow.md",
        PROJECT_ROOT / "dags" / "multimodal_etl_dag.py",
        PROJECT_ROOT / "dashboard" / "app.py",
    ]
    manquants = [chemin.name for chemin in attendus if not chemin.exists()]
    assert not manquants, f"documents manquants : {manquants}"


def test_aucun_document_ne_reference_un_fichier_disparu() -> None:
    # Le rapport et le runbook citent des chemins du dépôt : ils doivent exister.
    references = {
        "rapport_exploration_sources.md": ["data/samples/fakeddit_sample.tsv"],
        "runbook_airflow.md": ["docker/Dockerfile", "docker/.env.example"],
    }
    for document, chemins in references.items():
        contenu = _lit(document)
        for chemin in chemins:
            assert chemin in contenu, f"{document} ne cite plus {chemin}"
            assert Path(PROJECT_ROOT / chemin).exists(), f"{chemin} n'existe plus"
