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


def test_depose_copie_l_artefact_sous_un_nom_fixe(tmp_path: Path, monkeypatch) -> None:
    interim, raw, _ = _prepare(tmp_path, monkeypatch)
    archive = raw / "raw_publications_20260820_090000.json"
    archive.write_text("[]", encoding="utf-8")

    depose = transit.depose(archive, transit.EXTRACTION)

    assert depose == interim / transit.EXTRACTION
    assert depose.read_text(encoding="utf-8") == "[]"


def test_entree_extraction_prefere_le_fichier_de_transit(tmp_path: Path, monkeypatch) -> None:
    interim, raw, _ = _prepare(tmp_path, monkeypatch)
    (raw / "raw_publications_20260820_090000.json").write_text("archive", encoding="utf-8")
    (interim / transit.EXTRACTION).write_text("transit", encoding="utf-8")

    assert transit.entree_extraction().read_text(encoding="utf-8") == "transit"


def test_entree_extraction_se_replie_sur_la_derniere_archive(tmp_path: Path, monkeypatch) -> None:
    # C'est ce repli qui permet de rejouer la transformation seule après un nettoyage.
    _, raw, _ = _prepare(tmp_path, monkeypatch)
    ancienne = raw / "raw_publications_20260819_090000.json"
    recente = raw / "raw_publications_20260820_090000.json"
    ancienne.write_text("ancienne", encoding="utf-8")
    recente.write_text("recente", encoding="utf-8")
    os.utime(ancienne, (1_700_000_000, 1_700_000_000))
    os.utime(recente, (1_700_003_600, 1_700_003_600))

    entree = transit.entree_extraction()

    assert entree is not None
    assert entree.name == recente.name


def test_entree_extraction_renvoie_none_sans_donnee(tmp_path: Path, monkeypatch) -> None:
    _prepare(tmp_path, monkeypatch)
    assert transit.entree_extraction() is None


def test_entree_dataset_se_replie_sur_la_derniere_archive(tmp_path: Path, monkeypatch) -> None:
    _, _, processed = _prepare(tmp_path, monkeypatch)
    archive = processed / "publications_20260820_090000.parquet"
    archive.write_bytes(b"parquet")

    entree = transit.entree_dataset()

    assert entree is not None
    assert entree.name == archive.name


def test_mesures_font_l_aller_retour(tmp_path: Path, monkeypatch) -> None:
    _prepare(tmp_path, monkeypatch)
    transit.ecris_mesures("extraction", {"duree_sec": 1.5, "publications_extraites": 10})

    mesures = transit.lit_mesures("extraction")

    assert mesures["publications_extraites"] == 10


def test_lit_mesures_absentes_renvoie_un_dictionnaire_vide(tmp_path: Path, monkeypatch) -> None:
    _prepare(tmp_path, monkeypatch)
    assert transit.lit_mesures("chargement") == {}


def test_vide_supprime_tous_les_fichiers_temporaires(tmp_path: Path, monkeypatch) -> None:
    interim, _, _ = _prepare(tmp_path, monkeypatch)
    (interim / transit.EXTRACTION).write_text("[]", encoding="utf-8")
    transit.ecris_mesures("extraction", {"duree_sec": 1.0})

    supprimes = transit.vide()

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
        patch.object(pipeline.transit, "entree_dataset", return_value=dataset),
        patch.object(pipeline.transit, "ecris_mesures"),
        patch.object(pipeline, "compte_publications", return_value=7),
        patch.object(pipeline, "load_dataset", return_value={"publications": 3}) as loader,
    ):
        mesures = pipeline.run_load()

    loader.assert_called_once()
    assert loader.call_args.args[0] == dataset
    assert mesures["publications_en_base"] == 7
