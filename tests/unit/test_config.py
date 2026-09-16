"""The three knobs a run is steered by, and what each refuses.

The pipeline reads four sources into ``data/``, and until these existed neither could be
changed without editing a frozen dataclass: replaying one source after an outage meant
commenting out three lines of the connector table, and running the pipeline anywhere other
than beside the code was impossible. A wrong value fails here, at the moment the
configuration is built, and not two minutes into a run.
"""

from __future__ import annotations

import importlib

import pytest

from multimodal_etl import config


def _reloaded():
    """Rebuild the module so the module-level paths are recomputed from the environment."""
    return importlib.reload(config)


@pytest.fixture(autouse=True)
def _restore_module():
    yield
    importlib.reload(config)


def test_without_a_variable_the_four_sources_all_run(monkeypatch) -> None:
    monkeypatch.delenv("MULTIMODAL_ETL_SOURCES", raising=False)
    assert config.ExtractionConfig().enabled_sources == config.SOURCE_NAMES


def test_a_subset_of_sources_is_read_in_order(monkeypatch) -> None:
    monkeypatch.setenv("MULTIMODAL_ETL_SOURCES", "rss, kaggle_fakeddit")
    assert config.ExtractionConfig().enabled_sources == ("rss", "kaggle_fakeddit")


def test_an_unknown_source_is_named_rather_than_ignored(monkeypatch) -> None:
    """Silently dropping it would run three sources where four were asked for."""
    monkeypatch.setenv("MULTIMODAL_ETL_SOURCES", "rss,twitter")
    with pytest.raises(ValueError, match="twitter"):
        config.ExtractionConfig()


def test_without_a_variable_the_shipped_feeds_are_used(monkeypatch) -> None:
    monkeypatch.delenv("MULTIMODAL_ETL_RSS_FEEDS", raising=False)
    assert config.ExtractionConfig().rss_feeds == config.DEFAULT_RSS_FEEDS


def test_feeds_are_read_as_label_equals_url(monkeypatch) -> None:
    monkeypatch.setenv(
        "MULTIMODAL_ETL_RSS_FEEDS", "local=http://127.0.0.1:9/feed.xml,other=http://127.0.0.1:9/b"
    )
    assert config.ExtractionConfig().rss_feeds == (
        ("local", "http://127.0.0.1:9/feed.xml"),
        ("other", "http://127.0.0.1:9/b"),
    )


def test_a_feed_without_a_label_is_refused(monkeypatch) -> None:
    """`feedparser` accepts any string, so an unlabelled URL would run and produce nothing."""
    monkeypatch.setenv("MULTIMODAL_ETL_RSS_FEEDS", "http://127.0.0.1:9/feed.xml")
    with pytest.raises(ValueError, match="label=url"):
        config.ExtractionConfig()


def test_the_data_directory_defaults_to_data_beside_the_code(monkeypatch) -> None:
    monkeypatch.delenv("MULTIMODAL_ETL_DATA_DIR", raising=False)
    reloaded = _reloaded()
    assert reloaded.DATA_DIR == reloaded.PROJECT_ROOT / "data"


def test_an_absolute_data_directory_is_taken_as_it_is(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("MULTIMODAL_ETL_DATA_DIR", str(tmp_path))
    reloaded = _reloaded()
    assert tmp_path == reloaded.DATA_DIR
    assert tmp_path / "raw" == reloaded.RAW_DIR
    assert tmp_path / "db" == reloaded.DB_DIR


def test_a_relative_data_directory_hangs_off_the_project_root(monkeypatch) -> None:
    monkeypatch.setenv("MULTIMODAL_ETL_DATA_DIR", "var/scratch-data")
    reloaded = _reloaded()
    assert reloaded.DATA_DIR == reloaded.PROJECT_ROOT / "var" / "scratch-data"


def test_the_load_target_is_sqlite_in_the_data_directory_by_default(monkeypatch, tmp_path) -> None:
    monkeypatch.delenv("MULTIMODAL_ETL_DB_URL", raising=False)
    monkeypatch.setenv("MULTIMODAL_ETL_DATA_DIR", str(tmp_path))
    reloaded = _reloaded()
    assert reloaded.LoadConfig().resolved_url.endswith("db/multimodal_etl.db")


def test_relative_and_absolute_paths_are_inverses_of_each_other() -> None:
    """A dataset records `data/raw/images/x.jpg`, and has to be readable from anywhere."""
    absolute = config.IMAGES_DIR / "x.jpg"
    assert config.absolute_path(config.relative_path(absolute)) == absolute


def test_the_versioned_sample_is_found_whatever_the_data_directory(monkeypatch, tmp_path) -> None:
    """It is a committed input, not a run output: it does not move with `MULTIMODAL_ETL_DATA_DIR`.

    Hanging it off the data directory sent the capture run looking for it in an empty folder;
    the source found nothing, and the dashboard was photographed saying it had no dataset.
    """
    monkeypatch.setenv("MULTIMODAL_ETL_DATA_DIR", str(tmp_path))
    reloaded = _reloaded()
    assert reloaded.SAMPLES_DIR == reloaded.PROJECT_ROOT / "data" / "samples"
    assert (reloaded.SAMPLES_DIR / "fakeddit_sample.tsv").is_file()


def test_preparing_the_directories_never_creates_the_sample_directory(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("MULTIMODAL_ETL_DATA_DIR", str(tmp_path / "fresh"))
    reloaded = _reloaded()
    reloaded.ensure_dirs()

    assert reloaded.RAW_DIR.is_dir()
    assert reloaded.INTERIM_DIR.is_dir()
    assert not (tmp_path / "fresh" / "samples").exists()
