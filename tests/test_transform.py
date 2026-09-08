"""Unit tests of the transformation functions."""

from __future__ import annotations

from pathlib import Path

from multimodal_etl.config import PROJECT_ROOT, TransformConfig
from multimodal_etl.schema import generate_id, generate_source_id
from multimodal_etl.transform import (
    build_publication,
    clean_text,
    extract_domain,
    normalise_date,
    normalise_label,
    normalise_language,
    validate_image,
)


def _valid_raw(image_path: str) -> dict[str, object]:
    """A complete raw record, used as a base by several tests."""
    return {
        "source": "rss:test",
        "source_type": "rss",
        "access_method": "rss_feed",
        "title": "A test headline that is long enough to pass validation",
        "text": "Test body copy, long enough to clear the minimum character threshold.",
        "url": "https://news.example.com/article",
        "image_url": "https://news.example.com/img.jpg",
        "image_path": image_path,
        "image_source": "native",
        "language": "en",
        "label": "fake",
        "label_source": "fakenewsnet:politifact",
    }


def test_clean_text_strips_html_and_whitespace() -> None:
    raw = "<p>Hello   the   <b>world</b> !</p>\n"
    assert clean_text(raw) == "Hello the world !"


def test_clean_text_on_an_empty_string() -> None:
    assert clean_text("") == ""


def test_validate_image_requires_the_file_to_exist(tmp_path: Path) -> None:
    image = tmp_path / "image.jpg"
    image.write_bytes(b"bytes")
    assert validate_image(str(image)) is True
    assert validate_image(str(tmp_path / "absent.jpg")) is False
    assert validate_image("") is False


def test_validate_image_resolves_a_path_relative_to_the_project() -> None:
    # The dataset stores relative paths: they have to be resolved from the project root,
    # whatever the current working directory is.
    image = PROJECT_ROOT / "data" / "raw" / "images" / "test_valid_image.jpg"
    image.parent.mkdir(parents=True, exist_ok=True)
    image.write_bytes(b"bytes")
    try:
        assert validate_image("data/raw/images/test_valid_image.jpg") is True
        assert validate_image("data/raw/images/missing.jpg") is False
    finally:
        image.unlink(missing_ok=True)


def test_extract_domain() -> None:
    assert extract_domain("https://www.bbc.co.uk/news/article") == "bbc.co.uk"
    assert extract_domain("") == ""


def test_generate_id_is_stable_and_unique() -> None:
    premier = generate_id("https://a.com", "Titre A")
    second = generate_id("https://a.com", "Titre A")
    autre = generate_id("https://b.com", "Titre B")
    assert premier == second
    assert premier != autre
    assert len(premier) == 16


def test_generate_source_id_is_stable() -> None:
    assert generate_source_id("rss:bbc_news") == generate_source_id("rss:bbc_news")
    assert generate_source_id("rss:bbc_news") != generate_source_id("newsdata")


def test_normalise_label() -> None:
    assert normalise_label("Real") == "real"
    assert normalise_label("FAKE") == "fake"
    assert normalise_label("") is None
    assert normalise_label("controverse") == "unverified"


def test_normalise_language_maps_to_the_iso_code() -> None:
    # NewsData.io returns "english" where the RSS feeds declare "en".
    assert normalise_language("english") == "en"
    assert normalise_language("EN") == "en"
    assert normalise_language("en-GB") == "en"
    assert normalise_language("fr_FR") == "fr"
    assert normalise_language("") == "en"
    assert normalise_language(None) == "en"


def test_normalise_date_harmonises_the_formats() -> None:
    # The RFC 822 format of RSS feeds.
    assert normalise_date("Mon, 29 Jun 2026 10:00:00 GMT").startswith("2026-06-29T10:00:00")
    # The ISO format of the APIs.
    assert normalise_date("2026-06-29 10:00:00").startswith("2026-06-29T10:00:00")
    # The Unix timestamp some datasets use, integer or float.
    assert normalise_date("1500000000").startswith("2017-07-14")
    assert normalise_date("1425138660.0").startswith("2015-02-28")
    assert normalise_date("") is None
    assert normalise_date("date illisible") is None


def test_build_publication_on_a_valid_record(tmp_path: Path) -> None:
    image = tmp_path / "img.jpg"
    image.write_bytes(b"image")

    pub = build_publication(_valid_raw(str(image)), TransformConfig(), "2026-06-29T10:00:00+00:00")

    assert pub is not None
    assert pub.has_image is True
    assert pub.image_path == str(image)
    assert pub.domain == "example.com"
    assert pub.label == "fake"
    assert pub.access_method == "rss_feed"
    assert pub.source_id == generate_source_id("rss:test")


def test_build_publication_rejects_a_missing_image_file() -> None:
    # The image URL is filled in, but no file could be downloaded.
    raw = _valid_raw(image_path="")
    assert build_publication(raw, TransformConfig(require_image=True), "2026-06-29") is None


def test_build_publication_accepts_no_image_in_lenient_mode(tmp_path: Path) -> None:
    raw = _valid_raw(image_path="")
    pub = build_publication(raw, TransformConfig(require_image=False), "2026-06-29")
    assert pub is not None
    assert pub.has_image is False
    assert pub.image_source == "none"


def test_build_publication_rejects_text_that_is_too_short(tmp_path: Path) -> None:
    image = tmp_path / "img.jpg"
    image.write_bytes(b"image")
    raw = _valid_raw(str(image))
    raw["text"] = "too short"
    assert build_publication(raw, TransformConfig(), "2026-06-29") is None
