"""Unit tests of the image download."""

from __future__ import annotations

import io
from pathlib import Path

from PIL import Image

from multimodal_etl import images
from multimodal_etl.config import PROJECT_ROOT, ImageConfig, absolute_path


class FakeResponse:
    """Imitates the minimum of a ``requests`` response the module uses."""

    def __init__(self, content: bytes, content_type: str) -> None:
        self.content = content
        self.headers = {"Content-Type": content_type}

    def raise_for_status(self) -> None:
        return None


def _valid_png() -> bytes:
    """Build a real 2x2 pixel PNG image in memory."""
    buffer = io.BytesIO()
    Image.new("RGB", (2, 2), color="red").save(buffer, format="PNG")
    return buffer.getvalue()


def test_url_looks_plausible() -> None:
    assert images.url_plausible("https://site.com/photo.jpg") is True
    # A URL without an extension is still plausible: plenty of CDNs serve those.
    assert images.url_plausible("https://cdn.site.com/media/12345") is True
    assert images.url_plausible("") is False
    assert images.url_plausible("ftp://site.com/photo.jpg") is False
    assert images.url_plausible("not-a-url") is False


def test_the_file_name_is_deterministic() -> None:
    first = images.filename_for("https://site.com/a.png", "image/png")
    second = images.filename_for("https://site.com/a.png", "image/png")
    other = images.filename_for("https://site.com/b.png", "image/png")
    assert first == second
    assert first != other
    assert first.endswith(".png")


def test_download_image_writes_the_file(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(
        images.requests, "get", lambda *a, **k: FakeResponse(_valid_png(), "image/png")
    )
    path = images.download_image("https://site.com/a.png", ImageConfig(), tmp_path)
    assert path is not None
    assert path.is_file()


def test_download_image_rejects_a_non_image_type(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(
        images.requests, "get", lambda *a, **k: FakeResponse(b"<html></html>", "text/html")
    )
    assert images.download_image("https://site.com/page", ImageConfig(), tmp_path) is None
    assert list(tmp_path.iterdir()) == []


def test_download_image_deletes_an_unreadable_file(tmp_path: Path, monkeypatch) -> None:
    # The server announces an image, but the content is not one.
    monkeypatch.setattr(
        images.requests,
        "get",
        lambda *a, **k: FakeResponse(b"this is not an image", "image/png"),
    )
    assert images.download_image("https://site.com/trap.png", ImageConfig(), tmp_path) is None
    assert list(tmp_path.iterdir()) == []


def test_download_images_respects_the_cap(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(images, "IMAGES_DIR", tmp_path)
    monkeypatch.setattr(
        images.requests, "get", lambda *a, **k: FakeResponse(_valid_png(), "image/png")
    )
    records = [{"image_url": f"https://site.com/{i}.png"} for i in range(5)]

    counts = images.download_images(records, ImageConfig(max_images=2))

    assert counts["tentees"] == 2
    assert counts["reussies"] == 2
    assert counts["ignorees"] == 3
    assert [bool(r["image_path"]) for r in records] == [True, True, False, False, False]


def test_the_recorded_path_is_relative_to_the_project(tmp_path: Path, monkeypatch) -> None:
    # An absolute path would make the dataset useless outside the machine that produced
    # it — the Airflow container, for instance.
    directory = PROJECT_ROOT / "data" / "raw" / "images"
    monkeypatch.setattr(images, "IMAGES_DIR", directory)
    monkeypatch.setattr(
        images.requests, "get", lambda *a, **k: FakeResponse(_valid_png(), "image/png")
    )
    record = {"image_url": "https://site.com/relative.png"}

    images.download_images([record], ImageConfig())

    path = str(record["image_path"])
    assert path.startswith("data/raw/images/")
    assert not Path(path).is_absolute()
    absolute_path(path).unlink(missing_ok=True)
