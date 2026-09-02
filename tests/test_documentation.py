"""Vérifie que la documentation reste alignée sur le code.

Le schéma, les seuils d'alerte et les documents livrés décrivent la même chose. Rien
n'empêche mécaniquement le code d'évoluer sans que les documents suivent : ces tests
comblent ce trou.
"""

from __future__ import annotations

from pathlib import Path

from multimodal_etl.config import PROJECT_ROOT
from multimodal_etl.kpi import THRESHOLDS
from multimodal_etl.schema import COLUMNS

DOCS = PROJECT_ROOT / "docs"


def _read(nom: str) -> str:
    path_for = DOCS / nom
    assert path_for.exists(), f"document manquant : {nom}"
    return path_for.read_text(encoding="utf-8")


def test_the_data_dictionary_covers_the_whole_schema() -> None:
    dictionnaire = _read("schema_donnees.md")
    manquants = [champ for champ in COLUMNS if f"`{champ}`" not in dictionnaire]
    assert not manquants, f"champs absents du dictionnaire : {manquants}"


def test_the_diagram_covers_the_whole_schema() -> None:
    diagramme = _read("schema_donnees.mmd")
    manquants = [champ for champ in COLUMNS if champ not in diagramme]
    assert not manquants, f"champs absents du diagramme : {manquants}"


def test_the_monitoring_plan_documents_every_threshold() -> None:
    plan = _read("monitoring_plan.md")
    manquants = [seuil.libelle for seuil in THRESHOLDS.values() if seuil.libelle not in plan]
    assert not manquants, f"seuils absents du plan de monitoring : {manquants}"


def test_the_documents_the_readme_points_at_all_exist() -> None:
    attendus = [
        DOCS / "rapport_exploration_sources.md",
        DOCS / "schema_donnees.mmd",
        DOCS / "schema_donnees.md",
        DOCS / "monitoring_plan.md",
        DOCS / "preuve_execution_airflow.md",
        PROJECT_ROOT / "dags" / "multimodal_etl_dag.py",
        PROJECT_ROOT / "dashboard" / "app.py",
    ]
    manquants = [path_for.name for path_for in attendus if not path_for.exists()]
    assert not manquants, f"documents manquants : {manquants}"


def test_no_document_references_a_missing_file() -> None:
    # Le rapport et le runbook citent des chemins du dépôt : ils doivent exister.
    references = {
        "rapport_exploration_sources.md": ["data/samples/fakeddit_sample.tsv"],
        "runbook_airflow.md": ["docker/Dockerfile", "docker/.env.example"],
    }
    for document, chemins in references.items():
        contenu = _read(document)
        for path_for in chemins:
            assert path_for in contenu, f"{document} ne cite plus {path_for}"
            assert Path(PROJECT_ROOT / path_for).exists(), f"{path_for} n'existe plus"
