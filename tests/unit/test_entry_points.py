"""Every entry point a reader starts loads `.env` before the package reads the environment.

Importing `config` fixes the data directory, the list of sources and the database URL once
and for all. A `.env` loaded after that import is read too late, and its `MULTIMODAL_ETL_DATA_DIR`
never reaches the run. Three entry points had no `load_dotenv` at all.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from multimodal_etl.utils.paths import ROOT_DIR, SCRIPTS_DIR

#: What a reader starts by hand, each reading the data directory that `config` resolves at
#: import time. `MULTIMODAL_ETL_DATA_DIR` set in `.env` reaches the run only if `.env` is
#: loaded before that import.
ENTRY_POINTS = (
    SCRIPTS_DIR / "run_etl.py",
    SCRIPTS_DIR / "run_extract.py",
    SCRIPTS_DIR / "run_transform.py",
    SCRIPTS_DIR / "run_load.py",
    SCRIPTS_DIR / "quality_report.py",
    ROOT_DIR / "src" / "multimodal_etl" / "dashboard.py",
)


@pytest.mark.parametrize("entry_point", ENTRY_POINTS, ids=lambda path: path.name)
def test_every_entry_point_loads_dotenv_before_the_package(entry_point: Path) -> None:
    """Read from the source: importing the module here would find `config` already loaded."""
    tree = ast.parse(entry_point.read_text(encoding="utf-8"))
    statements = list(tree.body)

    def loads_dotenv(node: ast.stmt) -> bool:
        return (
            isinstance(node, ast.Expr)
            and isinstance(node.value, ast.Call)
            and getattr(node.value.func, "id", None) == "load_dotenv"
        )

    def imports_the_package(node: ast.stmt) -> bool:
        return (
            isinstance(node, ast.ImportFrom)
            and (node.module or "").startswith("multimodal_etl")
            and node.module != "multimodal_etl.utils.paths"
        )

    loading = [index for index, node in enumerate(statements) if loads_dotenv(node)]
    importing = [index for index, node in enumerate(statements) if imports_the_package(node)]

    assert loading, f"{entry_point.name} never calls load_dotenv"
    assert importing, f"{entry_point.name} imports nothing from the package"
    assert loading[0] < importing[0], f"{entry_point.name} imports the package before .env"
