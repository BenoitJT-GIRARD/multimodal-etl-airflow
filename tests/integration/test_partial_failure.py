"""The pipeline is built to survive a failing source. These tests check that it does.

Nothing verified this before: the connectors were each wrapped in a `try/except`, which is
an intention and not a guarantee. Every failure here is simulated — no test reaches the
network. The first tests replace a whole connector with a function that raises. The
real-connector tests keep the connector and replace only `requests.get`, so a connector that
catches its own request failures makes them fail.
"""

from __future__ import annotations

import io
import logging
from dataclasses import replace
from pathlib import Path

import pytest
import requests
from PIL import Image

from multimodal_etl import extract, images
from multimodal_etl.config import ExtractionConfig, ImageConfig
from multimodal_etl.sources import fakenewsnet

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


def _answer(status: int, body: bytes, content_type: str):
    """A stand-in for `requests.get` that returns a real `requests.Response`."""

    def get(url, **kwargs):
        response = requests.Response()
        response.status_code = status
        response.reason = "Too Many Requests" if status == 429 else "OK"
        response._content = body
        response.headers["Content-Type"] = content_type
        response.url = url
        return response

    return get


def _raise(exception: Exception):
    def get(url, **kwargs):
        raise exception

    return get


@pytest.mark.parametrize(
    ("source", "get", "expected_cause"),
    [
        ("rss", _raise(requests.exceptions.Timeout("timed out")), "network"),
        ("newsdata", _answer(429, b'{"status": "error"}', "application/json"), "quota"),
        ("newsdata", _answer(200, b"<html>maintenance</html>", "text/html"), "malformed"),
        ("fakenewsnet", _raise(requests.exceptions.ConnectionError("refused")), "network"),
    ],
    ids=["rss-timeout", "newsdata-quota", "newsdata-not-json", "fakenewsnet-unreachable"],
)
def test_a_real_connector_reports_its_failure_to_the_tally(
    monkeypatch, tmp_path: Path, source: str, get, expected_cause: str
) -> None:
    """The connector itself runs; only the network answer is simulated.

    Until the connectors raised their request failures, each of these four cases ended as
    `empty`, or as `network` for the answer that is not JSON, and the failed-sources count
    stayed at zero whatever happened on the network.
    """
    monkeypatch.setenv("NEWSDATA_API_KEY", "a-test-key")
    monkeypatch.setattr(fakenewsnet, "CACHE_DIR", tmp_path / "fakenewsnet")
    monkeypatch.setattr(requests, "get", get)
    config = replace(
        ExtractionConfig(),
        enabled_sources=(source,),
        rss_feeds=(("wire", "https://wire.invalid/rss.xml"),),
    )

    publications, tally = extract.collect_sources(config)

    assert publications == []
    assert tally[source] == {"count": -1, "cause": expected_cause}
    assert extract.failed_sources(tally) == 1


def test_the_newsdata_key_never_reaches_the_log(monkeypatch, caplog) -> None:
    """A failed NewsData.io call is logged with the URL requests quotes in its error.

    The request is prepared the way requests prepares it, so the URL in the error is the one a
    live call would carry. With the key in the query string, that URL held the key in clear.
    """
    key = "a-key-that-must-stay-out-of-the-logs"
    sent: dict[str, str] = {}

    def get(url, params=None, headers=None, **kwargs):
        prepared = requests.Request("GET", url, params=params, headers=headers).prepare()
        sent.update(prepared.headers)
        response = requests.Response()
        response.status_code = 429
        response.reason = "Too Many Requests"
        response._content = b'{"status": "error"}'
        response.url = prepared.url
        return response

    monkeypatch.setenv("NEWSDATA_API_KEY", key)
    monkeypatch.setattr(requests, "get", get)

    with caplog.at_level(logging.INFO):
        _, tally = extract.collect_sources(
            replace(ExtractionConfig(), enabled_sources=("newsdata",))
        )

    assert tally["newsdata"]["cause"] == "quota"
    assert sent["X-ACCESS-KEY"] == key
    assert key not in caplog.text


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
