"""Tests unitaires des fonctions de transformation."""

from __future__ import annotations

from pathlib import Path

from multimodal_etl.config import PROJECT_ROOT, TransformConfig
from multimodal_etl.schema import genere_id, genere_source_id
from multimodal_etl.transform import (
    construit_publication,
    extrait_domaine,
    nettoie_texte,
    normalise_date,
    normalise_label,
    normalise_langue,
    valide_image,
)


def _brut_valide(image_path: str) -> dict[str, object]:
    """Enregistrement brut complet, utilisé comme base dans plusieurs tests."""
    return {
        "source": "rss:test",
        "source_type": "rss",
        "access_method": "flux_rss",
        "title": "Un titre de test suffisamment long",
        "text": "Un contenu de test assez long pour passer le seuil minimal de caractères.",
        "url": "https://news.example.com/article",
        "image_url": "https://news.example.com/img.jpg",
        "image_path": image_path,
        "image_source": "native",
        "language": "en",
        "label": "fake",
        "label_source": "fakenewsnet:politifact",
    }


def test_nettoie_texte_retire_html_et_espaces() -> None:
    brut = "<p>Bonjour   le   <b>monde</b> !</p>\n"
    assert nettoie_texte(brut) == "Bonjour le monde !"


def test_nettoie_texte_chaine_vide() -> None:
    assert nettoie_texte("") == ""


def test_valide_image_exige_un_fichier_present(tmp_path: Path) -> None:
    fichier = tmp_path / "image.jpg"
    fichier.write_bytes(b"contenu")
    assert valide_image(str(fichier)) is True
    assert valide_image(str(tmp_path / "absent.jpg")) is False
    assert valide_image("") is False


def test_valide_image_resout_un_chemin_relatif_au_projet() -> None:
    # Le jeu de donnees stocke des chemins relatifs : ils doivent etre resolus
    # depuis la racine du projet, quel que soit le dossier de travail courant.
    fichier = PROJECT_ROOT / "data" / "raw" / "images" / "test_valide_image.jpg"
    fichier.parent.mkdir(parents=True, exist_ok=True)
    fichier.write_bytes(b"contenu")
    try:
        assert valide_image("data/raw/images/test_valide_image.jpg") is True
        assert valide_image("data/raw/images/inexistante.jpg") is False
    finally:
        fichier.unlink(missing_ok=True)


def test_extrait_domaine() -> None:
    assert extrait_domaine("https://www.bbc.co.uk/news/article") == "bbc.co.uk"
    assert extrait_domaine("") == ""


def test_genere_id_est_stable_et_unique() -> None:
    premier = genere_id("https://a.com", "Titre A")
    second = genere_id("https://a.com", "Titre A")
    autre = genere_id("https://b.com", "Titre B")
    assert premier == second
    assert premier != autre
    assert len(premier) == 16


def test_genere_source_id_est_stable() -> None:
    assert genere_source_id("rss:bbc_news") == genere_source_id("rss:bbc_news")
    assert genere_source_id("rss:bbc_news") != genere_source_id("newsdata")


def test_normalise_label() -> None:
    assert normalise_label("Real") == "real"
    assert normalise_label("FAKE") == "fake"
    assert normalise_label("") is None
    assert normalise_label("controverse") == "unverified"


def test_normalise_langue_ramene_au_code_iso() -> None:
    # NewsData.io renvoie "english" là où les flux RSS déclarent "en".
    assert normalise_langue("english") == "en"
    assert normalise_langue("EN") == "en"
    assert normalise_langue("en-GB") == "en"
    assert normalise_langue("fr_FR") == "fr"
    assert normalise_langue("") == "en"
    assert normalise_langue(None) == "en"


def test_normalise_date_harmonise_les_formats() -> None:
    # Format RFC 822 des flux RSS.
    assert normalise_date("Mon, 29 Jun 2026 10:00:00 GMT").startswith("2026-06-29T10:00:00")
    # Format ISO des API.
    assert normalise_date("2026-06-29 10:00:00").startswith("2026-06-29T10:00:00")
    # Horodatage Unix de certains jeux de données, entier ou flottant.
    assert normalise_date("1500000000").startswith("2017-07-14")
    assert normalise_date("1425138660.0").startswith("2015-02-28")
    assert normalise_date("") is None
    assert normalise_date("date illisible") is None


def test_construit_publication_valide(tmp_path: Path) -> None:
    image = tmp_path / "img.jpg"
    image.write_bytes(b"image")

    pub = construit_publication(
        _brut_valide(str(image)), TransformConfig(), "2026-06-29T10:00:00+00:00"
    )

    assert pub is not None
    assert pub.has_image is True
    assert pub.image_path == str(image)
    assert pub.domain == "example.com"
    assert pub.label == "fake"
    assert pub.access_method == "flux_rss"
    assert pub.source_id == genere_source_id("rss:test")


def test_construit_publication_rejette_sans_fichier_image() -> None:
    # L'URL de l'image est renseignée, mais aucun fichier n'a pu être téléchargé.
    brut = _brut_valide(image_path="")
    assert construit_publication(brut, TransformConfig(require_image=True), "2026-06-29") is None


def test_construit_publication_accepte_sans_image_en_mode_souple(tmp_path: Path) -> None:
    brut = _brut_valide(image_path="")
    pub = construit_publication(brut, TransformConfig(require_image=False), "2026-06-29")
    assert pub is not None
    assert pub.has_image is False
    assert pub.image_source == "aucune"


def test_construit_publication_rejette_texte_trop_court(tmp_path: Path) -> None:
    image = tmp_path / "img.jpg"
    image.write_bytes(b"image")
    brut = _brut_valide(str(image))
    brut["text"] = "court"
    assert construit_publication(brut, TransformConfig(), "2026-06-29") is None
