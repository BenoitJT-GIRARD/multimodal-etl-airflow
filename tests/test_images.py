"""Tests unitaires du téléchargement des images."""

from __future__ import annotations

import io
from pathlib import Path

from PIL import Image

from multimodal_etl import images
from multimodal_etl.config import PROJECT_ROOT, ImageConfig, chemin_absolu


class ReponseFactice:
    """Imite le minimum d'une réponse ``requests`` utilisé par le module."""

    def __init__(self, content: bytes, content_type: str) -> None:
        self.content = content
        self.headers = {"Content-Type": content_type}

    def raise_for_status(self) -> None:
        return None


def _png_valide() -> bytes:
    """Construit en mémoire une vraie image PNG de 2x2 pixels."""
    tampon = io.BytesIO()
    Image.new("RGB", (2, 2), color="red").save(tampon, format="PNG")
    return tampon.getvalue()


def test_url_plausible() -> None:
    assert images.url_plausible("https://site.com/photo.jpg") is True
    # Une URL sans extension reste plausible : beaucoup de CDN en servent.
    assert images.url_plausible("https://cdn.site.com/media/12345") is True
    assert images.url_plausible("") is False
    assert images.url_plausible("ftp://site.com/photo.jpg") is False
    assert images.url_plausible("pas-une-url") is False


def test_nom_de_fichier_est_deterministe() -> None:
    premier = images.nom_de_fichier("https://site.com/a.png", "image/png")
    second = images.nom_de_fichier("https://site.com/a.png", "image/png")
    autre = images.nom_de_fichier("https://site.com/b.png", "image/png")
    assert premier == second
    assert premier != autre
    assert premier.endswith(".png")


def test_telecharge_image_ecrit_le_fichier(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(
        images.requests, "get", lambda *a, **k: ReponseFactice(_png_valide(), "image/png")
    )
    chemin = images.telecharge_image("https://site.com/a.png", ImageConfig(), tmp_path)
    assert chemin is not None
    assert chemin.is_file()


def test_telecharge_image_refuse_un_type_non_image(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(
        images.requests, "get", lambda *a, **k: ReponseFactice(b"<html></html>", "text/html")
    )
    assert images.telecharge_image("https://site.com/page", ImageConfig(), tmp_path) is None
    assert list(tmp_path.iterdir()) == []


def test_telecharge_image_supprime_un_fichier_illisible(tmp_path: Path, monkeypatch) -> None:
    # Le serveur annonce une image, mais le contenu n'en est pas une.
    monkeypatch.setattr(
        images.requests,
        "get",
        lambda *a, **k: ReponseFactice(b"ceci n'est pas une image", "image/png"),
    )
    assert images.telecharge_image("https://site.com/piege.png", ImageConfig(), tmp_path) is None
    assert list(tmp_path.iterdir()) == []


def test_telecharge_images_respecte_le_plafond(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(images, "IMAGES_DIR", tmp_path)
    monkeypatch.setattr(
        images.requests, "get", lambda *a, **k: ReponseFactice(_png_valide(), "image/png")
    )
    records = [{"image_url": f"https://site.com/{i}.png"} for i in range(5)]

    compteurs = images.telecharge_images(records, ImageConfig(max_images=2))

    assert compteurs["tentees"] == 2
    assert compteurs["reussies"] == 2
    assert compteurs["ignorees"] == 3
    assert [bool(r["image_path"]) for r in records] == [True, True, False, False, False]


def test_le_chemin_enregistre_est_relatif_au_projet(tmp_path: Path, monkeypatch) -> None:
    # Un chemin absolu rendrait le jeu de donnees inutilisable hors de la machine
    # qui l'a produit (le conteneur Airflow, par exemple).
    dossier = PROJECT_ROOT / "data" / "raw" / "images"
    monkeypatch.setattr(images, "IMAGES_DIR", dossier)
    monkeypatch.setattr(
        images.requests, "get", lambda *a, **k: ReponseFactice(_png_valide(), "image/png")
    )
    record = {"image_url": "https://site.com/relatif.png"}

    images.telecharge_images([record], ImageConfig())

    chemin = str(record["image_path"])
    assert chemin.startswith("data/raw/images/")
    assert not Path(chemin).is_absolute()
    chemin_absolu(chemin).unlink(missing_ok=True)
