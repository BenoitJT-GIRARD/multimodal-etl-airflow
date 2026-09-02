"""Check that the documentation stays aligned with the code.

The schema, the alert thresholds and the delivered documents all describe the same thing.
Nothing mechanically stops the code from moving on without the documents following: these
tests fill that hole.
"""

from __future__ import annotations

from pathlib import Path

from multimodal_etl.config import PROJECT_ROOT
from multimodal_etl.kpi import THRESHOLDS
from multimodal_etl.schema import COLUMNS

DOCS = PROJECT_ROOT / "docs"


def _read(name: str) -> str:
    path = DOCS / name
    assert path.exists(), f"missing document: {name}"
    return path.read_text(encoding="utf-8")


def test_the_data_dictionary_covers_the_whole_schema() -> None:
    dictionary = _read("data_schema.md")
    missing = [field for field in COLUMNS if f"`{field}`" not in dictionary]
    assert not missing, f"fields absent from the dictionary: {missing}"


def test_the_diagram_covers_the_whole_schema() -> None:
    diagram = _read("data_schema.mmd")
    missing = [field for field in COLUMNS if field not in diagram]
    assert not missing, f"fields absent from the diagram: {missing}"


def test_the_monitoring_plan_documents_every_threshold() -> None:
    plan = _read("monitoring_plan.md")
    missing = [t.libelle for t in THRESHOLDS.values() if t.libelle not in plan]
    assert not missing, f"thresholds absent from the monitoring plan: {missing}"


def test_the_documents_the_readme_points_at_all_exist() -> None:
    expected = [
        DOCS / "source_exploration.md",
        DOCS / "data_schema.mmd",
        DOCS / "data_schema.md",
        DOCS / "monitoring_plan.md",
        DOCS / "airflow_run_evidence.md",
        PROJECT_ROOT / "dags" / "multimodal_etl_dag.py",
        PROJECT_ROOT / "dashboard" / "app.py",
    ]
    missing = [path.name for path in expected if not path.exists()]
    assert not missing, f"missing documents: {missing}"


def test_no_document_references_a_missing_file() -> None:
    # The report and the runbook quote paths of the repository: they have to exist.
    references = {
        "source_exploration.md": ["data/samples/fakeddit_sample.tsv"],
        "airflow_runbook.md": ["docker/Dockerfile", "docker/.env.example"],
    }
    for document, paths in references.items():
        content = _read(document)
        for path in paths:
            assert path in content, f"{document} no longer quotes {path}"
            assert Path(PROJECT_ROOT / path).exists(), f"{path} no longer exists"
