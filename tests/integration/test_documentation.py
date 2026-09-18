"""The published documents, read where they are published, against the code they describe.

The schema, the alert thresholds and the delivered documents all describe the same thing.
Nothing mechanically stops the code from moving on without the documents following: these
tests fill that hole, and they fail on the day a field is added to
:mod:`multimodal_etl.schema` and nothing else is touched.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
import yaml

from multimodal_etl.kpi import THRESHOLDS
from multimodal_etl.schema import COLUMNS
from multimodal_etl.utils.paths import DOCS_DIR, ROOT_DIR

pytestmark = [pytest.mark.integration, pytest.mark.claim]


def _read(name: str) -> str:
    path = DOCS_DIR / name
    assert path.exists(), f"missing document: {name}"
    return path.read_text(encoding="utf-8")


def test_the_data_dictionary_covers_the_whole_schema() -> None:
    dictionary = _read("DB.md")
    missing = [field for field in COLUMNS if f"`{field}`" not in dictionary]
    assert not missing, f"fields absent from the dictionary: {missing}"


def test_the_diagram_covers_the_whole_schema() -> None:
    diagram = _read("data_schema.mmd")
    missing = [field for field in COLUMNS if field not in diagram]
    assert not missing, f"fields absent from the diagram: {missing}"


def test_the_protocol_documents_every_threshold() -> None:
    plan = _read("protocol.md")
    missing = [t.label for t in THRESHOLDS.values() if t.label not in plan]
    assert not missing, f"thresholds absent from the protocol: {missing}"


def _slug(label: str) -> str:
    """« Share of the dominant source » and `dominant_source_share` name the same measure."""
    return re.sub(r"[^a-z0-9]+", "_", label.lower()).strip("_")


def test_every_indicator_carries_its_definition_and_its_unit() -> None:
    """`metrics.yaml` is the legend of the published numbers, and it is complete."""
    legend = yaml.safe_load((ROOT_DIR / "metrics.yaml").read_text(encoding="utf-8"))["metrics"]
    defined = {_slug(name) for name in legend}

    missing = [t.label for t in THRESHOLDS.values() if _slug(t.label) not in defined]
    assert not missing, f"indicators with no entry in metrics.yaml: {missing}"

    # The unit is decided in the code and repeated in the legend; a disagreement there is a
    # dashboard and a document that print two different units for the same number.
    for threshold in THRESHOLDS.values():
        entry = legend[_slug(threshold.label)]
        assert entry["unit"] == threshold.unit, threshold.label


def test_the_documents_the_readme_points_at_all_exist() -> None:
    expected = [
        DOCS_DIR / "architecture.md",
        DOCS_DIR / "data-source.md",
        DOCS_DIR / "DB.md",
        DOCS_DIR / "interface.md",
        DOCS_DIR / "protocol.md",
        DOCS_DIR / "runbook.md",
        DOCS_DIR / "data_schema.mmd",
        ROOT_DIR / "dags" / "multimodal_etl_dag.py",
        ROOT_DIR / "src" / "multimodal_etl" / "dashboard.py",
    ]
    missing = [path.name for path in expected if not path.exists()]
    assert not missing, f"missing documents: {missing}"


def test_no_document_references_a_missing_file() -> None:
    """A document quoting a path of the repository is only useful while the path is there."""
    references = {
        "data-source.md": ["data/samples/fakeddit_sample.tsv"],
        "runbook.md": ["infra/Dockerfile", "infra/.env.example"],
        "interface.md": [".streamlit/config.toml"],
    }
    for document, paths in references.items():
        content = _read(document)
        for path in paths:
            assert path in content, f"{document} no longer quotes {path}"
            assert Path(ROOT_DIR / path).exists(), f"{path} no longer exists"


def test_every_published_image_is_declared_in_the_manifest() -> None:
    """An image with no manifest entry cannot be retaken, and says nothing about its state."""
    images = DOCS_DIR / "images"
    manifest = json.loads((images / "MANIFEST.json").read_text(encoding="utf-8"))
    declared = set(manifest["images"])
    published = {path.name for path in images.glob("*.png")}
    assert published == declared, (
        f"published {published - declared}, declared {declared - published}"
    )
