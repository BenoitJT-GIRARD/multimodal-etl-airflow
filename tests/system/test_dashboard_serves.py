"""The dashboard started with the README's own command, questioned over HTTP.

``tests/integration/test_dashboard.py`` builds the page through Streamlit's harness, which
proves the callbacks run. It does not prove the command in ``## Running it`` starts anything:
a bad entry point, a theme file Streamlit refuses, a port already taken are all invisible to
the harness and visible to the first reader who types the command.

So this one types it, waits for the health route Streamlit serves, and asks for the page.
"""

from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import time
import tomllib
import urllib.error
import urllib.request
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path

import pytest

from multimodal_etl.utils.paths import ROOT_DIR

pytestmark = pytest.mark.system

#: Streamlit's own readiness route. Answering it means the server is up, not that the script
#: ran: the page is asked for separately below.
HEALTH = "/_stcore/health"
BOOT_TIMEOUT = 90


def _free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


def _get(url: str, timeout: float = 5.0) -> tuple[int, str]:
    with urllib.request.urlopen(url, timeout=timeout) as answer:
        return answer.status, answer.read().decode("utf-8", "replace")


@pytest.fixture(scope="module")
def dashboard(tmp_path_factory: pytest.TempPathFactory) -> Iterator[str]:
    """Start the dashboard as the README says to, on a port of its own."""
    data = tmp_path_factory.mktemp("dashboard-data")
    processed = data / "processed" / "runs"
    processed.mkdir(parents=True)
    # An empty data directory is a legitimate state — the page says what to run — and it is
    # not the one worth photographing or serving, so one run record is laid down.
    (processed / "run_20260914_120000.json").write_text(
        json.dumps(
            {
                "run_at": datetime.now(UTC).isoformat(timespec="seconds"),
                "orchestrator": "script",
                "durations_sec": {"extract": 30.0, "transform": 4.0, "load": 2.0},
                "rows_extracted": 3,
                "rows_loaded": 2,
                "rows_in_db": 2,
                "api_calls": 0,
                "per_source": {"rss": {"count": 3, "cause": "ok"}},
                "failed_sources": 0,
                "images": {"attempted": 3, "succeeded": 2, "bytes": 2048},
                "stats": {"raw_total": 3, "valid_total": 2, "duplicates": 0},
            }
        ),
        encoding="utf-8",
    )

    port = _free_port()
    log = data / "streamlit.log"
    # The server writes to a file and not to a pipe: a pipe no one drains fills up, and the
    # process then blocks on its own output with nothing left to serve.
    with log.open("w", encoding="utf-8") as handle:
        server = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "streamlit",
                "run",
                str(ROOT_DIR / "src" / "multimodal_etl" / "dashboard.py"),
                "--server.port",
                str(port),
                "--server.headless",
                "true",
            ],
            cwd=str(ROOT_DIR),
            env={**os.environ, "MULTIMODAL_ETL_DATA_DIR": str(data), "PYTHONIOENCODING": "utf-8"},
            stdout=handle,
            stderr=subprocess.STDOUT,
        )
        base = f"http://127.0.0.1:{port}"
        try:
            deadline = time.monotonic() + BOOT_TIMEOUT
            while time.monotonic() < deadline:
                if server.poll() is not None:
                    pytest.fail(
                        "streamlit exited before serving:\n"
                        + Path(log).read_text(encoding="utf-8", errors="replace")
                    )
                try:
                    if _get(base + HEALTH, timeout=1)[0] == 200:
                        break
                except (urllib.error.URLError, OSError, TimeoutError):
                    time.sleep(0.5)
            else:
                pytest.fail(
                    f"streamlit did not answer {HEALTH} within {BOOT_TIMEOUT} s:\n"
                    + Path(log).read_text(encoding="utf-8", errors="replace")
                )
            yield base
        finally:
            server.terminate()
            try:
                server.wait(timeout=15)
            except subprocess.TimeoutExpired:
                server.kill()


def test_the_command_in_the_readme_serves_the_application(dashboard: str) -> None:
    """The page itself is drawn by the browser, so what is checked here is that it is served."""
    assert _get(dashboard + HEALTH)[0] == 200

    status, body = _get(dashboard + "/")
    assert status == 200
    assert '<div id="root">' in body


def test_streamlit_reads_the_theme_this_repository_owns() -> None:
    """A `.streamlit/` in the wrong directory is ignored in silence, factory red and all.

    Streamlit resolves its configuration against the **working directory**, so the file is
    only read when the command is run from the repository root — which is what ``## Running
    it`` says to do. ``streamlit config show`` is the product answering what it actually
    applied, in its own process, from that directory.
    """
    shown = subprocess.run(
        [sys.executable, "-m", "streamlit", "config", "show"],
        cwd=str(ROOT_DIR),
        env={**os.environ, "PYTHONIOENCODING": "utf-8"},
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=120,
        check=False,
    )
    assert shown.returncode == 0, shown.stdout + shown.stderr

    # `config show` opens on a banner whose second line carries no `#`, so the text is not
    # TOML until the first section header.
    body = shown.stdout[shown.stdout.index("[global]") :]
    applied = tomllib.loads(body)
    owned = tomllib.loads((ROOT_DIR / ".streamlit" / "config.toml").read_text(encoding="utf-8"))
    assert applied["theme"]["primaryColor"] == owned["theme"]["primaryColor"]
    assert applied["client"]["toolbarMode"] == "minimal"
