"""Tests unitaires de la zone de transit entre les étapes."""

from __future__ import annotations

import os
from pathlib import Path

from multimodal_etl import transit


def _prepare(tmp_path: Path, monkeypatch) -> tuple[Path, Path, Path]:
    """Redirige la zone de transit et les dossiers d'archives vers tmp_path."""
    interim = tmp_path / "interim"
    raw = tmp_path / "raw"
    processed = tmp_path / "processed"
    for dossier in (interim, raw, processed):
        dossier.mkdir()

    monkeypatch.setattr(transit, "INTERIM_DIR", interim)
    monkeypatch.setattr(transit, "RAW_DIR", raw)
    monkeypatch.setattr(transit, "PROCESSED_DIR", processed)
    return interim, raw, processed


def test_stage_copies_the_artefact_under_a_fixed_name(tmp_path: Path, monkeypatch) -> None:
    interim, raw, _ = _prepare(tmp_path, monkeypatch)
    archive = raw / "raw_publications_20260820_090000.json"
    archive.write_text("[]", encoding="utf-8")

    stage = transit.stage(archive, transit.EXTRACTION)

    assert stage == interim / transit.EXTRACTION
    assert stage.read_text(encoding="utf-8") == "[]"


def test_extraction_input_prefers_the_working_file(tmp_path: Path, monkeypatch) -> None:
    interim, raw, _ = _prepare(tmp_path, monkeypatch)
    (raw / "raw_publications_20260820_090000.json").write_text("archive", encoding="utf-8")
    (interim / transit.EXTRACTION).write_text("transit", encoding="utf-8")

    assert transit.extraction_input().read_text(encoding="utf-8") == "transit"


def test_extraction_input_falls_back_to_the_last_archive(tmp_path: Path, monkeypatch) -> None:
    # C'est ce repli qui permet de rejouer la transformation seule après un nettoyage.
    _, raw, _ = _prepare(tmp_path, monkeypatch)
    ancienne = raw / "raw_publications_20260819_090000.json"
    recente = raw / "raw_publications_20260820_090000.json"
    ancienne.write_text("ancienne", encoding="utf-8")
    recente.write_text("recente", encoding="utf-8")
    os.utime(ancienne, (1_700_000_000, 1_700_000_000))
    os.utime(recente, (1_700_003_600, 1_700_003_600))

    entree = transit.extraction_input()

    assert entree is not None
    assert entree.name == recente.name


def test_extraction_input_returns_none_without_data(tmp_path: Path, monkeypatch) -> None:
    _prepare(tmp_path, monkeypatch)
    assert transit.extraction_input() is None


def test_dataset_input_falls_back_to_the_last_archive(tmp_path: Path, monkeypatch) -> None:
    _, _, processed = _prepare(tmp_path, monkeypatch)
    archive = processed / "publications_20260820_090000.parquet"
    archive.write_bytes(b"parquet")

    entree = transit.dataset_input()

    assert entree is not None
    assert entree.name == archive.name


def test_metrics_round_trip(tmp_path: Path, monkeypatch) -> None:
    _prepare(tmp_path, monkeypatch)
    transit.write_metrics("extraction", {"duree_sec": 1.5, "publications_extraites": 10})

    mesures = transit.read_metrics("extraction")

    assert mesures["publications_extraites"] == 10


def test_read_metrics_returns_an_empty_dict_when_absent(tmp_path: Path, monkeypatch) -> None:
    _prepare(tmp_path, monkeypatch)
    assert transit.read_metrics("chargement") == {}


def test_clear_deletes_every_temporary_file(tmp_path: Path, monkeypatch) -> None:
    interim, _, _ = _prepare(tmp_path, monkeypatch)
    (interim / transit.EXTRACTION).write_text("[]", encoding="utf-8")
    transit.write_metrics("extraction", {"duree_sec": 1.0})

    supprimes = transit.clear()

    assert sorted(supprimes) == sorted([transit.EXTRACTION, transit.MESURES["extraction"]])
    assert list(interim.iterdir()) == []


def test_pipeline_load_step_delegates_to_the_loader():
    """Regression: pipeline.run_load used to shadow the loader it imported.

    `pipeline` imported `load.etape_chargement` and then defined a function of the same
    name, so the inner call resolved to the pipeline function itself and raised
    ``TypeError: takes from 0 to 1 positional arguments but 2 were given``. The third
    task of the Airflow DAG could not run, and no test covered this path.
    """
    from pathlib import Path
    from unittest.mock import patch

    from multimodal_etl import pipeline

    dataset = Path("data/processed/anything.parquet")
    with (
        patch.object(pipeline.transit, "dataset_input", return_value=dataset),
        patch.object(pipeline.transit, "write_metrics"),
        patch.object(pipeline, "count_publications", return_value=7),
        patch.object(pipeline, "load_dataset", return_value={"publications": 3}) as loader,
    ):
        mesures = pipeline.run_load()

    loader.assert_called_once()
    assert loader.call_args.args[0] == dataset
    assert mesures["publications_en_base"] == 7
