"""The five scripts a reader is told to run, tested where they hold logic of their own.

`scripts/` is on the test path, so each one is imported and its functions called, rather than
shelled out to and asserted on by its printed text. The ones that only chain `pipeline.py`
carry nothing worth testing here — `tests/system/` runs those as processes, which is the only
way to learn anything about them.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from multimodal_etl.schema import COLUMNS, ENTITIES


def test_the_mermaid_diagram_carries_every_entity_and_every_field() -> None:
    """Drawn from schema.py: a field added to the code appears without anyone editing it."""
    import build_schema_diagram

    mermaid = build_schema_diagram.build_mermaid()

    assert mermaid.startswith("erDiagram")
    for entity in ENTITIES:
        assert f"    {entity} {{" in mermaid
    missing = [field for field in COLUMNS if field not in mermaid]
    assert not missing, f"fields absent from the diagram: {missing}"


def test_the_diagram_names_the_keys_of_each_entity() -> None:
    import build_schema_diagram

    mermaid = build_schema_diagram.build_mermaid()

    assert 'string id PK "KEY"' in mermaid
    assert 'string source_id PK "KEY"' in mermaid
    assert "PUBLICATION ||--|| IMAGE_CONTENT : pairs" in mermaid


def test_the_diagram_is_a_function_of_the_schema_and_of_nothing_else() -> None:
    """Twice in a row gives the same bytes; scripts/smoke.py compares it to the committed file."""
    import build_schema_diagram

    assert build_schema_diagram.build_mermaid() == build_schema_diagram.build_mermaid()


def test_writing_only_the_mermaid_leaves_the_picture_alone(monkeypatch, tmp_path) -> None:
    """`--no-render` exists because mermaid-cli draws a different PNG from version to version."""
    import build_schema_diagram

    monkeypatch.setattr(build_schema_diagram, "DOCS_DIR", tmp_path)
    monkeypatch.setattr(
        build_schema_diagram, "render", lambda _path: pytest.fail("render was called")
    )

    assert build_schema_diagram.main(["--no-render"]) == 0
    assert (tmp_path / "data_schema.mmd").read_text(encoding="utf-8").startswith("erDiagram")


def test_the_report_is_rendered_from_the_tracked_measures(monkeypatch, tmp_path) -> None:
    """The published markdown is a function of a tracked file, never of the disk's last run."""
    import quality_report

    measures = json.loads((quality_report.MEASURES).read_text(encoding="utf-8"))
    target = tmp_path / "data_quality.md"
    monkeypatch.setattr(quality_report, "REPORT", target)

    assert quality_report.main([]) == 0
    written = target.read_text(encoding="utf-8")
    assert measures["measured_on"] in written
    assert (
        f"n = {measures['collected']} publications collected, {measures['kept']} were kept"
    ) in written


def test_publishing_without_measures_says_which_command_is_missing(monkeypatch, tmp_path) -> None:
    import quality_report

    monkeypatch.setattr(quality_report, "MEASURES", tmp_path / "absent.json")

    assert quality_report.main([]) == 1


def test_measuring_an_empty_dataset_writes_nothing(monkeypatch, tmp_path) -> None:
    """A run that collected nothing must not overwrite the published measures with zeroes."""
    import pandas as pd
    import quality_report

    monkeypatch.setattr(quality_report, "load_latest_dataset", lambda: (pd.DataFrame(), {}, {}))
    written: list[Path] = []
    monkeypatch.setattr(quality_report, "_write", lambda path, payload: written.append(path))

    assert quality_report.main(["--measure"]) == 1
    assert not written


def test_the_duplicate_mode_writes_nothing(monkeypatch, tmp_path, capsys) -> None:
    import pandas as pd
    import quality_report

    frame = pd.DataFrame(
        [
            {
                "id": "a",
                "url": "https://example.invalid/story?utm_source=x",
                "title": "A HEADLINE, SHOUTED",
            },
            {"id": "b", "url": "https://www.example.invalid/story", "title": "A headline, shouted"},
        ]
    )
    monkeypatch.setattr(quality_report, "load_latest_dataset", lambda: (frame, {}, {}))
    monkeypatch.setattr(quality_report, "MEASURES", tmp_path / "absent.json")

    assert quality_report.main(["--duplicates"]) == 0
    printed = capsys.readouterr().out
    # The injected republication is what makes a published zero mean « nothing there ».
    assert "pairs missed  : 1 (by url+title)" in printed
    assert not (tmp_path / "absent.json").exists()
