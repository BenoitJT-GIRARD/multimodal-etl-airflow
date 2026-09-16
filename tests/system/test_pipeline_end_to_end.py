"""The pipeline started the way the README says to start it, against a feed it can be sure of.

``uv run python scripts/run_etl.py``, in a subprocess, with its own data directory and one RSS
feed served from this machine. Everything downstream is real: feedparser reads the XML,
requests fetches the JPEG, Pillow opens it, pandas writes the Parquet, SQLAlchemy creates the
tables and inserts the rows, and the working area is emptied at the end.

**Why a local feed rather than the three shipped ones.** A system test whose result depends on
what the BBC published this morning is not a test. The three real feeds are exercised by
tests/unit/sources/, against captured XML; what is checked here is the chain, end to end, and
a chain needs an input whose content is known in advance.

The two values the run has to produce are written into the feed: **three** entries, of which
**two** carry a usable image. The third is the one the founding rule of the dataset throws
away, and a run that kept it would pass every other assertion here.
"""

from __future__ import annotations

import http.server
import io
import json
import os
import subprocess
import sys
import threading
from collections.abc import Iterator
from pathlib import Path
from typing import ClassVar

import pytest
from PIL import Image

from multimodal_etl.utils.paths import ROOT_DIR

pytestmark = pytest.mark.system

#: What the feed announces, and what the run therefore has to end up with.
ENTRIES = 3
WITH_A_USABLE_IMAGE = 2

FEED = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:media="http://search.yahoo.com/mrss/">
  <channel>
    <title>Local wire</title>
    <link>http://127.0.0.1/</link>
    <description>A feed served by the test, so the run has a known input.</description>
    <item>
      <title>Harbour works finish two months ahead of schedule</title>
      <link>http://127.0.0.1:{port}/article/1</link>
      <description>The second basin opened this morning, after eighteen months of work on
      the quay and the lock that closes it.</description>
      <pubDate>Mon, 14 Sep 2026 08:00:00 GMT</pubDate>
      <media:content url="http://127.0.0.1:{port}/photo-1.jpg" type="image/jpeg" />
    </item>
    <item>
      <title>Night trains return between the two coasts this winter</title>
      <link>http://127.0.0.1:{port}/article/2</link>
      <description>Two services a week from December, on the route closed in two thousand
      and nine, with a stop added halfway.</description>
      <pubDate>Mon, 14 Sep 2026 09:30:00 GMT</pubDate>
      <media:content url="http://127.0.0.1:{port}/photo-2.jpg" type="image/jpeg" />
    </item>
    <item>
      <title>The image behind this one is a dead link</title>
      <link>http://127.0.0.1:{port}/article/3</link>
      <description>This entry exists to be dropped: its image answers 404, and the rule the
      pipeline is built around is that a publication without a file is not kept.</description>
      <pubDate>Mon, 14 Sep 2026 10:15:00 GMT</pubDate>
      <media:content url="http://127.0.0.1:{port}/missing.jpg" type="image/jpeg" />
    </item>
  </channel>
</rss>
"""


def _jpeg(colour: tuple[int, int, int]) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (64, 48), color=colour).save(buffer, format="JPEG")
    return buffer.getvalue()


class _Wire(http.server.BaseHTTPRequestHandler):
    """Serves the feed and two photographs, and 404s the third."""

    payloads: ClassVar[dict[str, tuple[str, bytes]]] = {}

    def do_GET(self) -> None:
        entry = self.payloads.get(self.path)
        if entry is None:
            self.send_error(404)
            return
        content_type, body = entry
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *_args: object) -> None:
        """Silence: the request log would land in the middle of pytest's output."""


@pytest.fixture(scope="module")
def wire() -> Iterator[int]:
    """A web server on loopback, for the length of this module. Returns its port."""
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _Wire)
    port = server.server_address[1]
    _Wire.payloads = {
        "/feed.xml": ("application/rss+xml", FEED.format(port=port).encode()),
        "/photo-1.jpg": ("image/jpeg", _jpeg((18, 63, 90))),
        "/photo-2.jpg": ("image/jpeg", _jpeg((188, 106, 36))),
    }
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield port
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


