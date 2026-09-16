"""The pipeline is built to survive a failing source. These tests check that it does.

Nothing verified this before: the connectors were each wrapped in a `try/except`, which is
an intention and not a guarantee. Every failure here is simulated — no test reaches the
network.
"""

from __future__ import annotations

import io
from pathlib import Path

import pytest
import requests
from PIL import Image

from multimodal_etl import extract, images
from multimodal_etl.config import ExtractionConfig, ImageConfig

pytestmark = [pytest.mark.integration, pytest.mark.simulation]


def _valid_png() -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (2, 2), color="red").save(buffer, format="PNG")
    return buffer.getvalue()


class FakeResponse:
    def __init__(self, content: bytes, content_type: str) -> None:
        self.content = content
        self.headers = {"Content-Type": content_type}

    def raise_for_status(self) -> None:
        return None


@pytest.mark.parametrize(
    ("failure", "expected_cause"),
    [
        (requests.exceptions.HTTPError("429 Too Many Requests"), "quota"),
        (requests.exceptions.Timeout("timed out"), "network"),
        (requests.exceptions.ConnectionError("name resolution failed"), "network"),
        (ValueError("malformed payload"), "malformed"),
        (KeyError("image_url"), "malformed"),
    ],
)
def test_one_broken_source_leaves_the_others_intact(monkeypatch, failure, expected_cause) -> None:
    def broken(config: ExtractionConfig) -> list[dict]:
        raise failure

    monkeypatch.setattr(
        extract,
        "_CONNECTORS",
        {
            "rss": lambda config: [{"title": "a"}],
            "newsdata": broken,
            "fakenewsnet": lambda config: [{"title": "b"}],
        },
    )

    publications, tally = extract.collect_sources(ExtractionConfig())

    assert len(publications) == 2, "the healthy sources must still deliver"
    assert tally["newsdata"]["count"] == -1
    assert tally["newsdata"]["cause"] == expected_cause
    assert tally["rss"]["cause"] == "ok"
    assert extract.failed_sources(tally) == 1


def test_every_source_failing_is_not_a_crash(monkeypatch) -> None:
    def broken(config: ExtractionConfig) -> list[dict]:
        raise requests.exceptions.Timeout("timed out")

    monkeypatch.setattr(extract, "_CONNECTORS", {"rss": broken, "fakenewsnet": broken})

    publications, tally = extract.collect_sources(ExtractionConfig())

    assert publications == []
    assert extract.failed_sources(tally) == 2


def test_a_truncated_image_does_not_stop_the_download_loop(tmp_path: Path, monkeypatch) -> None:
    # The second publication must be downloaded even though the first is a trap.
    responses = iter(
        [
            FakeResponse(b"this is not an image", "image/png"),
            FakeResponse(_valid_png(), "image/png"),
        ]
    )
    monkeypatch.setattr(images, "IMAGES_DIR", tmp_path)
    monkeypatch.setattr(images.requests, "get", lambda *a, **k: next(responses))

    records = [{"image_url": "https://s/1.png"}, {"image_url": "https://s/2.png"}]
    counts = images.download_images(records, ImageConfig())

    assert counts["failed"] == 1
    assert counts["succeeded"] == 1
    assert [bool(r["image_path"]) for r in records] == [False, True]


def test_an_oversized_image_is_refused_without_stopping_the_loop(
    tmp_path: Path, monkeypatch
) -> None:
    oversized = FakeResponse(b"\x00" * (2 * 1024 * 1024), "image/png")
    responses = iter([oversized, FakeResponse(_valid_png(), "image/png")])
    monkeypatch.setattr(images, "IMAGES_DIR", tmp_path)
    monkeypatch.setattr(images.requests, "get", lambda *a, **k: next(responses))

    records = [{"image_url": "https://s/big.png"}, {"image_url": "https://s/ok.png"}]
    counts = images.download_images(records, ImageConfig(max_size_mb=1.0))

    assert counts["failed"] == 1
    assert counts["succeeded"] == 1


def test_a_network_error_on_one_image_does_not_stop_the_others(tmp_path: Path, monkeypatch) -> None:
    def get(*args, **kwargs):
        if "1.png" in args[0]:
            raise requests.exceptions.Timeout("timed out")
        return FakeResponse(_valid_png(), "image/png")

    monkeypatch.setattr(images, "IMAGES_DIR", tmp_path)
    monkeypatch.setattr(images.requests, "get", get)

    records = [{"image_url": "https://s/1.png"}, {"image_url": "https://s/2.png"}]
    counts = images.download_images(records, ImageConfig())

    assert counts["failed"] == 1
    assert counts["succeeded"] == 1
