"""Test de fumée du tableau de bord.

Le tableau de bord est une surface publique : il doit s'ouvrir sans erreur. Streamlit fournit
un utilitaire qui exécute l'application sans navigateur et remonte les exceptions —
c'est le moyen le plus simple de vérifier que la page se construit vraiment.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from multimodal_etl.config import PROJECT_ROOT

APPLICATION = PROJECT_ROOT / "dashboard" / "app.py"


def _run() -> AppTest:
    application = AppTest.from_file(str(APPLICATION), default_timeout=120)
    application.run()
    return application


def test_the_dashboard_builds_without_error() -> None:
    application = _run()
    assert not application.exception, [str(e) for e in application.exception]


def test_the_dashboard_renders_its_sections() -> None:
    if not list((PROJECT_ROOT / "data" / "processed").glob("publications_*_stats.json")):
        pytest.skip("aucun jeu de données produit : lancer scripts/run_etl.py d'abord")

    application = _run()
    titres = [element.value for element in application.subheader]

    assert "État du pipeline" in titres
    assert "Qualité des données" in titres
    # Les cartes KPI sont bien présentes (qualité, volume, performance).
    assert len(application.metric) >= 12


def test_the_dashboard_file_exists() -> None:
    assert Path(APPLICATION).is_file()
