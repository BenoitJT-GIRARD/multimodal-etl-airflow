"""The DAG's contract, read from its source rather than from a running Airflow.

Importing ``dags/multimodal_etl_dag.py`` needs Apache Airflow, which this project does not
install outside its container: the DAG is executed in the image `infra/Dockerfile` builds, and
`docs/runbook.md` carries the transcript of it doing so. What is checked here is what a reader
would check by opening the file — that the five tasks are the five pipeline functions, in the
order the documents claim, and that nothing else is going on.

The reading is an AST parse, so a comment mentioning ``run_load`` proves nothing and a task
renamed in a string is caught.
"""

from __future__ import annotations

import ast

import pytest

from multimodal_etl import pipeline
from multimodal_etl.utils.paths import ROOT_DIR

DAG_FILE = ROOT_DIR / "dags" / "multimodal_etl_dag.py"

#: The five steps, in the order `docs/runbook.md` shows them running.
CHAIN = ("extract", "transform", "load", "metrics", "cleanup")


@pytest.fixture(scope="module")
def tree() -> ast.Module:
    return ast.parse(DAG_FILE.read_text(encoding="utf-8"))


def _operators(tree: ast.Module) -> dict[str, str]:
    """Each ``PythonOperator``'s task_id, and the name of the callable it is given."""
    found: dict[str, str] = {}
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Call) and getattr(node.func, "id", "") == "PythonOperator"):
            continue
        keywords = {k.arg: k.value for k in node.keywords}
        task_id = keywords.get("task_id")
        callable_node = keywords.get("python_callable")
        if isinstance(task_id, ast.Constant) and isinstance(callable_node, ast.Name):
            found[str(task_id.value)] = callable_node.id
    return found


def test_the_dag_declares_the_five_tasks(tree: ast.Module) -> None:
    assert tuple(_operators(tree)) == CHAIN


def test_every_task_calls_a_function_that_exists_in_the_pipeline(tree: ast.Module) -> None:
    """One copy of the logic: the DAG names the same functions the scripts call."""
    for task_id, callable_name in _operators(tree).items():
        if callable_name == "task_metrics":
            # The one wrapper, and it exists to record that the run came from Airflow.
            assert hasattr(pipeline, "run_metrics")
            continue
        assert hasattr(pipeline, callable_name), f"{task_id} calls an unknown {callable_name}"


def test_the_tasks_are_chained_in_order(tree: ast.Module) -> None:
    """`extract >> transform >> load >> metrics >> cleanup`, and nothing branching."""
    chains = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.RShift)
    ]
    assert chains, "the DAG declares no dependency between its tasks"

    names: list[str] = []

    def walk(node: ast.AST) -> None:
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.RShift):
            walk(node.left)
            walk(node.right)
        elif isinstance(node, ast.Name):
            names.append(node.id)

    walk(max(chains, key=lambda n: len(ast.dump(n))))
    assert tuple(names) == CHAIN


def test_the_dag_holds_no_business_logic(tree: ast.Module) -> None:
    """One wrapper, and it only names the orchestrator on the run record."""
    functions = [n.name for n in tree.body if isinstance(n, ast.FunctionDef)]
    assert functions == ["task_metrics"]


def test_the_dag_does_not_patch_the_import_path(tree: ast.Module) -> None:
    """The compose file puts the source tree on PYTHONPATH; a second answer would hide that.

    The docstring of the DAG names `sys.path` to say why it does not use one, so the check is
    on the code and not on the text: an import, an assignment, a call.
    """
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute) and node.attr == "path":
            assert getattr(node.value, "id", "") != "sys", "the DAG patches sys.path"
        if isinstance(node, ast.Import):
            assert all(alias.name != "sys" for alias in node.names), "the DAG imports sys"


def test_a_task_is_retried_once_and_not_indefinitely(tree: ast.Module) -> None:
    """A network hiccup deserves one retry; a broken source deserves a red task, not a loop."""
    defaults = next(
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Assign)
        and any(getattr(t, "id", "") == "default_args" for t in node.targets)
    )
    keys = {
        k.value: v for k, v in zip(defaults.value.keys, defaults.value.values, strict=True)
        if isinstance(k, ast.Constant)
    }
    assert keys["retries"].value == 1
