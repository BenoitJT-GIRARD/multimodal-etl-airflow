"""Tests unitaires des fonctions de transformation."""

from __future__ import annotations

from multimodal_etl.config import TransformConfig
from multimodal_etl.transform import (
    construit_publication,
    extrait_domaine,
    genere_id,
    nettoie_texte,
    normalise_label,
    valide_image,
)


def test_nettoie_texte_retire_html_et_espaces() -> None:
    brut = "<p>Bonjour   le   <b>monde</b> !</p>\n"
    assert nettoie_texte(brut) == "Bonjour le monde !"


def test_nettoie_texte_chaine_vide() -> None:
    assert nettoie_texte("") == ""


def test_valide_image_accepte_extensions_connues() -> None:
    config = TransformConfig()
    assert valide_image("https://site.com/photo.jpg", config) is True
    assert valide_image("https://site.com/photo.png?w=800", config) is True


def test_valide_image_rejette_url_invalide() -> None:
    config = TransformConfig()
    assert valide_image("", config) is False
    assert valide_image("ftp://site.com/photo.jpg", config) is False
    assert valide_image("https://site.com/page.html", config) is False


def test_extrait_domaine() -> None:
    assert extrait_domaine("https://www.bbc.co.uk/news/article") == "bbc.co.uk"
    assert extrait_domaine("") == ""


def test_genere_id_est_stable_et_unique() -> None:
    id1 = genere_id("https://a.com", "Titre A")
    id2 = genere_id("https://a.com", "Titre A")
    id3 = genere_id("https://b.com", "Titre B")
    assert id1 == id2
    assert id1 != id3
    assert len(id1) == 16


def test_normalise_label() -> None:
    assert normalise_label("Real") == "real"
    assert normalise_label("FAKE") == "fake"
    assert normalise_label("") is None
    assert normalise_label("controverse") == "unverified"


def test_construit_publication_valide() -> None:
    config = TransformConfig()
    brut = {
        "source": "rss:test",
        "source_type": "rss",
        "title": "Un titre de test suffisamment long",
        "text": "Un contenu de test assez long pour passer le seuil minimal de caracteres.",
        "url": "https://news.example.com/article",
        "image_url": "https://news.example.com/img.jpg",
        "language": "en",
        "label": "fake",
        "label_source": "fakenewsnet:politifact",
    }
    pub = construit_publication(brut, config, "2026-06-29T10:00:00+00:00")
    assert pub is not None
    assert pub.has_image is True
    assert pub.domain == "example.com"
    assert pub.label == "fake"


def test_construit_publication_rejette_sans_image_en_mode_strict() -> None:
    config = TransformConfig(require_image=True)
    brut = {
        "title": "Titre valide pour le test",
        "text": "Texte suffisamment long pour depasser le seuil minimal impose.",
        "url": "https://news.example.com/a",
        "image_url": "",
    }
    assert construit_publication(brut, config, "2026-06-29T10:00:00+00:00") is None


def test_construit_publication_rejette_texte_trop_court() -> None:
    config = TransformConfig()
    brut = {
        "title": "Titre",
        "text": "court",
        "url": "https://a.com",
        "image_url": "https://a.com/i.jpg",
    }
    assert construit_publication(brut, config, "2026-06-29T10:00:00+00:00") is None
