"""Tests unitaires du téléchargement des images."""

from __future__ import annotations

import io
from pathlib import Path

from PIL import Image

from multimodal_etl import images
from multimodal_etl.config import PROJECT_ROOT, ImageConfig, absolute_path


class ReponseFactice:
    """Imite le minimum d'une réponse ``requests`` utilisé par le module."""

    def __init__(self, content: bytes, content_type: str) -> None:
        self.content = content
        self.headers = {"Content-Type": content_type}

    def raise_for_status(self) -> None:
        return None


def _valid_png() -> bytes:
    """Construit en mémoire une vraie image PNG de 2x2 pixels."""
    tampon = io.BytesIO()
    Image.new("RGB", (2, 2), color="red").save(tampon, format="PNG")
    return tampon.getvalue()


def test_url_looks_plausible() -> None:
    assert images.url_plausible("https://site.com/photo.jpg") is True
    # Une URL sans extension reste plausible : beaucoup de CDN en servent.
    assert images.url_plausible("https://cdn.site.com/media/12345") is True
    assert images.url_plausible("") is False
    assert images.url_plausible("ftp://site.com/photo.jpg") is False
    assert images.url_plausible("pas-une-url") is False


def test_the_file_name_is_deterministic() -> None:
    premier = images.filename_for("https://site.com/a.png", "image/png")
    second = images.filename_for("https://site.com/a.png", "image/png")
    autre = images.filename_for("https://site.com/b.png", "image/png")
    assert premier == second
    assert premier != autre
    assert premier.endswith(".png")


def test_download_image_writes_the_file(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(
        images.requests, "get", lambda *a, **k: ReponseFactice(_valid_png(), "image/png")
    )
    path_for = images.download_image("https://site.com/a.png", ImageConfig(), tmp_path)
    assert path_for is not None
    assert path_for.is_file()


def test_download_image_rejects_a_non_image_type(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(
        images.requests, "get", lambda *a, **k: ReponseFactice(b"<html></html>", "text/html")
    )
    assert images.download_image("https://site.com/page", ImageConfig(), tmp_path) is None
    assert list(tmp_path.iterdir()) == []


def test_download_image_deletes_an_unreadable_file(tmp_path: Path, monkeypatch) -> None:
    # Le serveur annonce une image, mais le contenu n'en est pas une.
    monkeypatch.setattr(
        images.requests,
        "get",
        lambda *a, **k: ReponseFactice(b"ceci n'est pas une image", "image/png"),
    )
    assert images.download_image("https://site.com/piege.png", ImageConfig(), tmp_path) is None
    assert list(tmp_path.iterdir()) == []


def test_download_images_respects_the_cap(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(images, "IMAGES_DIR", tmp_path)
    monkeypatch.setattr(
        images.requests, "get", lambda *a, **k: ReponseFactice(_valid_png(), "image/png")
    )
    records = [{"image_url": f"https://site.com/{i}.png"} for i in range(5)]

    compteurs = images.download_images(records, ImageConfig(max_images=2))

    assert compteurs["tentees"] == 2
    assert compteurs["reussies"] == 2
    assert compteurs["ignorees"] == 3
    assert [bool(r["image_path"]) for r in records] == [True, True, False, False, False]


def test_the_recorded_path_is_relative_to_the_project(tmp_path: Path, monkeypatch) -> None:
    # Un path_for absolu rendrait le jeu de donnees inutilisable hors de la machine
    # qui l'a produit (le conteneur Airflow, par exemple).
    dossier = PROJECT_ROOT / "data" / "raw" / "images"
    monkeypatch.setattr(images, "IMAGES_DIR", dossier)
    monkeypatch.setattr(
        images.requests, "get", lambda *a, **k: ReponseFactice(_valid_png(), "image/png")
    )
    record = {"image_url": "https://site.com/relatif.png"}

    images.download_images([record], ImageConfig())

    path_for = str(record["image_path"])
    assert path_for.startswith("data/raw/images/")
    assert not Path(path_for).is_absolute()
    absolute_path(path_for).unlink(missing_ok=True)