@pytest.fixture(scope="module")
def completed_run(wire: int, tmp_path_factory: pytest.TempPathFactory) -> dict:
    """Run the pipeline once, exactly as ``## Running it`` says to, and hand back its record."""
    data = tmp_path_factory.mktemp("pipeline-data")
    environment = {
        **os.environ,
        "MULTIMODAL_ETL_DATA_DIR": str(data),
        "MULTIMODAL_ETL_SOURCES": "rss",
        "MULTIMODAL_ETL_RSS_FEEDS": f"local_wire=http://127.0.0.1:{wire}/feed.xml",
        # The `.env` of whoever runs the suite must not decide where this writes.
        "MULTIMODAL_ETL_DB_URL": f"sqlite:///{(data / 'run.db').as_posix()}",
        "NEWSDATA_API_KEY": "",
        "PYTHONIOENCODING": "utf-8",
    }
    finished = subprocess.run(
        [sys.executable, str(ROOT_DIR / "scripts" / "run_etl.py")],
        cwd=str(ROOT_DIR),
        env=environment,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=300,
        check=False,
    )
    assert finished.returncode == 0, finished.stdout + finished.stderr
    records = sorted((data / "processed" / "runs").glob("run_*.json"))
    assert records, f"no run record written.\n{finished.stdout}\n{finished.stderr}"
    return {
        "data": data,
        "stdout": finished.stdout,
        "record": json.loads(records[-1].read_text(encoding="utf-8")),
    }


def test_the_run_reports_what_it_collected_and_what_it_kept(completed_run: dict) -> None:
    record = completed_run["record"]
    assert record["rows_extracted"] == ENTRIES
    assert record["rows_loaded"] == WITH_A_USABLE_IMAGE
    assert record["rows_in_db"] == WITH_A_USABLE_IMAGE
    assert record["failed_sources"] == 0


def test_the_publication_whose_image_is_missing_is_dropped(completed_run: dict) -> None:
    """The founding rule, checked where it costs something: three in, two kept."""
    statistics = completed_run["record"]["stats"]
    assert statistics["raw_total"] == ENTRIES
    assert statistics["valid_total"] == WITH_A_USABLE_IMAGE


def test_every_kept_publication_has_its_image_on_disk(completed_run: dict) -> None:
    import pandas as pd

    from multimodal_etl.config import absolute_path

    processed = completed_run["data"] / "processed"
    dataset = sorted(processed.glob("publications_*.parquet"))[-1]
    frame = pd.read_parquet(dataset)

    assert len(frame) == WITH_A_USABLE_IMAGE
    assert frame["has_image"].all()
    for path in frame["image_path"]:
        assert absolute_path(path).is_file(), f"{path} is recorded but not on disk"


def test_the_database_holds_the_six_tables_of_the_schema(completed_run: dict) -> None:
    import sqlalchemy

    engine = sqlalchemy.create_engine(f"sqlite:///{(completed_run['data'] / 'run.db').as_posix()}")
    try:
        tables = set(sqlalchemy.inspect(engine).get_table_names())
        assert {
            "source",
            "publication",
            "text_content",
            "image_content",
            "label",
            "publications",
        } <= tables
        with engine.connect() as connection:
            rows = connection.execute(sqlalchemy.text("SELECT COUNT(*) FROM publications")).scalar()
        assert rows == WITH_A_USABLE_IMAGE
    finally:
        engine.dispose()


def test_the_working_area_is_empty_when_the_run_is_over(completed_run: dict) -> None:
    """The fifth step exists to leave nothing behind for the next run to pick up by mistake."""
    interim = completed_run["data"] / "interim"
    assert not list(interim.glob("*")) if interim.exists() else True


def test_the_run_prints_what_it_did(completed_run: dict) -> None:
    """Someone running the command reads the terminal, not the JSON record."""
    printed = completed_run["stdout"]
    assert f"publications extracted : {ENTRIES}" in printed
    assert f"new in database        : {WITH_A_USABLE_IMAGE}" in printed


def test_a_second_run_adds_nothing(wire: int, completed_run: dict) -> None:
    """Idempotency, measured on the database and not predicted by the loader."""
    data: Path = completed_run["data"]
    finished = subprocess.run(
        [sys.executable, str(ROOT_DIR / "scripts" / "run_etl.py")],
        cwd=str(ROOT_DIR),
        env={
            **os.environ,
            "MULTIMODAL_ETL_DATA_DIR": str(data),
            "MULTIMODAL_ETL_SOURCES": "rss",
            "MULTIMODAL_ETL_RSS_FEEDS": f"local_wire=http://127.0.0.1:{wire}/feed.xml",
            "MULTIMODAL_ETL_DB_URL": f"sqlite:///{(data / 'run.db').as_posix()}",
            "NEWSDATA_API_KEY": "",
            "PYTHONIOENCODING": "utf-8",
        },
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=300,
        check=False,
    )
    assert finished.returncode == 0, finished.stdout + finished.stderr

    record = json.loads(sorted((data / "processed" / "runs").glob("run_*.json"))[-1].read_text("utf-8"))
    assert record["rows_extracted"] == ENTRIES
    assert record["rows_loaded"] == 0
    assert record["rows_in_db"] == WITH_A_USABLE_IMAGE
