"""The Streamlit theme and the figure palette are the same colours, or they are two identities.

``.streamlit/config.toml`` cannot import anything: Streamlit reads it before the process
starts. So the values are written there by hand, and this test is what keeps them from
drifting away from :mod:`multimodal_etl.figure_style`, which is the copy the charts read.
"""

from __future__ import annotations

import tomllib

from multimodal_etl.figure_style import PALETTE
from multimodal_etl.utils.paths import ROOT_DIR

THEME = tomllib.loads((ROOT_DIR / ".streamlit" / "config.toml").read_text(encoding="utf-8"))


def test_every_theme_colour_is_a_token_of_the_palette() -> None:
    expected = {
        "primaryColor": PALETTE["primary"],
        "backgroundColor": PALETTE["paper"],
        "secondaryBackgroundColor": PALETTE["surface"],
        "textColor": PALETTE["ink"],
    }
    assert {key: THEME["theme"][key] for key in expected} == expected


def test_the_editor_toolbar_is_hidden() -> None:
    """It is not part of the product, and it was in every published screenshot."""
    assert THEME["client"]["toolbarMode"] == "minimal"


def test_the_page_accepts_no_upload() -> None:
    """A dashboard that reads versioned artefacts has nothing to receive."""
    assert THEME["server"]["maxUploadSize"] == 1
    assert THEME["server"]["enableXsrfProtection"] is True
