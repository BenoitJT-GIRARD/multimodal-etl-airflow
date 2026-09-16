"""Unit tests of the working area between the steps."""

from __future__ import annotations

import os
from pathlib import Path

from multimodal_etl import transit


def _prepare(tmp_path: Path, monkeypatch) -> tuple[Path, Path, Path]:
    """Point the working area and the archive folders at tmp_path."""
    interim = tmp_path / "interim"
    raw = tmp_path / "raw"
    processed = tmp_path / "processed"
    for directory in (interim, raw, processed):
        directory.mkdir()

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
    # This fallback is what allows the transform step to be replayed alone after a cleanup.
    _, raw, _ = _prepare(tmp_path, monkeypatch)
    older = raw / "raw_publications_20260819_090000.json"
    newer = raw / "raw_publications_20260820_090000.json"
    older.write_text("older", encoding="utf-8")
    newer.write_text("newer", encoding="utf-8")
    os.utime(older, (1_700_000_000, 1_700_000_000))
    os.utime(newer, (1_700_003_600, 1_700_003_600))

    found = transit.extraction_input()

    assert found is not None
    assert found.name == newer.name


def test_extraction_input_returns_none_without_data(tmp_path: Path, monkeypatch) -> None:
    _prepare(tmp_path, monkeypatch)
    assert transit.extraction_input() is None


def test_dataset_input_falls_back_to_the_last_archive(tmp_path: Path, monkeypatch) -> None:
    _, _, processed = _prepare(tmp_path, monkeypatch)
    archive = processed / "publications_20260820_090000.parquet"
    archive.write_bytes(b"parquet")

    found = transit.dataset_input()

    assert found is not None
    assert found.name == archive.name


def test_metrics_round_trip(tmp_path: Path, monkeypatch) -> None:
    _prepare(tmp_path, monkeypatch)
    transit.write_metrics("extract", {"duration_sec": 1.5, "publications_extracted": 10})

    metrics = transit.read_metrics("extract")

    assert metrics["publications_extracted"] == 10


def test_read_metrics_returns_an_empty_dict_when_absent(tmp_path: Path, monkeypatch) -> None:
    _prepare(tmp_path, monkeypatch)
    assert transit.read_metrics("load") == {}


def test_clear_deletes_every_temporary_file(tmp_path: Path, monkeypatch) -> None:
    interim, _, _ = _prepare(tmp_path, monkeypatch)
    (interim / transit.EXTRACTION).write_text("[]", encoding="utf-8")
    transit.write_metrics("extract", {"duration_sec": 1.0})

    removed = transit.clear()

    assert sorted(removed) == sorted([transit.EXTRACTION, transit.METRICS_FILES["extract"]])
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
        metrics = pipeline.run_load()

    loader.assert_called_once()
    assert loader.call_args.args[0] == dataset
    assert metrics["publications_in_db"] == 7
